import json

import pytest

from app.ai import agent
from app.ai.llm_client import ToolCall, Turn, Usage

BROKEN = {"pods": {"healthy": False}, "logs": {}, "events": {}, "deployments": {}, "network": {}}


def incident(**overrides):
    return {"workload": "Deployment/a", "severity": "high", "root_cause": "a is broken", "confidence": 80, **overrides}


class FakeConversation:
    """Scripted stand-in for an llm_client Conversation.

    Replies are final-answer strings, or OpenAI-style message dicts with
    `tool_calls` (see `tool_call()`). `calls` records, per send(), the latest
    text the model was given: the user prompt, a feedback message, or the
    joined tool outputs.
    """

    def __init__(self, replies, user_prompt, calls):
        self._replies = list(replies)
        self._latest = user_prompt
        self.calls = calls

    def send(self):
        self.calls.append(self._latest)
        reply = self._replies[len(self.calls) - 1]
        if isinstance(reply, str):
            return Turn(text=reply)
        return Turn(
            text=reply.get("content") or "",
            tool_calls=[
                ToolCall(id=c["id"], name=c["function"]["name"], arguments=c["function"]["arguments"])
                for c in reply.get("tool_calls") or []
            ],
        )

    def add_tool_results(self, results):
        self._latest = "\n".join(output for _, output in results)

    def add_user_message(self, text):
        self._latest = text


def fake_replies(monkeypatch, *replies):
    """Script the model's replies; returns what the model was sent per call."""
    calls = []
    monkeypatch.setattr(
        agent,
        "start_conversation",
        lambda system, user_prompt, tools, schema, usage: FakeConversation(replies, user_prompt, calls),
    )
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

    def fake(system, user_prompt, tools, schema, usage):
        seen.update(tools=tools, schema=schema)
        return FakeConversation([json.dumps({"incidents": [incident()]})], user_prompt, [])

    monkeypatch.setattr(agent, "start_conversation", fake)
    agent.analyze(BROKEN)
    assert seen == {"tools": None, "schema": agent.REPLY_SCHEMA}


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


def test_llm_client_retries_200_without_choices(monkeypatch):
    import httpx

    from app.ai import llm_client

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m")
    monkeypatch.setattr(llm_client.time, "sleep", lambda _s: None)
    replies = iter([
        httpx.Response(200, json={"error": {"message": "upstream provider error"}}),
        httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
    ])
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: next(replies))
    assert llm_client.chat("s", "u") == "ok"


def test_llm_client_fails_fast_on_out_of_credits(monkeypatch):
    import httpx

    from app.ai import llm_client

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m")
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json={"error": {"message": "This request requires more credits", "code": 402}})

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    with pytest.raises(llm_client.LLMError, match="out of credits"):
        llm_client.chat("s", "u")
    assert len(calls) == 1


def test_usage_is_accumulated_across_calls(monkeypatch):
    import httpx

    from app.ai import llm_client

    monkeypatch.setattr(settings, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m")
    body = {
        "choices": [{"message": {"content": json.dumps({"incidents": [incident()]})}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": 0.0004},
    }
    monkeypatch.setattr(llm_client.httpx, "post", lambda *a, **k: httpx.Response(200, json=body))
    diagnosis = agent.analyze(BROKEN)
    assert diagnosis["usage"]["calls"] == 1
    assert diagnosis["usage"]["prompt_tokens"] == 1000
    assert diagnosis["usage"]["completion_tokens"] == 200
    assert diagnosis["usage"]["cost_usd"] == 0.0004


def test_reply_schema_matches_incident_model():
    """Structured outputs must cover exactly the fields Incident accepts."""
    from app.models.schemas import Incident

    incident_schema = agent.REPLY_SCHEMA["properties"]["incidents"]["items"]
    assert set(incident_schema["properties"]) == set(Incident.model_fields)
    assert set(incident_schema["required"]) == set(Incident.model_fields)
    assert agent.REPLY_SCHEMA["additionalProperties"] is False
    assert incident_schema["additionalProperties"] is False



@pytest.mark.parametrize("provider, key_setting", [("anthropic", "ANTHROPIC_API_KEY"), ("openrouter", "OPENROUTER_API_KEY")])
def test_missing_key_reports_ai_disabled_instead_of_crashing(monkeypatch, provider, key_setting):
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, key_setting, "")
    diagnosis = agent.analyze(BROKEN)
    assert f"{key_setting} is not set" in diagnosis["error"]
    assert diagnosis["incidents"] == []


@pytest.mark.parametrize("tools, json_mode", [(None, True), ([{"type": "function"}], False)])
def test_openrouter_uses_json_mode_only_without_tools(monkeypatch, tools, json_mode):
    from app.ai import llm_client

    seen = {}

    def fake_chat_messages(messages, tools=None, json_mode=False, usage=None):
        seen["json_mode"] = json_mode
        return {"content": "{}"}

    monkeypatch.setattr(llm_client, "chat_messages", fake_chat_messages)
    llm_client.OpenRouterConversation("sys", "user", tools, Usage()).send()
    assert seen["json_mode"] is json_mode
