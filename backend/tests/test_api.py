import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.core import auth
from app.core.config import settings
from app.main import app

EVIDENCE = {"pods": {"healthy": True}, "logs": {}, "events": {}, "deployments": {}, "network": {}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(routes, "run_investigation", lambda kube, tracker: EVIDENCE)
    monkeypatch.setattr(routes, "analyze", lambda evidence, kube=None: {"root_cause": "x", "confidence": 50})
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


def body(**extra):
    return {"investigation_id": str(uuid.uuid4()), **extra}


def test_health_is_public(client, auth_on):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad-token"}, {"Authorization": "Basic x"}])
def test_protected_routes_reject_missing_or_bad_tokens(client, auth_on, headers):
    assert client.post("/investigate", json=body(), headers=headers).status_code == 401
    assert client.get("/clusters", headers=headers).status_code == 401


def test_valid_token_can_investigate(client, auth_on):
    response = client.post("/investigate", json=body(), headers={"Authorization": "Bearer good-token"})
    assert response.status_code == 200
    assert response.json()["diagnosis"]["root_cause"] == "x"


def test_progress_is_private_to_owner(client, auth_on, monkeypatch):
    payload = body()
    client.post("/investigate", json=payload, headers={"Authorization": "Bearer good-token"})
    url = f"/investigations/{payload['investigation_id']}/progress"

    assert client.get(url, headers={"Authorization": "Bearer good-token"}).status_code == 200

    # A different signed-in user cannot see it.
    monkeypatch.setattr(auth, "_verify_with_insforge", lambda token: auth.AuthUser(id="user-2"))
    auth._cache.clear()
    assert client.get(url, headers={"Authorization": "Bearer other-token"}).status_code == 404


def test_unknown_context_rejected(client, auth_on):
    response = client.post(
        "/investigate", json=body(context="not-a-cluster"), headers={"Authorization": "Bearer good-token"}
    )
    assert response.status_code == 400


def test_local_mode_needs_no_token(client, monkeypatch):
    monkeypatch.setattr(settings, "INSFORGE_URL", "")
    assert client.post("/investigate", json=body()).status_code == 200


def test_history_written_server_side_with_verified_user(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "INSFORGE_API_KEY", "admin-key")
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted.update(url=url, row=json[0], auth=headers["Authorization"])
        return httpx.Response(201, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.services.history.httpx.post", fake_post)
    payload = body(context="prod")
    response = client.post("/investigate", json=payload, headers={"Authorization": "Bearer good-token"})

    assert response.json()["saved"] is True
    assert posted["url"].endswith("/api/database/records/investigations")
    assert posted["auth"] == "Bearer admin-key"
    assert posted["row"]["user_id"] == "user-1"
    assert posted["row"]["id"] == payload["investigation_id"]
    assert posted["row"]["cluster_context"] == "prod"
