"""Inspector checks against recorded eval fixtures (no cluster, no LLM).

These pin down that the evidence for each scenario contains the signal a
correct diagnosis needs. If one fails after an inspector change, the
inspectors stopped surfacing that signal. A MissingFixture error means the
inspectors now run a new kubectl command: re-record the fixtures.
"""

import json

import pytest

from app.services.investigation import run_investigation
from app.services.progress import ProgressTracker
from evals.recording import ReplayKubectl, fixture_path
from evals.scenarios import SCENARIOS
from evals.scoring import matches, score


def evidence_for(scenario_id: str) -> dict:
    return run_investigation(ReplayKubectl(fixture_path(scenario_id)), ProgressTracker("test"))


def problem_pods(evidence: dict) -> "dict[str, str]":
    return {p["name"].rsplit("-", 2)[0]: p["status"] for p in evidence["pods"]["problematic_pods"]}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_has_a_fixture(scenario):
    assert fixture_path(scenario.id).exists()


def test_crashloop_evidence():
    evidence = evidence_for("crashloop")
    assert problem_pods(evidence) == {"payment-service": "CrashLoopBackOff"}
    lines = [line for pod in evidence["logs"]["logs"].values() for line in pod["lines"]]
    assert any("DATABASE_URL" in line for line in lines)


def test_imagepull_evidence():
    evidence = evidence_for("imagepull")
    assert problem_pods(evidence) == {"web-frontend": "ImagePullBackOff"}
    messages = " ".join(e["message"] for e in evidence["events"]["findings"])
    assert "this-tag-does-not-exist" in messages


def test_oomkilled_evidence():
    evidence = evidence_for("oomkilled")
    assert problem_pods(evidence).get("analytics-worker") in ("OOMKilled", "CrashLoopBackOff")


def test_selector_evidence():
    evidence = evidence_for("selector")
    issues = evidence["network"]["issues"]
    assert [(i["service"], i["selector"]) for i in issues] == [("orders-service", {"app": "orders-api"})]


def test_multi_evidence_has_all_four_failures():
    evidence = evidence_for("multi")
    assert set(problem_pods(evidence)) >= {"payment-service", "web-frontend", "analytics-worker"}
    assert any(i["service"] == "orders-service" for i in evidence["network"]["issues"])


# --- scoring ---------------------------------------------------------------


def test_matches_requires_every_group():
    assert matches("Missing DATABASE_URL", [["database_url"], ["missing", "unset"]])
    assert not matches("DATABASE_URL is fine", [["database_url"], ["missing", "unset"]])


def test_score_passes_a_correct_diagnosis_and_fails_a_generic_one():
    crashloop = next(s for s in SCENARIOS if s.id == "crashloop")
    good = {
        "root_cause": "payment-service crashes because DATABASE_URL is not set",
        "fix": "Add DATABASE_URL to the deployment env from a Secret",
        "kubectl_commands": ["kubectl set env deployment/payment-service DATABASE_URL=..."],
    }
    generic = {"root_cause": "A pod is crash looping", "fix": "Check the logs", "kubectl_commands": []}
    assert score(crashloop, good).passed
    assert not score(crashloop, generic).passed
    assert not score(crashloop, {**good, "error": "LLM unavailable"}).passed


def test_fixtures_are_valid_json():
    for scenario in SCENARIOS:
        assert isinstance(json.loads(fixture_path(scenario.id).read_text()), dict)


def test_readiness_evidence():
    evidence = evidence_for("readiness")
    assert problem_pods(evidence) == {"inventory-api": "NotReady"}
    messages = " ".join(e["message"] for e in evidence["events"]["findings"])
    assert "Readiness probe failed" in messages and "404" in messages


def test_pending_evidence():
    evidence = evidence_for("pending")
    assert problem_pods(evidence) == {"report-generator": "Pending"}
    messages = " ".join(e["message"] for e in evidence["events"]["findings"])
    assert "Insufficient cpu" in messages


def test_configmap_evidence():
    evidence = evidence_for("configmap")
    assert problem_pods(evidence) == {"notification-service": "CreateContainerConfigError"}
    pod = evidence["pods"]["problematic_pods"][0]
    assert 'configmap "notification-config" not found' in pod["containers"][0]["waiting_message"]


def test_liveness_evidence():
    evidence = evidence_for("liveness")
    assert set(problem_pods(evidence)) == {"search-service"}
    messages = " ".join(e["message"] for e in evidence["events"]["findings"])
    assert "Liveness probe failed" in messages and "8080" in messages


def test_silent_crash_evidence_has_no_logs():
    evidence = evidence_for("silent-crash")
    assert set(problem_pods(evidence)) == {"legacy-batch"}
    assert all(not pod["lines"] for pod in evidence["logs"]["logs"].values())


def test_healthy_cluster_needs_no_llm():
    from app.ai.agent import _cluster_looks_healthy

    evidence = evidence_for("healthy")
    assert _cluster_looks_healthy(evidence), (evidence["pods"], evidence["events"]["findings"])
