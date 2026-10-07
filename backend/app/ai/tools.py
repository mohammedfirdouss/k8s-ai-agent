"""Read-only kubectl tools the agent can call to dig deeper.

The model never writes kubectl commands itself: it picks a tool and fills
in a few typed arguments, and this module builds the command. Kinds come
from a fixed allowlist (Secrets are deliberately absent), names must be
valid Kubernetes names (so nothing can be smuggled in as a flag), and every
output is redacted and truncated before it goes back to the model.
"""

import json
import re
from typing import Optional

from app.kubernetes.kubectl import Kubectl
from app.kubernetes.redact import redact

# Kinds the agent may read. No Secrets: their values must never reach the LLM.
READABLE_KINDS = (
    "pod",
    "deployment",
    "replicaset",
    "statefulset",
    "daemonset",
    "job",
    "cronjob",
    "service",
    "endpoints",
    "ingress",
    "networkpolicy",
    "configmap",
    "persistentvolumeclaim",
    "horizontalpodautoscaler",
    "node",
)
# Kinds without a namespace.
CLUSTER_SCOPED = {"node"}

MAX_OUTPUT_CHARS = 4000
LOG_TAIL_LINES = 100

# RFC 1123 names (pods, services, namespaces...), plus dots for nodes/configmaps.
_NAME = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


class ToolError(Exception):
    """A tool call with invalid arguments; the message goes back to the model."""


def _schema(name: str, description: str, properties: dict, required: "list[str]") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_KIND = {"type": "string", "enum": list(READABLE_KINDS)}
_NAMESPACE = {"type": "string", "description": "Namespace (omit for nodes)."}

TOOL_SCHEMAS = [
    _schema(
        "describe",
        "kubectl describe one object: status, conditions, configuration and its recent events.",
        {"kind": _KIND, "name": {"type": "string"}, "namespace": _NAMESPACE},
        ["kind", "name"],
    ),
    _schema(
        "get_yaml",
        "The full YAML of one object (spec and status), e.g. to read probes, env, selectors or limits.",
        {"kind": _KIND, "name": {"type": "string"}, "namespace": _NAMESPACE},
        ["kind", "name"],
    ),
    _schema(
        "list",
        "List all objects of a kind in a namespace (kubectl get -o wide).",
        {"kind": _KIND, "namespace": _NAMESPACE},
        ["kind"],
    ),
    _schema(
        "logs",
        f"The last {LOG_TAIL_LINES} log lines of a pod's container. previous=true reads the "
        "container instance that crashed before the current one.",
        {
            "pod": {"type": "string"},
            "namespace": {"type": "string"},
            "container": {"type": "string", "description": "Container name; omit for single-container pods."},
            "previous": {"type": "boolean"},
        },
        ["pod", "namespace"],
    ),
]


def command_for(tool: str, args: dict) -> "list[str]":
    """The kubectl arguments for a tool call. Raises ToolError on bad input."""
    if tool == "logs":
        command = ["logs", _name(args.get("pod"), "pod"), "-n", _name(args.get("namespace"), "namespace")]
        if args.get("container"):
            command += ["-c", _name(args["container"], "container")]
        command += ["--tail", str(LOG_TAIL_LINES)]
        if args.get("previous"):
            command.append("--previous")
        return command

    kind = args.get("kind")
    if kind not in READABLE_KINDS:
        raise ToolError(f"kind must be one of: {', '.join(READABLE_KINDS)}")
    scope = _scope(kind, args.get("namespace"))
    if tool == "describe":
        return ["describe", kind, _name(args.get("name"), "name"), *scope]
    if tool == "get_yaml":
        return ["get", kind, _name(args.get("name"), "name"), *scope, "-o", "yaml"]
    if tool == "list":
        return ["get", kind, *scope, "-o", "wide"]
    raise ToolError(f"unknown tool '{tool}'")


def run_tool(kube: Kubectl, tool: str, raw_args: str) -> "tuple[str, Optional[list[str]]]":
    """Execute one tool call. Returns (output for the model, kubectl args run or None)."""
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ToolError("arguments must be a JSON object")
        command = command_for(tool, args)
    except (json.JSONDecodeError, ToolError) as exc:
        return f"Invalid tool call: {exc}", None

    result = kube.run(command)
    output = result.stdout if result.success else f"kubectl error: {result.error}"
    output = redact(output)
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(output) - MAX_OUTPUT_CHARS} more chars]"
    return output or "(no output)", command


def prefetch_commands(objects: "dict[str, list[str]]", namespace: str) -> "list[list[str]]":
    """Every command the tools can issue for the given objects in one namespace.

    `objects` maps kind -> names. Used when recording eval fixtures, so that
    replays can answer whatever the agent asks about the scenario.
    """
    commands = []
    for kind in READABLE_KINDS:
        if kind in CLUSTER_SCOPED:
            continue
        commands.append(command_for("list", {"kind": kind, "namespace": namespace}))
        for name in objects.get(kind, []):
            commands.append(command_for("describe", {"kind": kind, "name": name, "namespace": namespace}))
            commands.append(command_for("get_yaml", {"kind": kind, "name": name, "namespace": namespace}))
    for pod in objects.get("pod", []):
        for previous in (False, True):
            commands.append(command_for("logs", {"pod": pod, "namespace": namespace, "previous": previous}))
    return commands


def _scope(kind: str, namespace: Optional[str]) -> "list[str]":
    if kind in CLUSTER_SCOPED:
        return []
    return ["-n", _name(namespace, "namespace")]


def _name(value: Optional[str], field: str) -> str:
    if not isinstance(value, str) or not _NAME.match(value):
        raise ToolError(f"{field} must be a valid Kubernetes name, got {value!r}")
    return value
