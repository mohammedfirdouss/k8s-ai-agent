"""Claude via the official Anthropic Python SDK.

Implements the `Conversation` interface from `llm_client` in Claude's native
message format:

- The assistant's full `response.content` is appended back unchanged, so
  thinking blocks survive across tool-use turns.
- All tool results for a turn go back in one user message.
- The final answer is constrained to the diagnosis JSON schema with
  structured outputs (`output_config.format`); tool calls are still allowed.
- Cost is computed from the reported token counts and PRICES_PER_MTOK.
"""

import json
import time
from typing import Optional

import anthropic
from loguru import logger

from app.ai.llm_client import LLMError, ToolCall, Turn, Usage
from app.core.config import settings

MAX_TOKENS = 16000
REQUEST_TIMEOUT_SECONDS = 120
# The SDK retries connection errors, 408, 409, 429 and 5xx with backoff.
MAX_RETRIES = 3

# USD per million tokens (input, output), first-party API rates as of
# 2026-11. Haiku 5.5's rate applies to prompts up to 100K tokens, far more
# than an investigation sends. Unknown models report no cost.
PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# Prompt-cache pricing as multiples of the input rate.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


def anthropic_tools(tools: "list[dict]") -> "list[dict]":
    """Convert OpenAI-style function schemas to Claude tool definitions."""
    converted = []
    for tool in tools:
        function = tool["function"]
        converted.append(
            {
                "name": function["name"],
                "description": function["description"],
                "input_schema": {**function["parameters"], "additionalProperties": False},
            }
        )
    return converted


def cost_usd(model: str, usage) -> Optional[float]:
    """Cost of one response from its `usage`, or None for an unpriced model."""
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    input_rate, output_rate = prices
    cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
    total = (
        usage.input_tokens * input_rate
        + cache_write * input_rate * CACHE_WRITE_MULTIPLIER
        + cache_read * input_rate * CACHE_READ_MULTIPLIER
        + usage.output_tokens * output_rate
    )
    return total / 1_000_000


class AnthropicConversation:
    """Conversation with Claude through the Messages API."""

    def __init__(
        self,
        system: str,
        user_prompt: str,
        tools: "Optional[list[dict]]",
        response_schema: Optional[dict],
        usage: Usage,
    ):
        self._client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            max_retries=MAX_RETRIES,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        self._model = settings.ANTHROPIC_MODEL
        self._system = system
        self._messages: "list[dict]" = [{"role": "user", "content": user_prompt}]
        self._tools = anthropic_tools(tools) if tools else None
        self._schema = response_schema
        self._usage = usage

    def send(self) -> Turn:
        output_config: dict = {"effort": settings.ANTHROPIC_EFFORT}
        if self._schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": self._schema}
        params: dict = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": self._system,
            "messages": self._messages,
            "output_config": output_config,
        }
        if self._tools:
            params["tools"] = self._tools
            # A tool loop resends a growing history; cache its prefix. (A
            # single-shot call would only pay the cache-write premium.)
            params["cache_control"] = {"type": "ephemeral"}

        started = time.monotonic()
        try:
            response = self._client.messages.create(**params)
        except anthropic.AuthenticationError:
            raise LLMError("The Claude API rejected the API key. Check ANTHROPIC_API_KEY in backend/.env.")
        except anthropic.PermissionDeniedError:
            raise LLMError(
                "The Claude API key isn't allowed to use this model or feature. "
                "Check the key's workspace permissions and ANTHROPIC_MODEL."
            )
        except anthropic.NotFoundError:
            raise LLMError(
                f"The Claude API doesn't know the model '{self._model}'. Check ANTHROPIC_MODEL in backend/.env."
            )
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc.message).lower():
                raise LLMError(
                    "The Claude API account is out of credits. Top up at https://platform.claude.com."
                )
            raise LLMError(f"The Claude API rejected the request: {exc.message}")
        except anthropic.RateLimitError:
            raise LLMError("The Claude API is rate-limiting requests. Try again shortly.")
        except anthropic.APIStatusError as exc:
            raise LLMError(f"The Claude API returned an error (HTTP {exc.status_code}).")
        except anthropic.APIConnectionError:
            raise LLMError("Could not reach the Claude API.")

        elapsed = time.monotonic() - started
        usage = response.usage
        self._usage.record(
            usage.input_tokens
            + (getattr(usage, "cache_creation_input_tokens", None) or 0)
            + (getattr(usage, "cache_read_input_tokens", None) or 0),
            usage.output_tokens,
            cost_usd(self._model, usage),
            elapsed,
        )
        logger.debug(
            "Claude {} stop_reason={} tokens in/out {}/{}",
            self._model, response.stop_reason, usage.input_tokens, usage.output_tokens,
        )

        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to answer this request.")

        # Keep the full content (thinking, text and tool_use blocks) as is.
        self._messages.append({"role": "assistant", "content": response.content})
        text = "".join(block.text for block in response.content if block.type == "text")
        calls = [
            ToolCall(id=block.id, name=block.name, arguments=json.dumps(block.input))
            for block in response.content
            if block.type == "tool_use"
        ]
        return Turn(text=text, tool_calls=calls)

    def add_tool_results(self, results: "list[tuple[str, str]]") -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call_id, "content": output}
                    for call_id, output in results
                ],
            }
        )

    def add_user_message(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
