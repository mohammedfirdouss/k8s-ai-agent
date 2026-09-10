"""Investigation service.

Orchestrates the Kubernetes inspectors in order and assembles one
structured evidence payload:

    Check Pods -> Collect Logs -> Analyze Events
        -> Inspect Deployments -> Check Networking

AI reasoning over this evidence is added in a later step.
"""

from loguru import logger

from app.kubernetes import inspectors


def run_investigation() -> dict:
    """Run a full evidence-gathering investigation of the cluster.

    Each step is isolated: if one inspector fails, its section carries
    the error and the remaining steps still run.
    """
    logger.info("Starting cluster investigation")

    pods = _safe_step("pods", inspectors.inspect_pods)

    problematic_pods = pods.get("problematic_pods", [])
    logs = _safe_step("logs", lambda: inspectors.collect_logs(problematic_pods))

    events = _safe_step("events", inspectors.analyze_events)
    deployments = _safe_step("deployments", inspectors.inspect_deployments)
    network = _safe_step("network", inspectors.inspect_network)

    logger.info("Investigation complete")
    return {
        "pods": pods,
        "logs": logs,
        "events": events,
        "deployments": deployments,
        "network": network,
    }


def _safe_step(name: str, step) -> dict:
    """Run one inspection step, converting unexpected crashes into an error section."""
    logger.info("Investigation step: {}", name)
    try:
        return step()
    except Exception as exc:  # noqa: BLE001 — one bad step must not kill the investigation
        logger.exception("Investigation step '{}' crashed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}
