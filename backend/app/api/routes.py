"""HTTP routes for the API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import AuthUser, get_current_user
from app.kubernetes import kubectl
from app.models.schemas import (
    ClustersResponse,
    HealthResponse,
    InvestigateRequest,
    InvestigationStarted,
    InvestigationStatus,
)
from app.services import jobs, progress

router = APIRouter()


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


@router.post(
    "/investigations",
    response_model=InvestigationStarted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["investigation"],
)
def start_investigation(
    request: InvestigateRequest,
    user: AuthUser = Depends(get_current_user),
) -> InvestigationStarted:
    """Start investigating a cluster in the background.

    Returns the investigation id at once; poll GET /investigations/{id}
    for progress and the result. The optional `context` selects which
    kubeconfig context (cluster) to investigate.
    """
    context = request.context or None
    if context is not None and context not in kubectl.list_contexts()["clusters"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown cluster context '{context}'.",
        )
    try:
        investigation_id = jobs.start(user, context)
    except jobs.TooManyRunning:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You already have investigations running. Wait for one to finish.",
        )
    return InvestigationStarted(investigation_id=investigation_id)


@router.get("/investigations/{investigation_id}", response_model=InvestigationStatus, tags=["investigation"])
def get_investigation(
    investigation_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> InvestigationStatus:
    """Progress of one of the caller's investigations, and its result once finished.

    Finished investigations stay here for 10 minutes; after that, read them
    from the user's history.
    """
    tracker = progress.get(str(investigation_id), owner_id=user.id)
    if tracker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
    return InvestigationStatus(investigation_id=investigation_id, **tracker.snapshot())
