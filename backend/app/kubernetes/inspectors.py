"""Cluster inspectors.

Each inspector collects one kind of troubleshooting evidence via kubectl
and returns a plain dict, so the investigation service can assemble a
single structured payload. No AI reasoning happens here — this layer
only gathers evidence, like a junior DevOps engineer running kubectl.
"""

from typing import Optional

from loguru import logger

from app.kubernetes.kubectl import run_kubectl, run_kubectl_json

# Container/pod states we consider problematic.
PROBLEM_POD_STATES = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "Pending",
    "Error",
    "OOMKilled",
    "ContainerCreating",
    "CreateContainerConfigError",
}

# Event reasons that usually point at a real failure.
PROBLEM_EVENT_REASONS = {
    "FailedScheduling",
    "BackOff",
    "FailedMount",
    "FailedPull",
    "ErrImagePull",
    "Unhealthy",
    "OOMKilling",
    "FailedCreate",
}

# Log lines matching any of these markers are treated as significant.
LOG_ERROR_MARKERS = (
    "error",
    "exception",
    "traceback",
    "fatal",
    "panic",
    "refused",
    "timeout",
    "cannot",
    "failed",
    "missing",
    "not found",
    "unauthorized",
)

# Caps that keep the payload small enough for an LLM prompt later.
MAX_LOG_LINES_PER_POD = 30
MAX_EVENTS = 40


def _pod_problem_state(pod: dict) -> Optional[str]:
    """Return the problematic state of a pod, or None if it looks healthy."""
    phase = pod.get("status", {}).get("phase", "")
    container_statuses = pod.get("status", {}).get("containerStatuses", [])

    for container in container_statuses:
        state = container.get("state", {})
        waiting_reason = state.get("waiting", {}).get("reason", "")
        if waiting_reason in PROBLEM_POD_STATES:
            return waiting_reason

        last_terminated = container.get("lastState", {}).get("terminated", {})
        if last_terminated.get("reason") == "OOMKilled":
            return "OOMKilled"

        terminated_reason = state.get("terminated", {}).get("reason", "")
        if terminated_reason in ("Error", "OOMKilled"):
            return terminated_reason

    if phase in ("Pending", "Failed"):
        return phase
    return None


def inspect_pods() -> dict:
    """Check all pods and report the unhealthy ones."""
    data, error = run_kubectl_json(["get", "pods", "-A"])
    if error:
        return {"healthy": None, "error": error, "problematic_pods": []}

    problematic = []
    pods = data.get("items", [])
    for pod in pods:
        state = _pod_problem_state(pod)
        if state is None:
            continue
        restart_count = sum(
            c.get("restartCount", 0) for c in pod.get("status", {}).get("containerStatuses", [])
        )
        problematic.append(
            {
                "name": pod["metadata"]["name"],
                "namespace": pod["metadata"]["namespace"],
                "status": state,
                "restarts": restart_count,
            }
        )

    logger.info("Pod inspection: {} pods total, {} problematic", len(pods), len(problematic))
    return {
        "healthy": not problematic,
        "total_pods": len(pods),
        "problematic_pods": problematic,
    }


