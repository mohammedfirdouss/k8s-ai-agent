"""Investigation service.

Orchestrates the Kubernetes inspectors in order and assembles one
structured evidence payload:

    Check Pods -> Collect Logs -> Analyze Events
        -> Inspect Deployments -> Check Networking

AI reasoning over this evidence happens afterwards, in `app.ai.agent`.
"""

from loguru import logger

from app.kubernetes import inspectors
from app.kubernetes.kubectl import Kubectl
from app.services.progress import ProgressTracker


def run_investigation(kube: Kubectl, tracker: ProgressTracker) -> dict:
    """Run a full evidence-gathering investigation of the cluster.

    Each step is isolated: if one inspector fails, its section carries
    the error and the remaining steps still run. Progress is reported
    to this investigation's tracker so the frontend can poll it live.
    """
    logger.info("Starting cluster investigation (context: {})", kube.context or "default")

    pods = _tracked_step(tracker, "Checking Pods", "pods", lambda: inspectors.inspect_pods(kube))

    problematic_pods = pods.get("problematic_pods", [])
    logs = _tracked_step(
        tracker, "Reading Logs", "logs", lambda: inspectors.collect_logs(kube, problematic_pods)
    )

    events = _tracked_step(
        tracker, "Analyzing Events", "events", lambda: inspectors.analyze_events(kube)
    )
    deployments = _tracked_step(
        tracker, "Inspecting Deployments", "deployments", lambda: inspectors.inspect_deployments(kube)
    )
    network = _tracked_step(
        tracker, "Checking Networking", "network", lambda: inspectors.inspect_network(kube)
    )

    logger.info("Investigation complete")
    return {
        "pods": pods,
        "logs": logs,
        "events": events,
        "deployments": deployments,
        "network": network,
    }


def _tracked_step(tracker: ProgressTracker, progress_name: str, name: str, step) -> dict:
    """Run one inspection step with progress reporting.

    Unexpected crashes become an error section instead of killing the
    whole investigation.
    """
    logger.info("Investigation step: {}", name)
    tracker.start_step(progress_name)
    try:
        return step()
    except Exception as exc:  # noqa: BLE001 — one bad step must not kill the investigation
        logger.exception("Investigation step '{}' crashed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        tracker.finish_step(progress_name)
