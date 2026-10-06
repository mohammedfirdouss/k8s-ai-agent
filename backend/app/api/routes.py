"""HTTP routes for the API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.agent import analyze
from app.core.auth import AuthUser, get_current_user
from app.kubernetes import kubectl
from app.kubernetes.kubectl import Kubectl
from app.models.schemas import (
    ClustersResponse,
    HealthResponse,
    InvestigateRequest,
    InvestigateResponse,
)
from app.services import history, progress
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
    the service is up. Deliberately unauthenticated.
    """
    return HealthResponse(status="healthy", service="ai-kubernetes-agent")


@router.get("/clusters", response_model=ClustersResponse, tags=["investigation"])
def list_clusters(_user: AuthUser = Depends(get_current_user)) -> ClustersResponse:
    """List the clusters (kubeconfig contexts) available on this machine."""
    return ClustersResponse(**kubectl.list_contexts())


@router.post("/investigate", response_model=InvestigateResponse, tags=["investigation"])
def investigate(
    request: InvestigateRequest,
    user: AuthUser = Depends(get_current_user),
) -> InvestigateResponse:
    """Investigate a cluster and return an AI diagnosis with the evidence.

    The body carries a client-generated `investigation_id` (used to poll
    progress and as the history row id) and an optional kubeconfig
    `context` selecting which cluster to investigate.

    Defined as a sync function on purpose: kubectl and LLM calls are
    blocking, so FastAPI runs this in a worker thread instead of the
    event loop.
    """
    context = request.context or None
    if context is not None:
        available = kubectl.list_contexts()["clusters"]
        if context not in available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown cluster context '{context}'.",
            )

    investigation_id = str(request.investigation_id)
    try:
        tracker = progress.create(investigation_id, owner_id=user.id)
    except progress.InvestigationIdInUse:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An investigation with this id already exists.",
        )

    kube = Kubectl(context)
    try:
        evidence = run_investigation(kube, tracker)

        # If even pod listing failed, the cluster itself is unreachable —
        # return a beginner-friendly message and skip AI reasoning.
        if evidence.get("pods", {}).get("error"):
            tracker.finish_step("AI Reasoning")
            return InvestigateResponse(
                investigation_id=request.investigation_id,
                status="error",
                diagnosis={"error": "Investigation could not run — cluster unreachable."},
                investigation=evidence,
                cluster_error=CLUSTER_UNREACHABLE_MESSAGE,
            )

        tracker.start_step("AI Reasoning")
        diagnosis = analyze(evidence)
        tracker.finish_step("AI Reasoning")
    finally:
        tracker.finish()

    saved = history.save_investigation(
        investigation_id,
        user,
        context=context,
        status="failed" if diagnosis.get("error") else "completed",
        diagnosis=diagnosis,
    )
    return InvestigateResponse(
        investigation_id=request.investigation_id,
        status="success",
        diagnosis=diagnosis,
        investigation=evidence,
        saved=saved,
    )


@router.get("/investigations/{investigation_id}/progress", tags=["investigation"])
def investigation_progress(
    investigation_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Live progress of one of the caller's investigations.

    The frontend polls this while POST /investigate is running to show
    step-by-step status.
    """
    tracker = progress.get(str(investigation_id), owner_id=user.id)
    if tracker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
    return tracker.snapshot()
