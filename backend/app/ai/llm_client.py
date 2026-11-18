"""LLM client: one conversation interface over two providers.

The agent loop talks to a `Conversation`: send a turn, get back text and/or
tool calls, add tool results or a follow-up message, repeat.
`start_conversation()` picks the provider from LLM_PROVIDER:

- "openrouter": the OpenRouter chat-completions API (any model it routes to)
- "anthropic": Claude through the official Anthropic SDK (see
  `anthropic_client.py`)

API keys come from the environment / backend/.env — never hardcoded.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

import httpx
from loguru import logger

from app.core.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 4
# Exponential backoff between attempts: 2s, 4s, 8s (capped by Retry-After when given).
BACKOFF_BASE_SECONDS = 2
MAX_BACKOFF_SECONDS = 20


class LLMError(Exception):
    """Raised when the LLM cannot produce a response."""


@dataclass
class ToolCall:
    """One tool call the model asked for. `arguments` is a JSON string."""

    id: str
    name: str
    arguments: str


@dataclass
class Turn:
    """One model reply: final text, or tool calls to run first."""

    text: str = ""
    tool_calls: "list[ToolCall]" = field(default_factory=list)


@dataclass
class Usage:
    """LLM usage accumulated across the calls of one investigation."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # None when the provider gives no cost (and it can't be computed).
    cost_usd: Optional[float] = None
    seconds: float = 0.0

    def record(
        self, prompt_tokens: int, completion_tokens: int, cost_usd: Optional[float], seconds: float
    ) -> None:
        """Add one successful call."""
        self.calls += 1
        self.seconds += seconds
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        if cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + cost_usd

    def add(self, response_json: dict, seconds: float) -> None:
        """Add one OpenRouter call from its response body."""
        usage = response_json.get("usage") or {}
        cost = usage.get("cost")
        self.record(
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
            None if cost is None else float(cost),
            seconds,
        )

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": None if self.cost_usd is None else round(self.cost_usd, 6),
            "seconds": round(self.seconds, 2),
        }


class Conversation(Protocol):
    """A multi-turn exchange with the model, in the provider's own format."""

    def send(self) -> Turn:
        """Get the model's next turn (and record it in the history). Raises LLMError."""

    def add_tool_results(self, results: "list[tuple[str, str]]") -> None:
        """Answer the last turn's tool calls: (tool call id, output) pairs."""

    def add_user_message(self, text: str) -> None:
        """Add a follow-up message (e.g. feedback on an invalid answer)."""


def start_conversation(
    system: str,
    user_prompt: str,
    tools: "Optional[list[dict]]",
    response_schema: Optional[dict],
    usage: Usage,
) -> Conversation:
    """Begin a conversation with the configured provider.

    `tools` are OpenAI-style function schemas (`app.ai.tools.TOOL_SCHEMAS`).
    `response_schema` is the JSON schema the final answer must follow; Claude
    enforces it with structured outputs, OpenRouter gets JSON mode instead.
    """
    problem = configuration_problem()
    if problem:
        raise LLMError(problem)
    if settings.LLM_PROVIDER == "anthropic":
        from app.ai.anthropic_client import AnthropicConversation

        return AnthropicConversation(system, user_prompt, tools, response_schema, usage)
    if settings.LLM_PROVIDER == "openrouter":
        return OpenRouterConversation(system, user_prompt, tools, usage)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Use 'anthropic' or 'openrouter'.")


def model_label() -> str:
    """Provider and model in use, for logs and eval reports."""
    if settings.LLM_PROVIDER == "anthropic":
        return f"anthropic/{settings.ANTHROPIC_MODEL}"
    return f"openrouter/{settings.OPENROUTER_MODEL}"


def configuration_problem() -> Optional[str]:
    """Why the configured provider can't run, or None when it can."""
    if settings.LLM_PROVIDER == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            return (
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable AI analysis "
                "(or set LLM_PROVIDER=openrouter to use OpenRouter)."
            )
        return None
    if settings.LLM_PROVIDER == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            return "OPENROUTER_API_KEY is not set. Add it to backend/.env to enable AI analysis."
        if not settings.OPENROUTER_MODEL:
            return (
                "OPENROUTER_MODEL is not set. Add a model id (e.g. 'deepseek/deepseek-chat') "
                "to backend/.env."
            )
        return None
    return f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Use 'anthropic' or 'openrouter'."


