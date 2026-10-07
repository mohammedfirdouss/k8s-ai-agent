"""Eval scenarios and their scoring rubrics.

Each scenario is a broken workload from `k8s-test-scenarios/` plus:
- `ready`: when the failure has fully developed and evidence can be taken
- a rubric: keyword groups a correct diagnosis must contain

Rubric groups are AND-ed; the alternatives inside a group are OR-ed, and
matching is case-insensitive. Keep alternatives broad enough to accept
any correct phrasing, but specific enough that a generic answer fails.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "k8s-test-scenarios"

Groups = "list[list[str]]"


@dataclass(frozen=True)
class Expectation:
    """What a correct diagnosis of one broken workload must say."""

    workload: str
    # Must appear in root_cause + explanation.
    cause: Groups
    # Must appear in fix + kubectl_commands.
    fix: Groups
    # When the evidence cannot establish the cause, a calibrated diagnosis
    # must not claim more confidence than this.
    max_confidence: "float | None" = None


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    manifests: "list[str]"
    # Called with the scenario namespace's pods (`kubectl get pods -o json`
    # items); True once the failure is ready to be investigated.
    ready: "Callable[[list[dict]], bool]"
    expectations: "list[Expectation]" = field(default_factory=list)
    # True for control scenarios: any incident is a false alarm.
    expect_healthy: bool = False
    # Extra wait after `ready` first holds, for failures that need time to
    # show in events (e.g. repeated probe failures).
    settle_seconds: int = 0

    @property
    def namespace(self) -> str:
        return f"eval-{self.id}"


def _container_statuses(pods: "list[dict]") -> "list[dict]":
    return [c for pod in pods for c in pod.get("status", {}).get("containerStatuses", [])]


def _any_waiting(*reasons: str) -> "Callable[[list[dict]], bool]":
    def check(pods: "list[dict]") -> bool:
        return any(
            c.get("state", {}).get("waiting", {}).get("reason") in reasons
            for c in _container_statuses(pods)
        )

    return check


def _oom_killed(pods: "list[dict]") -> bool:
    return any(
        c.get("lastState", {}).get("terminated", {}).get("reason") == "OOMKilled"
        for c in _container_statuses(pods)
    )


def _restarted_at_least(count: int) -> "Callable[[list[dict]], bool]":
    def check(pods: "list[dict]") -> bool:
        return any(c.get("restartCount", 0) >= count for c in _container_statuses(pods))

    return check


def _running_not_ready(pods: "list[dict]") -> bool:
    return any(
        "running" in c.get("state", {}) and not c.get("ready") for c in _container_statuses(pods)
    )


def _unschedulable(pods: "list[dict]") -> bool:
    return any(
        cond.get("type") == "PodScheduled" and cond.get("reason") == "Unschedulable"
        for pod in pods
        for cond in pod.get("status", {}).get("conditions", [])
    )


def _all_ready(pods: "list[dict]") -> bool:
    statuses = _container_statuses(pods)
    return bool(statuses) and all(c.get("ready") for c in statuses)


CRASHLOOP = Expectation(
    workload="payment-service",
    cause=[["DATABASE_URL"], ["missing", "not set", "unset", "absent", "undefined", "empty", "not defined"]],
    fix=[["DATABASE_URL"], ["env", "secret", "configmap"]],
)
IMAGE_PULL = Expectation(
    workload="web-frontend",
    cause=[
        ["this-tag-does-not-exist", "image tag", "tag"],
        ["not exist", "does not exist", "doesn't exist", "not found", "nonexistent", "non-existent",
         "invalid", "wrong", "incorrect", "manifest unknown"],
    ],
    fix=[["set image", "image:", "image tag", "tag", "nginx:"]],
)
OOM = Expectation(
    workload="analytics-worker",
    cause=[
        ["oom", "out of memory", "out-of-memory"],
        ["limit", "16mi", "insufficient memory", "not enough memory", "memory allocation"],
    ],
    fix=[["memory"], ["limit", "limits", "resources"]],
)
SELECTOR = Expectation(
    workload="orders-service",
    cause=[["selector", "label"], ["orders-api", "mismatch", "does not match", "doesn't match", "not match"]],
    fix=[["selector", "label"], ["orders-service", "orders-api"]],
)

READINESS = Expectation(
    workload="inventory-api",
    cause=[["readiness"], ["/healthz", "404"]],
    fix=[["/healthz", "readinessprobe", "readiness probe", "path"]],
)
PENDING = Expectation(
    workload="report-generator",
    cause=[["cpu"], ["insufficient", "request", "64", "capacity", "exceed"]],
    fix=[["cpu"], ["request"]],
)
MISSING_CONFIGMAP = Expectation(
    workload="notification-service",
    cause=[["notification-config"], ["not found", "missing", "does not exist", "doesn't exist", "nonexistent"]],
    fix=[["configmap"], ["create", "notification-config"]],
)
LIVENESS = Expectation(
    workload="search-service",
    cause=[["liveness"], ["8080"]],
    fix=[["liveness", "probe"], ["port"]],
)
SILENT_CRASH = Expectation(
    workload="legacy-batch",
    cause=[["exit", "crash", "terminat"]],
    fix=[["log", "command", "entrypoint", "debug", "investigat", "inspect"]],
    max_confidence=70,
)

SCENARIOS: "list[Scenario]" = [
    Scenario(
        id="crashloop",
        description="CrashLoopBackOff: missing DATABASE_URL env var",
        manifests=["01-crashloopbackoff.yaml"],
        ready=_any_waiting("CrashLoopBackOff"),
        expectations=[CRASHLOOP],
    ),
    Scenario(
        id="imagepull",
        description="ImagePullBackOff: nonexistent image tag",
        manifests=["02-imagepullbackoff.yaml"],
        ready=_any_waiting("ImagePullBackOff"),
        expectations=[IMAGE_PULL],
    ),
    Scenario(
        id="oomkilled",
        description="OOMKilled: 16Mi memory limit",
        manifests=["03-oomkilled.yaml"],
        ready=_oom_killed,
        expectations=[OOM],
    ),
    Scenario(
        id="selector",
        description="Service selector matches no pods",
        manifests=["04-selector-mismatch.yaml"],
        ready=_all_ready,
        expectations=[SELECTOR],
    ),
    Scenario(
        id="multi",
        description="All four failures at once (expects every one diagnosed)",
        manifests=[
            "01-crashloopbackoff.yaml",
            "02-imagepullbackoff.yaml",
            "03-oomkilled.yaml",
            "04-selector-mismatch.yaml",
        ],
        ready=lambda pods: (
            _any_waiting("CrashLoopBackOff")(pods)
            and _any_waiting("ImagePullBackOff")(pods)
            and _oom_killed(pods)
            and any(_all_ready([p]) for p in pods if p["metadata"]["name"].startswith("orders-service"))
        ),
        expectations=[CRASHLOOP, IMAGE_PULL, OOM, SELECTOR],
    ),
    Scenario(
        id="readiness",
        description="Readiness probe hits a 404 path; pod never Ready",
        manifests=["05-readiness-probe.yaml"],
        ready=_running_not_ready,
        settle_seconds=20,
        expectations=[READINESS],
    ),
    Scenario(
        id="pending",
        description="Pending: requests 64 CPUs",
        manifests=["06-pending-resources.yaml"],
        ready=_unschedulable,
        expectations=[PENDING],
    ),
    Scenario(
        id="configmap",
        description="CreateContainerConfigError: missing ConfigMap",
        manifests=["07-missing-configmap.yaml"],
        ready=_any_waiting("CreateContainerConfigError"),
        expectations=[MISSING_CONFIGMAP],
    ),
    Scenario(
        id="liveness",
        description="Liveness probe on the wrong port; restarted in a loop",
        manifests=["08-liveness-probe.yaml"],
        ready=_restarted_at_least(2),
        expectations=[LIVENESS],
    ),
    Scenario(
        id="silent-crash",
        description="Exits 1 with no logs — cause unknowable; confidence must be low",
        manifests=["09-silent-crash.yaml"],
        # Recent kubelets report terminated/Error between restarts rather
        # than waiting/CrashLoopBackOff, so wait on the restart count.
        ready=_restarted_at_least(2),
        expectations=[SILENT_CRASH],
    ),
    Scenario(
        id="healthy",
        description="Healthy control — any incident is a false alarm",
        manifests=["10-healthy.yaml"],
        ready=lambda pods: len(pods) >= 2 and _all_ready(pods),
        settle_seconds=10,
        expect_healthy=True,
    ),
]


def get(scenario_ids: "list[str] | None") -> "list[Scenario]":
    if not scenario_ids:
        return SCENARIOS
    by_id = {s.id: s for s in SCENARIOS}
    unknown = [i for i in scenario_ids if i not in by_id]
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}. Known: {', '.join(by_id)}")
    return [by_id[i] for i in scenario_ids]
