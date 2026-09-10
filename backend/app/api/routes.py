"""HTTP routes for the API."""

from fastapi import APIRouter

from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Simple health check endpoint.

    Used by load balancers, Kubernetes probes, and humans to verify
    the service is up.
    """
    return HealthResponse(status="healthy", service="ai-kubernetes-agent")