def _significant_lines(log_text: str) -> list[str]:
    """Keep only lines that look like failures, capped for brevity."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    significant = [
        line for line in lines if any(marker in line.lower() for marker in LOG_ERROR_MARKERS)
    ]
    # If nothing matched, keep the tail — the last lines before a crash
    # are usually the most informative ones.
    if not significant:
        significant = lines[-10:]
    return significant[-MAX_LOG_LINES_PER_POD:]


def collect_logs(problematic_pods: list[dict]) -> dict:
    """Fetch concise, failure-focused logs for each problematic pod."""
    logs: dict[str, dict] = {}
    for pod in problematic_pods:
        name, namespace = pod["name"], pod["namespace"]
        result = run_kubectl(["logs", name, "-n", namespace, "--tail", "100"])

        # A crash-looping container often has no current logs; the
        # previous (crashed) container's logs hold the real error.
        if (not result.success or not result.stdout.strip()):
            previous = run_kubectl(["logs", name, "-n", namespace, "--tail", "100", "--previous"])
            if previous.success and previous.stdout.strip():
                result = previous

        key = f"{namespace}/{name}"
        if not result.success:
            logs[key] = {"error": result.error, "lines": []}
        else:
            logs[key] = {"error": None, "lines": _significant_lines(result.stdout)}

    logger.info("Log collection: gathered logs for {} pods", len(logs))
    return {"pods_with_logs": len(logs), "logs": logs}


def analyze_events() -> dict:
    """Read cluster events and summarize the failure-related ones."""
    data, error = run_kubectl_json(["get", "events", "-A"])
    if error:
        return {"error": error, "findings": []}

    findings = []
    for event in data.get("items", []):
        reason = event.get("reason", "")
        if event.get("type") != "Warning" and reason not in PROBLEM_EVENT_REASONS:
            continue
        involved = event.get("involvedObject", {})
        findings.append(
            {
                "reason": reason,
                "type": event.get("type", ""),
                "object": f'{involved.get("kind", "")}/{involved.get("name", "")}',
                "namespace": involved.get("namespace", ""),
                "message": event.get("message", "")[:300],
                "count": event.get("count", 1),
            }
        )

    findings = findings[-MAX_EVENTS:]
    logger.info("Event analysis: {} failure-related events", len(findings))
    return {"error": None, "total_findings": len(findings), "findings": findings}


def inspect_deployments() -> dict:
    """Check deployments for missing replicas and failed rollouts."""
    data, error = run_kubectl_json(["get", "deployments", "-A"])
    if error:
        return {"healthy": None, "error": error, "unhealthy_deployments": []}

    unhealthy = []
    deployments = data.get("items", [])
    for deployment in deployments:
        spec_replicas = deployment.get("spec", {}).get("replicas", 0)
        status = deployment.get("status", {})
        available = status.get("availableReplicas", 0)
        unavailable = status.get("unavailableReplicas", 0)

        failed_conditions = [
            {"type": c.get("type"), "reason": c.get("reason"), "message": c.get("message", "")[:300]}
            for c in status.get("conditions", [])
            if c.get("status") == "False"
        ]

        if available < spec_replicas or unavailable > 0 or failed_conditions:
            unhealthy.append(
                {
                    "name": deployment["metadata"]["name"],
                    "namespace": deployment["metadata"]["namespace"],
                    "desired_replicas": spec_replicas,
                    "available_replicas": available,
                    "unavailable_replicas": unavailable,
                    "failed_conditions": failed_conditions,
                }
            )

    logger.info(
        "Deployment inspection: {} deployments total, {} unhealthy", len(deployments), len(unhealthy)
    )
    return {
        "healthy": not unhealthy,
        "total_deployments": len(deployments),
        "unhealthy_deployments": unhealthy,
    }


def inspect_network() -> dict:
    """Check services for selector/endpoint problems and DNS health."""
    services_data, services_error = run_kubectl_json(["get", "svc", "-A"])
    endpoints_data, endpoints_error = run_kubectl_json(["get", "endpoints", "-A"])
    if services_error or endpoints_error:
        return {"healthy": None, "error": services_error or endpoints_error, "issues": []}

    # Map "namespace/name" -> whether the endpoints object has addresses.
    endpoints_ready: dict[str, bool] = {}
    for endpoint in endpoints_data.get("items", []):
        key = f'{endpoint["metadata"]["namespace"]}/{endpoint["metadata"]["name"]}'
        has_addresses = any(subset.get("addresses") for subset in endpoint.get("subsets") or [])
        endpoints_ready[key] = has_addresses

    issues = []
    services = services_data.get("items", [])
    for service in services:
        name = service["metadata"]["name"]
        namespace = service["metadata"]["namespace"]
        spec = service.get("spec", {})

        # ExternalName services and selector-less services manage their
        # own endpoints, so "no endpoints" is not a failure for them.
        if spec.get("type") == "ExternalName" or not spec.get("selector"):
            continue

        if not endpoints_ready.get(f"{namespace}/{name}", False):
            issues.append(
                {
                    "service": name,
                    "namespace": namespace,
                    "problem": "no ready endpoints",
                    "hint": "selector may not match any healthy pod labels",
                    "selector": spec.get("selector", {}),
                }
            )

    # DNS: the cluster's DNS service (kube-dns/CoreDNS) must have endpoints.
    dns_healthy = any(
        ready for key, ready in endpoints_ready.items() if key.startswith("kube-system/kube-dns")
    )

    logger.info("Network inspection: {} services total, {} with issues", len(services), len(issues))
    return {
        "healthy": not issues and dns_healthy,
        "total_services": len(services),
        "dns_healthy": dns_healthy,
        "issues": issues,
    }
