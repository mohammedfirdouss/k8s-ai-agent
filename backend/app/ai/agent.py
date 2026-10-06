"""AI Kubernetes agent.

Consumes the investigation evidence, asks the LLM for a diagnosis, and
returns a structured result: a list of independent incidents (each with
root cause, explanation, fix, kubectl commands, prevention, confidence and
supporting evidence) plus a one-line headline.
"""

import json
from typing import Optional

from loguru import logger
from pydantic import BaseModel, ValidationError

from app.ai.llm_client import LLMError, chat
from app.ai.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from app.models.schemas import Diagnosis, Incident

HEALTHY_ROOT_CAUSE = "No problems detected"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class _LLMReply(BaseModel):
    """The JSON shape the system prompt asks the model for."""

    summary: Optional[str] = None
    incidents: "list[Incident]"


def analyze(evidence: dict) -> dict:
    """Turn investigation evidence into a diagnosis dict (see `Diagnosis`).

    Never raises: when the LLM is unavailable or returns something
    unusable, the diagnosis carries an `error` message instead.
    """
    if _cluster_looks_healthy(evidence):
        logger.info("Evidence shows no problems — skipping LLM analysis")
        return Diagnosis(
            summary="All pods, deployments, services, and events look healthy.",
            root_cause=HEALTHY_ROOT_CAUSE,
            confidence=95,
        ).model_dump()

    user_prompt = build_user_prompt(evidence)
    reply_error = None
    # One retry: a malformed reply is sent back with the validation error.
    for attempt in (1, 2):
        prompt = user_prompt
        if reply_error:
            prompt += (
                f"\n\nYour previous reply was invalid ({reply_error}). "
                "Respond with ONLY the JSON object in the required shape."
            )
        try:
            reply = chat(SYSTEM_PROMPT, prompt)
        except LLMError as exc:
            logger.error("AI analysis unavailable: {}", exc)
            return Diagnosis(error=str(exc)).model_dump()

        parsed, reply_error = _parse_reply(reply)
        if parsed is not None:
            diagnosis = _to_diagnosis(parsed)
            logger.info(
                "Diagnosis: {} incident(s) — {}", len(diagnosis.incidents), diagnosis.root_cause
            )
            return diagnosis.model_dump()
        logger.warning("LLM reply attempt {} was not a valid diagnosis: {}", attempt, reply_error)

    return Diagnosis(error="AI returned a response that could not be parsed").model_dump()


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


def _parse_reply(reply: str) -> "tuple[Optional[_LLMReply], Optional[str]]":
    """Parse and validate the LLM reply. Returns (reply, None) or (None, error)."""
    text = reply.strip()
    # Some models wrap JSON in ```json fences despite instructions.
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:]
    try:
        return _LLMReply.model_validate(json.loads(text)), None
    except json.JSONDecodeError as exc:
        return None, f"not valid JSON: {exc.msg}"
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return None, f"{location}: {first['msg']}"


def _to_diagnosis(reply: _LLMReply) -> Diagnosis:
    """Normalize incidents and derive the headline."""
    incidents = []
    for incident in reply.incidents:
        severity = incident.severity.lower().strip()
        confidence = incident.confidence
        incidents.append(
            incident.model_copy(
                update={
                    "severity": severity if severity in SEVERITY_ORDER else "medium",
                    "confidence": None if confidence is None else max(0.0, min(100.0, confidence)),
                }
            )
        )
    incidents.sort(key=lambda i: SEVERITY_ORDER[i.severity])

    if not incidents:
        return Diagnosis(summary=reply.summary, root_cause=HEALTHY_ROOT_CAUSE, confidence=None)

    if len(incidents) == 1:
        headline = incidents[0].root_cause
    else:
        headline = reply.summary or f"{len(incidents)} issues: " + "; ".join(i.root_cause for i in incidents)
    return Diagnosis(
        summary=reply.summary,
        incidents=incidents,
        root_cause=headline,
        # The headline is only as certain as its least certain incident.
        confidence=min((i.confidence for i in incidents if i.confidence is not None), default=None),
    )
