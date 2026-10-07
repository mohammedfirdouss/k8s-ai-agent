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

    pods: dict = {}
    logs: dict = {}
    events: dict = {}
    deployments: dict = {}
    network: dict = {}


class Incident(BaseModel):
    """One independent problem found in the cluster."""

    # Affected controller or object, e.g. "Deployment/payment-service".
    workload: Optional[str] = None
    namespace: Optional[str] = None
    # critical | high | medium | low
    severity: str = "medium"
    root_cause: str
    explanation: Optional[str] = None
    fix: Optional[str] = None
    kubectl_commands: "list[str]" = []
    prevention: Optional[str] = None
    confidence: Optional[float] = None
    confidence_reasoning: Optional[str] = None
    # Specific evidence lines the diagnosis rests on.
    evidence: "list[str]" = []


class Diagnosis(BaseModel):
    """AI-generated diagnosis of the cluster's problems.

    `incidents` lists each independent problem, most severe first.
    `root_cause` and `confidence` are a one-line headline (used for
    history). `error` is set, and the rest empty, when AI analysis could
    not run — for example when no OpenRouter API key is configured.
    """

    summary: Optional[str] = None
    incidents: "list[Incident]" = []
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    error: Optional[str] = None
    # Extra read-only kubectl commands the agent chose to run.
    commands_run: "list[str]" = []


class InvestigateRequest(BaseModel):
    """Request body for POST /investigations."""

    # Kubeconfig context (cluster) to investigate; default context when omitted.
    context: Optional[str] = None


class InvestigationStarted(BaseModel):
    """Response body for POST /investigations."""

    investigation_id: UUID


class ProgressStep(BaseModel):
    name: str
    # pending | running | done
    status: str


class ClustersResponse(BaseModel):
    """Response body for the /clusters endpoint."""

    clusters: "list[str]"
    current: Optional[str] = None
    error: Optional[str] = None


class InvestigateResponse(BaseModel):
    """The result of a finished investigation."""

    investigation_id: UUID
    status: str
    diagnosis: Diagnosis
    investigation: InvestigationEvidence
    # True when the investigation was saved to the user's history.
    saved: bool = False
    # Beginner-friendly message set when the cluster itself was unreachable.
    cluster_error: Optional[str] = None


class InvestigationStatus(BaseModel):
    """Response body for GET /investigations/{id}: progress, then the result."""

    investigation_id: UUID
    running: bool
    steps: "list[ProgressStep]"
    # Set once the investigation has finished.
    result: Optional[InvestigateResponse] = None
