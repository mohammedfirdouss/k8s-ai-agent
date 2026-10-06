import json

from app.ai import agent

BROKEN = {"pods": {"healthy": False}, "logs": {}, "events": {}, "deployments": {}, "network": {}}


def incident(**overrides):
    return {"workload": "Deployment/a", "severity": "high", "root_cause": "a is broken", "confidence": 80, **overrides}


def fake_replies(monkeypatch, *replies):
    calls = []

    def fake_chat(system, user, json_mode=True):
        calls.append(user)
        return replies[len(calls) - 1]

    monkeypatch.setattr(agent, "chat", fake_chat)
    return calls


def test_incidents_sorted_by_severity_and_headline_uses_summary(monkeypatch):
    reply = {
        "summary": "Two problems",
        "incidents": [incident(severity="low", root_cause="minor"), incident(severity="Critical", root_cause="down", confidence=95)],
    }
    fake_replies(monkeypatch, json.dumps(reply))
    diagnosis = agent.analyze(BROKEN)

    assert [i["severity"] for i in diagnosis["incidents"]] == ["critical", "low"]
    assert diagnosis["root_cause"] == "Two problems"
    assert diagnosis["confidence"] == 80  # least certain incident
    assert diagnosis["error"] is None


def test_single_incident_headline_is_its_root_cause(monkeypatch):
    fake_replies(monkeypatch, json.dumps({"incidents": [incident(confidence=150)]}))
    diagnosis = agent.analyze(BROKEN)
    assert diagnosis["root_cause"] == "a is broken"
    assert diagnosis["incidents"][0]["confidence"] == 100  # clamped


def test_invalid_reply_is_retried_with_the_error(monkeypatch):
    calls = fake_replies(monkeypatch, '{"summary": "no incidents key"}', "```json\n" + json.dumps({"incidents": [incident()]}) + "\n```")
    diagnosis = agent.analyze(BROKEN)
    assert len(calls) == 2
    assert "previous reply was invalid" in calls[1] and "incidents" in calls[1]
    assert diagnosis["root_cause"] == "a is broken"


def test_two_invalid_replies_give_an_error(monkeypatch):
    fake_replies(monkeypatch, "not json", "still not json")
    assert agent.analyze(BROKEN)["error"] == "AI returned a response that could not be parsed"


def test_empty_incident_list_means_healthy(monkeypatch):
    fake_replies(monkeypatch, json.dumps({"summary": "fine", "incidents": []}))
    assert agent.analyze(BROKEN)["root_cause"] == agent.HEALTHY_ROOT_CAUSE


def test_missed_flagged_problem_triggers_retry_naming_it(monkeypatch):
    evidence = {
        **BROKEN,
        "pods": {"healthy": False, "problematic_pods": [
            {"name": "a-1", "namespace": "ns", "workload": "Deployment/a", "status": "CrashLoopBackOff"}]},
        "network": {"healthy": False, "issues": [
            {"service": "orders", "namespace": "ns", "problem": "no ready endpoints"}]},
    }
    first = {"incidents": [incident()]}
    second = {"incidents": [incident(), incident(workload="Service/orders", root_cause="selector matches nothing")]}
    calls = fake_replies(monkeypatch, json.dumps(first), json.dumps(second))

    diagnosis = agent.analyze(evidence)
    assert len(calls) == 2
    assert "Service/orders in ns has no ready endpoints" in calls[1]
    assert len(diagnosis["incidents"]) == 2


def test_keeps_more_complete_answer_when_retry_is_worse(monkeypatch):
    evidence = {**BROKEN, "network": {"issues": [
        {"service": "orders", "namespace": "ns", "problem": "no ready endpoints"},
        {"service": "billing", "namespace": "ns", "problem": "no ready endpoints"}]}}
    first = {"incidents": [incident(workload="Service/orders")]}
    second = {"incidents": []}
    fake_replies(monkeypatch, json.dumps(first), json.dumps(second))
    assert agent.analyze(evidence)["incidents"][0]["workload"] == "Service/orders"
