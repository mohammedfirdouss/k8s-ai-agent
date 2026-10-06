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


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    manifests: "list[str]"
    # Called with the scenario namespace's pods (`kubectl get pods -o json`
    # items); True once the failure is ready to be investigated.
    ready: "Callable[[list[dict]], bool]"
    expectations: "list[Expectation]" = field(default_factory=list)

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
    cause=[["oom", "out of memory", "out-of-memory"], ["limit", "16mi"]],
    fix=[["memory"], ["limit", "limits", "resources"]],
)
SELECTOR = Expectation(
    workload="orders-service",
    cause=[["selector", "label"], ["orders-api", "mismatch", "does not match", "doesn't match", "not match"]],
    fix=[["selector", "label"], ["orders-service", "orders-api"]],
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
]


def get(scenario_ids: "list[str] | None") -> "list[Scenario]":
    if not scenario_ids:
        return SCENARIOS
    by_id = {s.id: s for s in SCENARIOS}
    unknown = [i for i in scenario_ids if i not in by_id]
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}. Known: {', '.join(by_id)}")
    return [by_id[i] for i in scenario_ids]
