"""OpenRouter LLM client.

A thin wrapper around the OpenRouter chat-completions API. The API key
comes from the environment (provided via InsForge) — never hardcoded.
"""

import time
from typing import Optional

import httpx
from loguru import logger

from app.core.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Raised when the LLM cannot produce a response."""


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
    messages: "list[dict]", tools: "Optional[list[dict]]" = None, json_mode: bool = False
) -> dict:
    """Send a multi-turn chat request and return the assistant message dict.

    The message has `content` and, when `tools` were offered and the model
    chose to use them, `tool_calls` (OpenAI format).

    Retries transient failures (network errors, 5xx, rate limits) up to
    MAX_ATTEMPTS times. Raises LLMError when no response can be obtained.
    """
    if not settings.OPENROUTER_API_KEY:
        raise LLMError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env to enable AI analysis."
        )
    if not settings.OPENROUTER_MODEL:
        raise LLMError(
            "OPENROUTER_MODEL is not set. Add a model id (e.g. 'anthropic/claude-sonnet-4.5') "
            "to backend/.env."
        )

    payload: dict = {
        "model": settings.OPENROUTER_MODEL,
        "messages": messages,
        # Low temperature: we want deterministic, factual troubleshooting.
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}

    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
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
            time.sleep(attempt)  # simple backoff: 1s, 2s
            continue

        if response.status_code == 200:
            try:
                return response.json()["choices"][0]["message"]
            except (KeyError, IndexError, TypeError, ValueError):
                # OpenRouter reports some upstream provider failures as a 200
                # with an error body and no choices; treat them as transient.
                last_error = f"no completion in response: {response.text[:200]}"
                logger.warning("LLM attempt {}/{} failed: {}", attempt, MAX_ATTEMPTS, last_error)
                time.sleep(attempt)
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
        time.sleep(attempt)

    raise LLMError(f"LLM request failed after {MAX_ATTEMPTS} attempts ({last_error})")