class OpenRouterConversation:
    """Conversation over the OpenRouter chat-completions API (OpenAI format)."""

    def __init__(self, system: str, user_prompt: str, tools: "Optional[list[dict]]", usage: Usage):
        self._messages: "list[dict]" = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        self._tools = tools
        self._usage = usage

    def send(self) -> Turn:
        # JSON mode and tool calling don't mix on every provider.
        message = chat_messages(
            self._messages, tools=self._tools, json_mode=self._tools is None, usage=self._usage
        )
        content = message.get("content") or ""
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            self._messages.append({"role": "assistant", "content": content, "tool_calls": raw_calls})
        else:
            self._messages.append({"role": "assistant", "content": content})
        calls = [
            ToolCall(
                id=call.get("id", ""),
                name=call.get("function", {}).get("name", ""),
                arguments=call.get("function", {}).get("arguments", ""),
            )
            for call in raw_calls
        ]
        return Turn(text=content, tool_calls=calls)

    def add_tool_results(self, results: "list[tuple[str, str]]") -> None:
        for call_id, output in results:
            self._messages.append({"role": "tool", "tool_call_id": call_id, "content": output})

    def add_user_message(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})


def chat(system_prompt: str, user_prompt: str, json_mode: bool = True) -> str:
    """Send one single-turn chat request and return the reply text.

    With `json_mode`, asks the model for a JSON object (OpenRouter
    `response_format`); if the routed provider rejects that parameter, the
    request is retried without it.
    """
    message = chat_messages(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        json_mode=json_mode,
    )
    return message.get("content") or ""


def chat_messages(
    messages: "list[dict]",
    tools: "Optional[list[dict]]" = None,
    json_mode: bool = False,
    usage: Optional[Usage] = None,
) -> dict:
    """Send a multi-turn chat request and return the assistant message dict.

    The message has `content` and, when `tools` were offered and the model
    chose to use them, `tool_calls` (OpenAI format). Token and cost usage of
    a successful call is added to `usage` when given.

    Retries transient failures (network errors, 5xx, rate limits) up to
    MAX_ATTEMPTS times. Raises LLMError when no response can be obtained.
    """
    if not settings.OPENROUTER_API_KEY:
        raise LLMError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env to enable AI analysis."
        )
    if not settings.OPENROUTER_MODEL:
        raise LLMError(
            "OPENROUTER_MODEL is not set. Add a model id (e.g. 'deepseek/deepseek-chat') "
            "to backend/.env."
        )

    payload: dict = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        # Low temperature: we want deterministic, factual troubleshooting.
        "temperature": 0.2,
        # Ask OpenRouter to report token counts and cost.
        "usage": {"include": True},
    }
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}

    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = httpx.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            last_error = f"network error: {exc}"
            logger.warning("LLM attempt {}/{} failed: {}", attempt, MAX_ATTEMPTS, last_error)
            _backoff(attempt)
            continue

        account_problem = _account_problem(response)
        if account_problem:
            raise LLMError(account_problem)

        if response.status_code == 200:
            try:
                body = response.json()
                message = body["choices"][0]["message"]
                if usage is not None:
                    usage.add(body, time.monotonic() - started)
                return message
            except (KeyError, IndexError, TypeError, ValueError):
                # OpenRouter reports some upstream provider failures as a 200
                # with an error body and no choices; treat them as transient.
                last_error = f"no completion in response: {response.text[:200]}"
                logger.warning("LLM attempt {}/{} failed: {}", attempt, MAX_ATTEMPTS, last_error)
                _backoff(attempt)
                continue

        if response.status_code == 400 and "response_format" in payload and "response_format" in response.text:
            logger.warning("Model rejected JSON mode; retrying without response_format")
            del payload["response_format"]
            continue

        # 429 (rate limit) and 5xx are worth retrying; 4xx are not.
        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        logger.warning("LLM attempt {}/{} failed: {}", attempt, MAX_ATTEMPTS, last_error)
        if response.status_code != 429 and response.status_code < 500:
            break
        _backoff(attempt, response.headers.get("retry-after"))

    raise LLMError(f"LLM request failed after {MAX_ATTEMPTS} attempts ({last_error})")


def _backoff(attempt: int, retry_after: Optional[str] = None) -> None:
    """Sleep before the next attempt; skipped after the last one."""
    if attempt >= MAX_ATTEMPTS:
        return
    delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
    if retry_after and retry_after.isdigit():
        delay = int(retry_after)
    time.sleep(min(delay, MAX_BACKOFF_SECONDS))


def _account_problem(response: httpx.Response) -> Optional[str]:
    """A readable message for errors no retry can fix (credits, key), else None.

    OpenRouter reports these either as the HTTP status or, on a 200, as an
    error code in the body.
    """
    code = response.status_code
    try:
        error = response.json().get("error") or {}
        code = int(error.get("code") or code) if isinstance(error, dict) else code
    except (ValueError, AttributeError, TypeError):
        pass
    if code == 402:
        return "The AI provider account is out of credits. Top up at https://openrouter.ai/settings/credits."
    if code in (401, 403):
        return "The AI provider rejected the API key. Check OPENROUTER_API_KEY in backend/.env."
    return None
