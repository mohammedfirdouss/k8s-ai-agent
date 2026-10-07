import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.core import auth
from app.core.config import settings
from app.main import app
from app.services import jobs

EVIDENCE = {"pods": {"healthy": True}, "logs": {}, "events": {}, "deployments": {}, "network": {}}
GOOD = {"Authorization": "Bearer good-token"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(jobs, "run_investigation", lambda kube, tracker: EVIDENCE)
    monkeypatch.setattr(jobs, "analyze", lambda evidence, kube=None: {"root_cause": "x", "confidence": 50})
    monkeypatch.setattr(routes.kubectl, "list_contexts", lambda: {"clusters": ["prod"], "current": "prod", "error": None})
    return TestClient(app)


@pytest.fixture
def auth_on(monkeypatch):
    """Enable auth with a fake InsForge that knows one token."""
    monkeypatch.setattr(settings, "INSFORGE_URL", "https://insforge.test")
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "")
    auth._cache.clear()

    def fake_get(url, headers, timeout):
        request = httpx.Request("GET", url)
        if headers["Authorization"] == "Bearer good-token":
            return httpx.Response(200, json={"user": {"id": "user-1", "email": "a@b.c"}}, request=request)
        return httpx.Response(401, json={"error": "invalid"}, request=request)

    monkeypatch.setattr(auth.httpx, "get", fake_get)


def run_to_completion(client, headers=None, **body):
    """Start an investigation and poll until it finishes. Returns (id, status JSON)."""
    started = client.post("/investigations", json=body, headers=headers or {})
    assert started.status_code == 202, started.text
    investigation_id = started.json()["investigation_id"]
    for _ in range(200):
        status = client.get(f"/investigations/{investigation_id}", headers=headers or {}).json()
        if not status["running"]:
            return investigation_id, status
        time.sleep(0.01)
    raise AssertionError("investigation did not finish")


def test_health_is_public(client, auth_on):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad-token"}, {"Authorization": "Basic x"}])
def test_protected_routes_reject_missing_or_bad_tokens(client, auth_on, headers):
    assert client.post("/investigations", json={}, headers=headers).status_code == 401
    assert client.get("/clusters", headers=headers).status_code == 401
    assert client.get("/investigations/00000000-0000-0000-0000-000000000000", headers=headers).status_code == 401


def test_investigation_runs_in_background_and_returns_result(client, auth_on):
    _, status = run_to_completion(client, GOOD)
    assert status["result"]["diagnosis"]["root_cause"] == "x"
    # Evidence collection is stubbed out here; the AI step is real.
    assert {s["name"]: s["status"] for s in status["steps"]}["AI Reasoning"] == "done"


def test_investigation_is_private_to_owner(client, auth_on, monkeypatch):
    investigation_id, _ = run_to_completion(client, GOOD)
    url = f"/investigations/{investigation_id}"
    assert client.get(url, headers=GOOD).status_code == 200

    # A different signed-in user cannot see it.
    monkeypatch.setattr(auth, "_verify_with_insforge", lambda token: auth.AuthUser(id="user-2"))
    auth._cache.clear()
    assert client.get(url, headers={"Authorization": "Bearer other-token"}).status_code == 404


def test_unknown_context_rejected(client, auth_on):
    assert client.post("/investigations", json={"context": "not-a-cluster"}, headers=GOOD).status_code == 400


def test_per_user_running_limit(client, auth_on, monkeypatch):
    monkeypatch.setattr(jobs.progress, "running_count", lambda owner_id: jobs.MAX_RUNNING_PER_USER)
    assert client.post("/investigations", json={}, headers=GOOD).status_code == 429


def test_crashed_job_finishes_with_error(client, auth_on, monkeypatch):
    def boom(kube, tracker):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(jobs, "run_investigation", boom)
    _, status = run_to_completion(client, GOOD)
    assert status["result"]["status"] == "error"
    assert "RuntimeError" in status["result"]["diagnosis"]["error"]


def test_local_mode_needs_no_token(client, monkeypatch):
    monkeypatch.setattr(settings, "INSFORGE_URL", "")
    _, status = run_to_completion(client)
    assert status["result"]["status"] == "success"


def test_history_written_server_side_with_verified_user(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "admin-key")
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted.update(url=url, row=json[0], auth=headers["Authorization"])
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.history.httpx.post", fake_post)
    investigation_id, status = run_to_completion(client, GOOD, context="prod")

    assert status["result"]["saved"] is True
    assert posted["url"].endswith("/api/database/records/investigations")
    assert posted["auth"] == "Bearer admin-key"
    assert posted["row"]["user_id"] == "user-1"
    assert posted["row"]["id"] == investigation_id
    assert posted["row"]["cluster_context"] == "prod"
