"""OpenRouter LLM client.

A thin wrapper around the OpenRouter chat-completions API. The API key
comes from the environment (provided via InsForge) — never hardcoded.
"""

import time

import httpx
from loguru import logger

from app.core.config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3


class LLMError(Exception):
    """Raised when the LLM cannot produce a response."""


def chat(system_prompt: str, user_prompt: str) -> str:
    """Send one chat request to OpenRouter and return the reply text.

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

    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # Low temperature: we want deterministic, factual troubleshooting.
        "temperature": 0.2,
    }
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
                return response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError):
                raise LLMError("OpenRouter returned an unexpected response format")

        # 429 (rate limit) and 5xx are worth retrying; 4xx are not.
        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        logger.warning("LLM attempt {}/{} failed: {}", attempt, MAX_ATTEMPTS, last_error)
        if response.status_code != 429 and response.status_code < 500:
            break
        time.sleep(attempt)

    raise LLMError(f"LLM request failed after {MAX_ATTEMPTS} attempts ({last_error})")
