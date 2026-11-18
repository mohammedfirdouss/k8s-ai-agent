from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.ai import anthropic_client
from app.ai.anthropic_client import AnthropicConversation, cost_usd
from app.ai.llm_client import LLMError, Usage
from app.ai.tools import TOOL_SCHEMAS
from app.core.config import settings

SCHEMA = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(call_id, name, args):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def response(*blocks, stop_reason="end_turn", input_tokens=1000, output_tokens=200):
    usage = SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_creation_input_tokens=None, cache_read_input_tokens=None,
    )
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage)


@pytest.fixture
def fake_sdk(monkeypatch):
    """Replace the SDK client; returns (requests sent, queue of responses or exceptions)."""
    sent, queue = [], []

    class FakeMessages:
        def create(self, **params):
            # Snapshot the message list as it was at call time.
            sent.append({**params, "messages": list(params["messages"])})
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr(anthropic_client.anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=FakeMessages()))
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(settings, "ANTHROPIC_EFFORT", "medium")
    return sent, queue


def api_error(cls, status, message):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message=message, response=httpx2.Response(status, request=request), body=None)


def test_single_shot_request_shape_and_cost(fake_sdk):
    sent, queue = fake_sdk
    queue.append(response(text_block('{"summary": null, "incidents": []}')))
    usage = Usage()
    turn = AnthropicConversation("SYS", "evidence", None, SCHEMA, usage).send()

    params = sent[0]
    assert params["model"] == "claude-haiku-5-5"
    assert params["system"] == "SYS"
    assert params["messages"] == [{"role": "user", "content": "evidence"}]
    assert params["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert "temperature" not in params and "tools" not in params and "cache_control" not in params
    assert turn.text == '{"summary": null, "incidents": []}' and turn.tool_calls == []
    # 1000 in x $0.10/M + 200 out x $0.50/M
    assert usage.cost_usd == pytest.approx(0.0002)
    assert (usage.calls, usage.prompt_tokens, usage.completion_tokens) == (1, 1000, 200)


def test_tool_loop_keeps_content_and_groups_results(fake_sdk):
    sent, queue = fake_sdk
    thinking = SimpleNamespace(type="thinking", thinking="", signature="sig")
    first = response(thinking, tool_block("t1", "describe", {"kind": "pod"}), tool_block("t2", "logs", {"pod": "p"}),
                     stop_reason="tool_use")
    queue += [first, response(text_block("{}"))]
    conversation = AnthropicConversation("SYS", "evidence", TOOL_SCHEMAS, SCHEMA, Usage())

    turn = conversation.send()
    assert [(c.id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("t1", "describe", '{"kind": "pod"}'), ("t2", "logs", '{"pod": "p"}')]
    conversation.add_tool_results([("t1", "out1"), ("t2", "out2")])
    conversation.send()

    second = sent[1]
    # The assistant turn goes back unchanged, thinking block included.
    assert second["messages"][1] == {"role": "assistant", "content": first.content}
    # Both tool results in one user message.
    assert second["messages"][2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "out1"},
        {"type": "tool_result", "tool_use_id": "t2", "content": "out2"},
    ]}
    tool = next(t for t in second["tools"] if t["name"] == "describe")
    assert tool["input_schema"]["additionalProperties"] is False and "kind" in tool["input_schema"]["properties"]
    assert second["cache_control"] == {"type": "ephemeral"}


def test_refusal_raises(fake_sdk):
    _, queue = fake_sdk
    queue.append(response(stop_reason="refusal"))
    with pytest.raises(LLMError, match="declined"):
        AnthropicConversation("SYS", "e", None, SCHEMA, Usage()).send()


@pytest.mark.parametrize("error, message", [
    (api_error(anthropic.BadRequestError, 400, "Your credit balance is too low to access the Anthropic API."), "out of credits"),
    (api_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "rejected the API key"),
    (api_error(anthropic.BadRequestError, 400, "messages: bad shape"), "rejected the request"),
    (api_error(anthropic.InternalServerError, 500, "overloaded"), "HTTP 500"),
])
def test_errors_become_readable_llm_errors(fake_sdk, error, message):
    _, queue = fake_sdk
    queue.append(error)
    with pytest.raises(LLMError, match=message):
        AnthropicConversation("SYS", "e", None, SCHEMA, Usage()).send()


def test_cost_includes_cache_and_skips_unpriced_models():
    usage = SimpleNamespace(input_tokens=100, output_tokens=0,
                            cache_creation_input_tokens=1000, cache_read_input_tokens=10000)
    # (100 + 1000x1.25 + 10000x0.1) x $0.10/M
    assert cost_usd("claude-haiku-5-5", usage) == pytest.approx(2350 * 0.10 / 1_000_000)
    assert cost_usd("some-future-model", usage) is None
