"""Background investigation jobs.

POST /investigations starts a job and returns its id immediately; the job
runs on a small thread pool (kubectl and LLM calls block) and reports
progress and its final result to its tracker, which the frontend polls.
No HTTP request is held open for the minute or more an investigation can
take, and a page refresh can pick the job back up by id.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from loguru import logger

from app.ai.agent import analyze
from app.core.auth import AuthUser
from app.kubernetes.kubectl import Kubectl
from app.services import history, progress
from app.services.investigation import run_investigation

# Investigations running at once across all users.
MAX_CONCURRENT_JOBS = 4
# Investigations one user may have running at once.
MAX_RUNNING_PER_USER = 2

# Shown when kubectl cannot reach the cluster at all.
CLUSTER_UNREACHABLE_MESSAGE = (
    "Unable to connect to the Kubernetes cluster.\n\n"
    "Please verify:\n"
    "- kubeconfig path (KUBECONFIG_PATH or ~/.kube/config)\n"
    "- the cluster is running and reachable\n"
    "- kubectl permissions (try: kubectl get pods -A)"
)

_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="investigation")


class TooManyRunning(Exception):
    """The user already has MAX_RUNNING_PER_USER investigations running."""


def start(user: AuthUser, context: Optional[str]) -> str:
    """Start an investigation in the background and return its id."""
    if progress.running_count(user.id) >= MAX_RUNNING_PER_USER:
        raise TooManyRunning()
    investigation_id = str(uuid.uuid4())
    tracker = progress.create(investigation_id, owner_id=user.id)
    _executor.submit(_run, investigation_id, tracker, user, context)
    return investigation_id


def _run(investigation_id: str, tracker: progress.ProgressTracker, user: AuthUser, context: Optional[str]) -> None:
    """The job body. Never raises: failures become an error result."""
    try:
        tracker.finish(_investigate(investigation_id, tracker, user, context))
    except Exception as exc:  # noqa: BLE001 — a crashed job must still finish
        logger.exception("Investigation {} crashed", investigation_id)
        tracker.finish(
            {
                "investigation_id": investigation_id,
                "status": "error",
                "diagnosis": {"error": f"Investigation failed unexpectedly ({type(exc).__name__})."},
                "investigation": {},
                "saved": False,
            }
        )


def _investigate(investigation_id: str, tracker: progress.ProgressTracker, user: AuthUser, context: Optional[str]) -> dict:
    kube = Kubectl(context)
    evidence = run_investigation(kube, tracker)

    # If even pod listing failed, the cluster itself is unreachable —
    # return a beginner-friendly message and skip AI reasoning.
    if evidence.get("pods", {}).get("error"):
        tracker.finish_step("AI Reasoning")
        return {
            "investigation_id": investigation_id,
            "status": "error",
            "diagnosis": {"error": "Investigation could not run — cluster unreachable."},
            "investigation": evidence,
            "cluster_error": CLUSTER_UNREACHABLE_MESSAGE,
            "saved": False,
        }

    tracker.start_step("AI Reasoning")
    diagnosis = analyze(evidence, kube)
    tracker.finish_step("AI Reasoning")

    saved = history.save_investigation(
        investigation_id,
        user,
        context=context,
        status="failed" if diagnosis.get("error") else "completed",
        diagnosis=diagnosis,
    )
    return {
        "investigation_id": investigation_id,
        "status": "success",
        "diagnosis": diagnosis,
        "investigation": evidence,
        "saved": saved,
    }
