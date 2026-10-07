import json

from app.ai import agent

BROKEN = {"pods": {"healthy": False}, "logs": {}, "events": {}, "deployments": {}, "network": {}}


def incident(**overrides):
    return {"workload": "Deployment/a", "severity": "high", "root_cause": "a is broken", "confidence": 80, **overrides}


def fake_replies(monkeypatch, *replies):
    """Script the model's replies. Strings are final answers; dicts are raw messages.

    Returns the list of last-message contents the model was sent per call.
    """
    calls = []

    def fake_chat_messages(messages, tools=None, json_mode=False):
        calls.append(messages[-1]["content"])
        reply = replies[len(calls) - 1]
        return reply if isinstance(reply, dict) else {"content": reply}

    monkeypatch.setattr(agent, "chat_messages", fake_chat_messages)
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


# --- tool use ----------------------------------------------------------------

from app.ai import tools
from app.core.config import settings
from app.kubernetes.kubectl import KubectlResult


class FakeKubectl:
    def __init__(self):
        self.commands = []

    def run(self, args):
        self.commands.append(args)
        return KubectlResult(success=True, stdout="command: [sh, -c, exit 1]\nDB_PASSWORD=hunter2")


def tool_call(name, arguments, call_id="c1"):
    return {"content": "", "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}


def test_agent_runs_tools_then_answers(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MAX_TOOL_CALLS", 3)
    kube = FakeKubectl()
    calls = fake_replies(
        monkeypatch,
        tool_call("get_yaml", {"kind": "pod", "name": "legacy-batch-1", "namespace": "ns"}),
        json.dumps({"incidents": [incident(root_cause="the container command exits 1")]}),
    )
    diagnosis = agent.analyze(BROKEN, kube)

    assert kube.commands == [["get", "pod", "legacy-batch-1", "-n", "ns", "-o", "yaml"]]
    assert "hunter2" not in calls[1] and "exit 1" in calls[1]  # tool output, redacted
    assert diagnosis["commands_run"] == ["kubectl get pod legacy-batch-1 -n ns -o yaml"]
    assert diagnosis["root_cause"] == "the container command exits 1"


def test_tool_budget_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MAX_TOOL_CALLS", 1)
    kube = FakeKubectl()
    args = {"kind": "pod", "name": "a", "namespace": "ns"}
    calls = fake_replies(
        monkeypatch,
        tool_call("describe", args),
        tool_call("describe", args, call_id="c2"),
        json.dumps({"incidents": [incident()]}),
    )
    agent.analyze(BROKEN, kube)
    assert len(kube.commands) == 1
    assert "budget exhausted" in calls[2]


def test_no_tools_without_kubectl(monkeypatch):
    seen = {}

    def fake(messages, tools=None, json_mode=False):
        seen.update(tools=tools, json_mode=json_mode)
        return {"content": json.dumps({"incidents": [incident()]})}

    monkeypatch.setattr(agent, "chat_messages", fake)
    agent.analyze(BROKEN)
    assert seen == {"tools": None, "json_mode": True}


def test_tool_arguments_cannot_inject_flags_or_read_secrets():
    for name, args in [
        ("describe", {"kind": "secret", "name": "db", "namespace": "ns"}),
        ("describe", {"kind": "pod", "name": "--all-namespaces", "namespace": "ns"}),
        ("logs", {"pod": "a", "namespace": "ns; rm -rf /"}),
        ("get_yaml", {"kind": "pod", "name": "a"}),  # missing namespace
        ("exec", {"pod": "a"}),
    ]:
        output, command = tools.run_tool(FakeKubectl(), name, json.dumps(args))
        assert command is None and output.startswith("Invalid tool call"), (name, args)
