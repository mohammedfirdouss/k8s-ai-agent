"""HTTP routes for the API."""

from typing import Optional

from fastapi import APIRouter

from app.ai.agent import analyze
from app.kubernetes import kubectl
from app.models.schemas import (
    ClustersResponse,
    HealthResponse,
    InvestigateRequest,
    InvestigateResponse,
)
from app.services import progress
from app.services.investigation import run_investigation

router = APIRouter()

# Shown when kubectl cannot reach the cluster at all.
CLUSTER_UNREACHABLE_MESSAGE = (
    "Unable to connect to the Kubernetes cluster.\n\n"
    "Please verify:\n"
    "- kubeconfig path (KUBECONFIG_PATH or ~/.kube/config)\n"
    "- the cluster is running and reachable\n"
    "- kubectl permissions (try: kubectl get pods -A)"
)


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Simple health check endpoint.

    Used by load balancers, Kubernetes probes, and humans to verify
    the service is up.
    """
    return HealthResponse(status="healthy", service="ai-kubernetes-agent")


@router.get("/clusters", response_model=ClustersResponse, tags=["investigation"])
def list_clusters() -> ClustersResponse:
    """List the clusters (kubeconfig contexts) available on this machine."""
    return ClustersResponse(**kubectl.list_contexts())


@router.post("/investigate", response_model=InvestigateResponse, tags=["investigation"])
def investigate(request: Optional[InvestigateRequest] = None) -> InvestigateResponse:
    """Investigate a cluster and return an AI diagnosis with the evidence.

    Accepts an optional {"context": "..."} body selecting which
    kubeconfig context (cluster) to investigate.

    Defined as a sync function on purpose: kubectl and LLM calls are
    blocking, so FastAPI runs this in a worker thread instead of the
    event loop.
    """
    kubectl.set_context(request.context if request else None)
    progress.reset()
    try:
        evidence = run_investigation()

        # If even pod listing failed, the cluster itself is unreachable —
        # return a beginner-friendly message and skip AI reasoning.
        if evidence.get("pods", {}).get("error"):
            progress.finish_step("AI Reasoning")
            return InvestigateResponse(
                status="error",
                diagnosis={"error": "Investigation could not run — cluster unreachable."},
                investigation=evidence,
                cluster_error=CLUSTER_UNREACHABLE_MESSAGE,
            )

        progress.start_step("AI Reasoning")
        diagnosis = analyze(evidence)
        progress.finish_step("AI Reasoning")
    finally:
        progress.finish()
        kubectl.set_context(None)
    return InvestigateResponse(status="success", diagnosis=diagnosis, investigation=evidence)


@router.get("/investigate/progress", tags=["investigation"])
async def investigation_progress() -> dict:
    """Live progress of the current (or last) investigation.

    The frontend polls this while POST /investigate is running to show
    step-by-step status.
    """
    return progress.snapshot()
