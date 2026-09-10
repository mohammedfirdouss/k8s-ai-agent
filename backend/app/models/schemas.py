"""Pydantic schemas used by the API."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for the /health endpoint."""

    status: str
    service: str


class InvestigationResult(BaseModel):
    """Result of a troubleshooting investigation (placeholder).

    All fields are optional for now; they will be filled in once the
    Kubernetes inspectors and AI analysis are implemented.
    """

    root_cause: str | None = None
    suggested_fix: str | None = None
    confidence: float | None = None
