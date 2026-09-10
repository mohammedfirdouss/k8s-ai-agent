"""Pydantic schemas used by the API."""

from typing import Optional

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


class InvestigateResponse(BaseModel):
    """Response body for the /investigate endpoint."""

    status: str
    investigation: InvestigationEvidence


class InvestigationResult(BaseModel):
    """Result of a troubleshooting investigation (placeholder).

    All fields are optional for now; they will be filled in once the
    Kubernetes inspectors and AI analysis are implemented.
    """

    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence: Optional[float] = None
