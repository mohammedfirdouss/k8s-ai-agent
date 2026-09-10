"""HTTP routes for the API."""

from fastapi import APIRouter

from app.models.schemas import HealthResponse, InvestigateResponse
from app.services.investigation import run_investigation

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Simple health check endpoint.

    Used by load balancers, Kubernetes probes, and humans to verify
    the service is up.
    """
    return HealthResponse(status="healthy", service="ai-kubernetes-agent")


@router.post("/investigate", response_model=InvestigateResponse, tags=["investigation"])
def investigate() -> InvestigateResponse:
    """Run a cluster investigation and return the gathered evidence.

    Defined as a sync function on purpose: kubectl calls are blocking,
    so FastAPI runs this in a worker thread instead of the event loop.
    """
    evidence = run_investigation()
    return InvestigateResponse(status="success", investigation=evidence)
