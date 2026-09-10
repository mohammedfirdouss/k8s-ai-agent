"""HTTP routes for the API."""

from fastapi import APIRouter

from app.ai.agent import analyze
from app.models.schemas import HealthResponse, InvestigateResponse
from app.services import progress
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
    """Investigate the cluster and return an AI diagnosis with the evidence.

    Defined as a sync function on purpose: kubectl and LLM calls are
    blocking, so FastAPI runs this in a worker thread instead of the
    event loop.
    """
    progress.reset()
    try:
        evidence = run_investigation()
        progress.start_step("AI Reasoning")
        diagnosis = analyze(evidence)
        progress.finish_step("AI Reasoning")
    finally:
        progress.finish()
    return InvestigateResponse(status="success", diagnosis=diagnosis, investigation=evidence)


@router.get("/investigate/progress", tags=["investigation"])
async def investigation_progress() -> dict:
    """Live progress of the current (or last) investigation.

    The frontend polls this while POST /investigate is running to show
    step-by-step status.
    """
    return progress.snapshot()
