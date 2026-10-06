"""Pydantic schemas used by the API."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for the /health endpoint."""

    status: str
    service: str


class InvestigationEvidence(BaseModel):
    """Structured Kubernetes evidence gathered by the investigation layer.

    Each section is a free-form dict produced by one inspector; the
    exact shape is documented in `app.kubernetes.inspectors`.
    """

    pods: dict
    logs: dict
    events: dict
    deployments: dict
    network: dict


class Diagnosis(BaseModel):
    """AI-generated diagnosis of the cluster's problems.

    `error` is set (and the other fields empty) when AI analysis could
    not run — for example when no OpenRouter API key is configured.
    """

    root_cause: Optional[str] = None
    explanation: Optional[str] = None
    fix: Optional[str] = None
    kubectl_commands: "list[str]" = []
    prevention: Optional[str] = None
    confidence: Optional[float] = None
    confidence_reasoning: Optional[str] = None
    error: Optional[str] = None


class InvestigateRequest(BaseModel):
    """Request body for /investigate."""

    # Client-generated id, so the frontend can poll this investigation's
    # progress while the request is still running. Also the history row id.
    investigation_id: UUID
    # Kubeconfig context (cluster) to investigate; default context when omitted.
    context: Optional[str] = None


class ClustersResponse(BaseModel):
    """Response body for the /clusters endpoint."""

    clusters: "list[str]"
    current: Optional[str] = None
    error: Optional[str] = None


class InvestigateResponse(BaseModel):
    """Response body for the /investigate endpoint."""

    investigation_id: UUID
    status: str
    diagnosis: Diagnosis
    investigation: InvestigationEvidence
    # True when the investigation was saved to the user's history.
    saved: bool = False
    # Beginner-friendly message set when the cluster itself was unreachable.
    cluster_error: Optional[str] = None
