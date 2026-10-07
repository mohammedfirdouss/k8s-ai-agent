"""Cluster inspectors.

Each inspector collects one kind of troubleshooting evidence via kubectl
and returns a plain dict, so the investigation service can assemble a
single structured payload. No AI reasoning happens here — this layer
only gathers evidence, like a junior DevOps engineer running kubectl.
"""

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.kubernetes.kubectl import Kubectl, KubectlResult
from app.kubernetes.redact import redact

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
MAX_LABEL_CANDIDATES = 5

# A restarted container that has been up for less than this is treated as
# unstable even if it happens to be running right now (e.g. a liveness probe
# killing it in a loop). Up longer than this, it recovered.
STABLE_AFTER = timedelta(minutes=5)


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pod_problem_state(pod: dict, now: datetime) -> Optional[str]:
    """Return the problematic state of a pod, or None if it looks healthy."""
    phase = pod.get("status", {}).get("phase", "")
    if phase == "Succeeded":
        return None
    container_statuses = pod.get("status", {}).get("containerStatuses", [])

    # A stuck init container blocks the whole pod, so report it first.
    for container in pod.get("status", {}).get("initContainerStatuses", []):
        waiting_reason = container.get("state", {}).get("waiting", {}).get("reason", "")
        if waiting_reason in PROBLEM_POD_STATES:
            return f"Init:{waiting_reason}"

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

    # Running but failing its readiness probe: receives no traffic.
    if phase == "Running" and any(
        "running" in c.get("state", {}) and not c.get("ready") for c in container_statuses
    ):
        return "NotReady"

    # Up right now, but only briefly since its last restart: crashing or being
    # killed in a loop. Restarts with reason "Unknown" come from the node or
    # container runtime restarting (e.g. a reboot), not from the app.
    for container in container_statuses:
        last = container.get("lastState", {}).get("terminated", {})
        started = _parse_time(container.get("state", {}).get("running", {}).get("startedAt"))
        if (
            container.get("restartCount", 0) > 0
            and last.get("reason") not in (None, "Unknown")
            and started is not None
            and now - started < STABLE_AFTER
        ):
            return "RestartingRecently"
    return None


def _pod_key(pod: dict) -> str:
    return f'{pod["metadata"]["namespace"]}/{pod["metadata"]["name"]}'


def _workload(pod: dict) -> Optional[str]:
    """The controller that owns a pod, e.g. "Deployment/payment-service"."""
    owners = pod.get("metadata", {}).get("ownerReferences") or []
    if not owners:
        return None
    owner = owners[0]
    kind, name = owner.get("kind", ""), owner.get("name", "")
    # Deployment pods are owned by a ReplicaSet named <deployment>-<hash>.
    if kind == "ReplicaSet" and "-" in name:
        return f"Deployment/{name.rsplit('-', 1)[0]}"
    return f"{kind}/{name}"


def _container_details(pod: dict) -> "list[dict]":
    """Image, resource limits and last termination of each container."""
    statuses = {c.get("name"): c for c in pod.get("status", {}).get("containerStatuses", [])}
    details = []
    for container in pod.get("spec", {}).get("containers", []):
        status = statuses.get(container.get("name"), {})
        last = status.get("lastState", {}).get("terminated") or status.get("state", {}).get("terminated") or {}
        details.append(
            {
                "name": container.get("name"),
                "image": container.get("image"),
                "requests": container.get("resources", {}).get("requests", {}),
                "limits": container.get("resources", {}).get("limits", {}),
                # e.g. 'configmap "x" not found' for CreateContainerConfigError.
                "waiting_message": redact(status.get("state", {}).get("waiting", {}).get("message", ""))[:300] or None,
                "last_exit_code": last.get("exitCode"),
                "last_termination_reason": last.get("reason"),
            }
        )
    return details


