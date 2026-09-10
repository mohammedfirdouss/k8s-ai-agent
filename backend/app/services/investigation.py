"""Investigation service.

Orchestrates the Kubernetes inspectors in order and assembles one
structured evidence payload:

    Check Pods -> Collect Logs -> Analyze Events
        -> Inspect Deployments -> Check Networking

AI reasoning over this evidence is added in a later step.
"""

from loguru import logger

from app.kubernetes import inspectors
from app.services import progress


def run_investigation() -> dict:
    """Run a full evidence-gathering investigation of the cluster.

    Each step is isolated: if one inspector fails, its section carries
    the error and the remaining steps still run. Progress is reported
    to the in-memory tracker so the frontend can poll it live.
    """
    logger.info("Starting cluster investigation")

    pods = _tracked_step("Checking Pods", "pods", inspectors.inspect_pods)

    problematic_pods = pods.get("problematic_pods", [])
    logs = _tracked_step("Reading Logs", "logs", lambda: inspectors.collect_logs(problematic_pods))

    events = _tracked_step("Analyzing Events", "events", inspectors.analyze_events)
    deployments = _tracked_step(
        "Inspecting Deployments", "deployments", inspectors.inspect_deployments
    )
    network = _tracked_step("Checking Networking", "network", inspectors.inspect_network)

    logger.info("Investigation complete")
    return {
        "pods": pods,
        "logs": logs,
        "events": events,
        "deployments": deployments,
        "network": network,
    }


def _tracked_step(progress_name: str, name: str, step) -> dict:
    """Run one inspection step with progress reporting.

    Unexpected crashes become an error section instead of killing the
    whole investigation.
    """
    logger.info("Investigation step: {}", name)
    progress.start_step(progress_name)
    try:
        return step()
    except Exception as exc:  # noqa: BLE001 — one bad step must not kill the investigation
        logger.exception("Investigation step '{}' crashed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        progress.finish_step(progress_name)
