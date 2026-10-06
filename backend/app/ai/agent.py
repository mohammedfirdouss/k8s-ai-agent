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
    flagged = _flagged_problems(evidence)
    best: Optional[_LLMReply] = None
    feedback = None
    # Up to one retry, feeding back what was wrong: a malformed reply, or
    # problems the inspectors flagged that no incident covers.
    for attempt in (1, 2):
        prompt = user_prompt + (f"\n\n{feedback}" if feedback else "")
        try:
            reply = chat(SYSTEM_PROMPT, prompt)
        except LLMError as exc:
            if best is not None:
                break  # keep the incomplete-but-valid first answer
            logger.error("AI analysis unavailable: {}", exc)
            return Diagnosis(error=str(exc)).model_dump()

        parsed, reply_error = _parse_reply(reply)
        if parsed is None:
            logger.warning("LLM reply attempt {} was not a valid diagnosis: {}", attempt, reply_error)
            feedback = (
                f"Your previous reply was invalid ({reply_error}). "
                "Respond with ONLY the JSON object in the required shape."
            )
            continue

        missing = _uncovered(flagged, parsed)
        if best is None or len(missing) < len(_uncovered(flagged, best)):
            best = parsed
        if not missing:
            break
        logger.warning("LLM reply attempt {} missed flagged problems: {}", attempt, missing)
        feedback = (
            "Your previous reply did not include an incident for these problems found in "
            "the evidence: " + "; ".join(missing) + ". Respond again with the full JSON "
            "object, with one incident for every independent problem."
        )

    if best is None:
        return Diagnosis(error="AI returned a response that could not be parsed").model_dump()
    diagnosis = _to_diagnosis(best)
    logger.info("Diagnosis: {} incident(s) — {}", len(diagnosis.incidents), diagnosis.root_cause)
    return diagnosis.model_dump()


def _flagged_problems(evidence: dict) -> "dict[str, str]":
    """Problems the inspectors flagged deterministically: name -> description.

    Every one of these must be covered by some incident; the name is what an
    incident has to mention.
    """
    flagged: "dict[str, str]" = {}
    for pod in evidence.get("pods", {}).get("problematic_pods", []):
        workload = pod.get("workload") or f'Pod/{pod["name"]}'
        name = workload.split("/", 1)[-1]
        flagged.setdefault(name, f'{workload} in {pod["namespace"]} is {pod["status"]}')
    for deployment in evidence.get("deployments", {}).get("unhealthy_deployments", []):
        flagged.setdefault(
            deployment["name"], f'Deployment/{deployment["name"]} in {deployment["namespace"]} is unavailable'
        )
    for issue in evidence.get("network", {}).get("issues", []):
        flagged.setdefault(
            issue["service"], f'Service/{issue["service"]} in {issue["namespace"]} has {issue["problem"]}'
        )
    return flagged


def _uncovered(flagged: "dict[str, str]", reply: _LLMReply) -> "list[str]":
    """Descriptions of flagged problems that no incident mentions."""
    text = " ".join(
        " ".join(filter(None, [i.workload, i.root_cause, i.explanation])) for i in reply.incidents
    ).lower()
    return [description for name, description in flagged.items() if name.lower() not in text]


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