def _node_ready(kube: Kubectl) -> "Optional[dict[str, bool]]":
    """Map node name -> whether it is Ready now, or None on error."""
    data, error = kube.run_json(["get", "nodes"])
    if error:
        return None
    return {
        node["metadata"]["name"]: any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in node.get("status", {}).get("conditions", [])
        )
        for node in data.get("items", [])
    }


def _pod_states(kube: Kubectl) -> "Optional[dict[str, Optional[str]]]":
    """Map "namespace/name" -> problem state (None when healthy), or None on error."""
    data, error = kube.run_json(["get", "pods", "-A"])
    if error:
        return None
    now = kube.now()
    return {_pod_key(pod): _pod_problem_state(pod, now) for pod in data.get("items", [])}


def inspect_pods(kube: Kubectl) -> dict:
    """Check all pods and report the unhealthy ones."""
    data, error = kube.run_json(["get", "pods", "-A"])
    if error:
        return {"healthy": None, "error": error, "problematic_pods": []}

    problematic = []
    now = kube.now()
    pods = data.get("items", [])
    for pod in pods:
        state = _pod_problem_state(pod, now)
        if state is None:
            continue
        restart_count = sum(
            c.get("restartCount", 0) for c in pod.get("status", {}).get("containerStatuses", [])
        )
        problematic.append(
            {
                "name": pod["metadata"]["name"],
                "namespace": pod["metadata"]["namespace"],
                "workload": _workload(pod),
                "status": state,
                "restarts": restart_count,
                "containers": _container_details(pod),
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
    lines = [redact(line.strip()) for line in log_text.splitlines() if line.strip()]
    significant = [
        line for line in lines if any(marker in line.lower() for marker in LOG_ERROR_MARKERS)
    ]
    # If nothing matched, keep the tail — the last lines before a crash
    # are usually the most informative ones.
    if not significant:
        significant = lines[-10:]
    return significant[-MAX_LOG_LINES_PER_POD:]


def _has_logs(result: KubectlResult) -> bool:
    """True when kubectl returned actual container output.

    When a container was just replaced, kubectl prints the kubelet notice
    "unable to retrieve container logs for ..." on stdout instead of logs.
    """
    text = result.stdout.strip()
    return result.success and bool(text) and not text.startswith("unable to retrieve container logs")


def collect_logs(kube: Kubectl, problematic_pods: list[dict]) -> dict:
    """Fetch concise, failure-focused logs for each problematic pod."""
    logs: dict[str, dict] = {}
    for pod in problematic_pods:
        name, namespace = pod["name"], pod["namespace"]
        result = kube.run(["logs", name, "-n", namespace, "--tail", "100"])

        # A crash-looping container often has no current logs; the
        # previous (crashed) container's logs hold the real error.
        if not _has_logs(result):
            previous = kube.run(["logs", name, "-n", namespace, "--tail", "100", "--previous"])
            if _has_logs(previous):
                result = previous
        if result.success and not _has_logs(result):
            # e.g. the kubelet's "unable to retrieve container logs" notice.
            result = KubectlResult(success=True, stdout="", command=result.command)

        key = f"{namespace}/{name}"
        if not result.success:
            logs[key] = {"error": result.error, "lines": []}
        else:
            logs[key] = {"error": None, "lines": _significant_lines(result.stdout)}

    logger.info("Log collection: gathered logs for {} pods", len(logs))
    return {"pods_with_logs": len(logs), "logs": logs}


def _event_time(event: dict) -> str:
    """Sortable timestamp of an event's most recent occurrence."""
    return (
        event.get("lastTimestamp")
        or (event.get("series") or {}).get("lastObservedTime")
        or event.get("eventTime")
        or event.get("firstTimestamp")
        or event.get("metadata", {}).get("creationTimestamp")
        or ""
    )


def analyze_events(kube: Kubectl) -> dict:
    """Read cluster events and summarize the failure-related ones.

    Events outlive the problems they describe (they are kept for an hour by
    default), so warnings about pods that have since become healthy (or no
    longer exist) and nodes that are Ready again are dropped: they describe
    resolved issues and mislead the diagnosis. The number dropped is
    reported instead.
    """
    data, error = kube.run_json(["get", "events", "-A"])
    if error:
        return {"error": error, "findings": []}
    pod_states = _pod_states(kube)
    node_ready = _node_ready(kube)

    findings = []
    resolved = 0
    events = sorted(data.get("items", []), key=_event_time)
    for event in events:
        reason = event.get("reason", "")
        if event.get("type") != "Warning" and reason not in PROBLEM_EVENT_REASONS:
            continue
        involved = event.get("involvedObject", {})
        if involved.get("kind") == "Pod" and pod_states is not None:
            key = f'{involved.get("namespace", "")}/{involved.get("name", "")}'
            if pod_states.get(key) is None:  # healthy now, or gone
                resolved += 1
                continue
        if involved.get("kind") == "Node" and node_ready is not None:
            if node_ready.get(involved.get("name", ""), True):  # Ready now, or gone
                resolved += 1
                continue
        findings.append(
            {
                "reason": reason,
                "type": event.get("type", ""),
                "object": f'{involved.get("kind", "")}/{involved.get("name", "")}',
                "namespace": involved.get("namespace", ""),
                "message": redact(event.get("message", ""))[:300],
                "count": event.get("count", 1),
                "last_seen": _event_time(event) or None,
            }
        )

    findings = findings[-MAX_EVENTS:]  # newest last, so keep the most recent
    logger.info("Event analysis: {} failure-related events ({} resolved, omitted)", len(findings), resolved)
    return {
        "error": None,
        "total_findings": len(findings),
        "resolved_events_omitted": resolved,
        "findings": findings,
    }


def inspect_deployments(kube: Kubectl) -> dict:
    """Check deployments for missing replicas and failed rollouts."""
    data, error = kube.run_json(["get", "deployments", "-A"])
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
            {"type": c.get("type"), "reason": c.get("reason"), "message": redact(c.get("message", ""))[:300]}
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


def inspect_network(kube: Kubectl) -> dict:
    """Check services for selector/endpoint problems and DNS health."""
    services_data, services_error = kube.run_json(["get", "svc", "-A"])
    endpoints_data, endpoints_error = kube.run_json(["get", "endpoints", "-A"])
    if services_error or endpoints_error:
        return {"healthy": None, "error": services_error or endpoints_error, "issues": []}

    # Map "namespace/name" -> whether the endpoints object has addresses.
    endpoints_ready: dict[str, bool] = {}
    for endpoint in endpoints_data.get("items", []):
        key = f'{endpoint["metadata"]["namespace"]}/{endpoint["metadata"]["name"]}'
        has_addresses = any(subset.get("addresses") for subset in endpoint.get("subsets") or [])
        endpoints_ready[key] = has_addresses

    pods_data, pods_error = kube.run_json(["get", "pods", "-A"])
    labels_by_namespace: "dict[str, list[dict]]" = {}
    for pod in [] if pods_error else pods_data.get("items", []):
        labels_by_namespace.setdefault(pod["metadata"]["namespace"], []).append(
            {"pod": pod["metadata"]["name"], "labels": pod["metadata"].get("labels", {})}
        )

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
            selector = spec.get("selector", {})
            candidates = labels_by_namespace.get(namespace, [])
            matching = [
                c["pod"] for c in candidates
                if all(c["labels"].get(k) == v for k, v in selector.items())
            ]
            issues.append(
                {
                    "service": name,
                    "namespace": namespace,
                    "problem": "no ready endpoints",
                    "selector": selector,
                    # Pods the selector matches (if any exist, they are not
                    # Ready); when empty, the selector matches no pod at all.
                    "pods_matching_selector": matching,
                    # Labels of pods in the same namespace, to compare
                    # against the selector.
                    "pod_labels_in_namespace": candidates[:MAX_LABEL_CANDIDATES],
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
