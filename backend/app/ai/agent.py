"""AI Kubernetes agent.

Consumes the investigation evidence, asks the LLM for a diagnosis, and
returns a structured result: root cause, explanation, fix, kubectl
commands, prevention advice, and a confidence score.
"""

import json
from typing import Optional

from loguru import logger

from app.ai.llm_client import LLMError, chat
from app.ai.prompt_builder import SYSTEM_PROMPT, build_user_prompt

# Every diagnosis dict carries these keys, so the API response shape is
# stable even when analysis fails or is skipped.
_EMPTY_DIAGNOSIS = {
    "root_cause": None,
    "explanation": None,
    "fix": None,
    "kubectl_commands": [],
    "prevention": None,
    "confidence": None,
    "confidence_reasoning": None,
    "error": None,
}


def analyze(evidence: dict) -> dict:
    """Turn investigation evidence into a diagnosis.

    Never raises: when the LLM is unavailable or returns something
    unusable, the diagnosis carries an `error` message instead.
    """
    if _cluster_looks_healthy(evidence):
        logger.info("Evidence shows no problems — skipping LLM analysis")
        return {
            **_EMPTY_DIAGNOSIS,
            "root_cause": "No problems detected",
            "explanation": "All pods, deployments, services, and events look healthy.",
            "confidence": 95,
            "confidence_reasoning": "No failure signals present in any evidence section.",
        }

    try:
        reply = chat(SYSTEM_PROMPT, build_user_prompt(evidence))
    except LLMError as exc:
        logger.error("AI analysis unavailable: {}", exc)
        return {**_EMPTY_DIAGNOSIS, "error": str(exc)}

    diagnosis = _parse_diagnosis(reply)
    if diagnosis is None:
        logger.error("LLM reply was not valid diagnosis JSON")
        return {**_EMPTY_DIAGNOSIS, "error": "AI returned a response that could not be parsed"}

    logger.info(
        "Diagnosis: {} (confidence {})", diagnosis.get("root_cause"), diagnosis.get("confidence")
    )
    return diagnosis


def _cluster_looks_healthy(evidence: dict) -> bool:
    """True when every evidence section succeeded and found no problems."""
    pods = evidence.get("pods", {})
    deployments = evidence.get("deployments", {})
    network = evidence.get("network", {})
    events = evidence.get("events", {})
    return (
        pods.get("healthy") is True
        and deployments.get("healthy") is True
        and network.get("healthy") is True
        and events.get("error") is None
        and not events.get("findings")
    )


def _parse_diagnosis(reply: str) -> Optional[dict]:
    """Parse the LLM reply into a diagnosis dict, or None if unusable."""
    text = reply.strip()
    # Some models wrap JSON in ```json fences despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None

    diagnosis = {**_EMPTY_DIAGNOSIS}
    for key in diagnosis:
        if key in raw:
            diagnosis[key] = raw[key]

    # Keep confidence a sane number between 0 and 100.
    confidence = diagnosis.get("confidence")
    if isinstance(confidence, (int, float)):
        diagnosis["confidence"] = max(0, min(100, float(confidence)))
    else:
        diagnosis["confidence"] = None

    if not isinstance(diagnosis.get("kubectl_commands"), list):
        diagnosis["kubectl_commands"] = []

    return diagnosis
