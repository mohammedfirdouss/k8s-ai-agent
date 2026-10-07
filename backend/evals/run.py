"""Run the diagnosis evals.

Offline (default): replay recorded kubectl fixtures through the real
inspectors and the configured LLM.

    python -m evals.run                          # all scenarios
    python -m evals.run -s crashloop -s oomkilled --repeat 3

Live: apply each scenario to a real cluster in its own namespace, wait for
the failure to develop, investigate, then clean up. --record refreshes the
fixtures from that run.

    python -m evals.run --live --context kind-k8s-ai-test --record

Run from the backend/ directory so backend/.env (OpenRouter settings) loads.
Every investigation scans the whole cluster, so use a dedicated test
cluster with nothing else broken in it.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.ai.agent import analyze
from app.ai.tools import prefetch_commands
from app.core.config import settings
from app.kubernetes.kubectl import Kubectl
from app.services.investigation import run_investigation
from app.services.progress import ProgressTracker
from evals import scenarios as scenario_defs
from evals.recording import RecordingKubectl, ReplayKubectl, fixture_path
from evals.scenarios import MANIFEST_DIR, Scenario
from evals.scoring import ScenarioScore, score

RESULTS_DIR = Path(__file__).resolve().parent / "results"
READY_TIMEOUT_SECONDS = 300
POLL_SECONDS = 3


def main() -> int:
    args = _parse_args()
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "WARNING")

    if not args.no_llm and not (settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL):
        print("OPENROUTER_API_KEY and OPENROUTER_MODEL must be set (backend/.env), or pass --no-llm.")
        return 2

    selected = scenario_defs.get(args.scenario)
    if args.live:
        _wait_for_healthy_baseline(Kubectl(args.context))

    results = []
    for scenario in selected:
        print(f"\n▶ {scenario.id}: {scenario.description}")
        collected = _collect_live(scenario, args) if args.live else _collect_replay(scenario)
        if collected is None:
            continue
        evidence, kube = collected
        if args.no_llm:
            print("  evidence collected (LLM skipped)")
            continue
        if isinstance(kube, ReplayKubectl):
            kube.strict = False
        for attempt in range(1, args.repeat + 1):
            misses_before = len(getattr(kube, "misses", []))
            started = time.monotonic()
            diagnosis = analyze(evidence, kube)
            latency = time.monotonic() - started
            result = score(scenario, diagnosis)
            misses = getattr(kube, "misses", [])[misses_before:]
            results.append({"score": result, "latency": latency, "diagnosis": diagnosis, "fixture_misses": misses})
            _print_attempt(result, attempt, args.repeat, latency, diagnosis)
            if misses:
                print(f"    note: {len(misses)} tool call(s) not in fixture: {', '.join(misses[:3])}")

    if not results:
        return 0
    pass_rate = _print_summary(results)
    _save(results, args)
    return 0 if pass_rate >= args.min_pass else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--scenario", action="append", help="scenario id (repeatable); default all")
    parser.add_argument("--live", action="store_true", help="run against a real cluster instead of fixtures")
    parser.add_argument("--context", help="kubeconfig context for --live")
    parser.add_argument("--record", action="store_true", help="with --live: save fixtures from this run")
    parser.add_argument("--repeat", type=int, default=1, help="LLM runs per scenario (measures variance)")
    parser.add_argument("--no-llm", action="store_true", help="only collect evidence (e.g. to record)")
    parser.add_argument("--no-tools", action="store_true", help="single-shot diagnosis without agent tool calls")
    parser.add_argument("--min-pass", type=float, default=0.0, help="exit 1 if pass rate is below this (0-1)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.no_tools:
        settings.AGENT_MAX_TOOL_CALLS = 0
    if args.record and not args.live:
        parser.error("--record requires --live")
    return args


# --- evidence collection ----------------------------------------------------


def _collect_replay(scenario: Scenario) -> "tuple[dict, Kubectl] | None":
    path = fixture_path(scenario.id)
    if not path.exists():
        print(f"  no fixture at {path.name} — record it with --live --record")
        return None
    kube = ReplayKubectl(path)
    return run_investigation(kube, ProgressTracker("eval")), kube


def _collect_live(scenario: Scenario, args: argparse.Namespace) -> "tuple[dict, Kubectl] | None":
    setup = Kubectl(args.context)
    ns = scenario.namespace
    _run_or_die(setup, ["create", "namespace", ns])
    try:
        for manifest in scenario.manifests:
            _run_or_die(setup, ["apply", "-n", ns, "-f", str(MANIFEST_DIR / manifest)])
        if not _wait_until_ready(setup, scenario):
            print(f"  failure state did not develop within {READY_TIMEOUT_SECONDS}s — skipped")
            return None
        kube = RecordingKubectl(args.context) if args.record else Kubectl(args.context)
        evidence = run_investigation(kube, ProgressTracker("eval"))
        if args.record:
            _prefetch_for_agent(kube, ns)
            kube.save(fixture_path(scenario.id))
            print(f"  recorded {fixture_path(scenario.id).name} ({len(kube.recorded)} commands)")
        return evidence, kube
    finally:
        setup.run(["delete", "namespace", ns, "--wait=true", "--timeout=120s"])


def _prefetch_for_agent(kube: RecordingKubectl, namespace: str) -> None:
    """Record every tool command the agent could run about this scenario."""
    objects: "dict[str, list[str]]" = {}
    for kind in ("pod", "deployment", "replicaset", "service", "endpoints", "configmap"):
        data, error = kube.run_json(["get", kind, "-n", namespace])
        if not error:
            objects[kind] = [item["metadata"]["name"] for item in data.get("items", [])]
    for command in prefetch_commands(objects, namespace):
        kube.run(command)
    nodes, error = kube.run_json(["get", "nodes"])
    for node in [] if error else nodes.get("items", []):
        kube.run(["describe", "node", node["metadata"]["name"]])
        kube.run(["get", "node", node["metadata"]["name"], "-o", "yaml"])


def _wait_until_ready(kube: Kubectl, scenario: Scenario) -> bool:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        data, error = kube.run_json(["get", "pods", "-n", scenario.namespace])
        if not error and scenario.ready(data.get("items", [])):
            if scenario.settle_seconds:
                time.sleep(scenario.settle_seconds)
            return True
        time.sleep(POLL_SECONDS)
    return False


def _wait_for_healthy_baseline(kube: Kubectl) -> None:
    """Every scenario assumes the rest of the cluster is healthy."""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while True:
        data, error = kube.run_json(["get", "pods", "-A"])
        if error:
            raise SystemExit(f"Cluster unreachable: {error}")
        leftovers = sorted({p["metadata"]["namespace"] for p in data["items"]
                            if p["metadata"]["namespace"].startswith("eval-")})
        if leftovers:
            raise SystemExit(f"Leftover eval namespaces: {', '.join(leftovers)} — delete them first")
        not_ready = [
            f'{p["metadata"]["namespace"]}/{p["metadata"]["name"]}'
            for p in data["items"]
            if not _pod_settled(p)
        ]
        if not not_ready:
            return
        if time.monotonic() > deadline:
            raise SystemExit(f"Cluster baseline is not healthy: {', '.join(not_ready)}")
        time.sleep(POLL_SECONDS)


def _pod_settled(pod: dict) -> bool:
    status = pod.get("status", {})
    if status.get("phase") == "Succeeded":
        return True
    return status.get("phase") == "Running" and all(
        c.get("ready") for c in status.get("containerStatuses", [])
    )


def _run_or_die(kube: Kubectl, args: "list[str]") -> None:
    result = kube.run(args)
    if not result.success:
        raise SystemExit(f"kubectl {' '.join(args)} failed: {result.error}")


# --- reporting ----------------------------------------------------------------


def _print_attempt(result: ScenarioScore, attempt: int, repeat: int, latency: float, diagnosis: dict) -> None:
    label = f"  run {attempt}/{repeat}" if repeat > 1 else " "
    verdict = "PASS" if result.passed else "FAIL"
    confidence = f"{result.confidence:.0f}%" if result.confidence is not None else "—"
    print(f"{label} {verdict}  coverage {result.coverage:.0%}  confidence {confidence}  {latency:.1f}s")
    if result.error:
        print(f"    error: {result.error}")
    if result.false_alarms:
        print(f"    ✗ {result.false_alarms} false alarm(s) on a healthy cluster")
    for e in result.expectations:
        if not e.passed:
            checks = (("workload", e.named_workload), ("cause", e.cause), ("fix", e.fix), ("calibration", e.calibrated))
            missing = [name for name, ok in checks if not ok]
            print(f"    ✗ {e.workload}: missing {', '.join(missing)}")
    if not result.passed and diagnosis.get("root_cause"):
        print(f"    root cause given: {diagnosis['root_cause']}")


# kubectl verbs that change the cluster, i.e. actually apply a fix.
FIX_VERBS = ("set ", "patch ", "create ", "apply ", "scale ", "rollout ", "label ", "annotate ", "delete ")


def _actionable_share(incidents: "list[dict]") -> "float | None":
    """Share of incidents with at least one command that applies a fix (not edit/get/describe/logs)."""
    if not incidents:
        return None
    def actionable(incident: dict) -> bool:
        return any(
            any(f"kubectl {verb}" in cmd for verb in FIX_VERBS) for cmd in incident.get("kubectl_commands") or []
        )
    return sum(actionable(i) for i in incidents) / len(incidents)


def _print_summary(results: "list[dict]") -> float:
    by_scenario: "dict[str, list[dict]]" = {}
    for r in results:
        by_scenario.setdefault(r["score"].scenario, []).append(r)

    print(f"\n{'scenario':<13} {'pass':>7} {'coverage':>9} {'confidence':>11} {'actionable':>11} {'tools':>6} {'latency':>8}")
    for scenario_id, runs in by_scenario.items():
        passes = sum(r["score"].passed for r in runs)
        coverage = statistics.mean(r["score"].coverage for r in runs)
        confidences = [r["score"].confidence for r in runs if r["score"].confidence is not None]
        confidence = f"{statistics.mean(confidences):.0f}%" if confidences else "—"
        latency = statistics.mean(r["latency"] for r in runs)
        actionable = _actionable_share([i for r in runs for i in r["diagnosis"].get("incidents", [])])
        actionable_text = f"{actionable:.0%}" if actionable is not None else "—"
        tool_calls = statistics.mean(len(r["diagnosis"].get("commands_run") or []) for r in runs)
        print(
            f"{scenario_id:<13} {passes:>3}/{len(runs):<3} {coverage:>9.0%} {confidence:>11} "
            f"{actionable_text:>11} {tool_calls:>6.1f} {latency:>7.1f}s"
        )

    pass_rate = sum(r["score"].passed for r in results) / len(results)
    mode = f"agent, up to {settings.AGENT_MAX_TOOL_CALLS} tool calls" if settings.AGENT_MAX_TOOL_CALLS else "single-shot"
    print(f"\nOverall: {pass_rate:.0%} of {len(results)} runs passed  (model: {settings.OPENROUTER_MODEL}, {mode})")
    return pass_rate


def _save(results: "list[dict]", args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{stamp}.json"
    path.write_text(json.dumps({
        "model": settings.OPENROUTER_MODEL,
        "mode": "live" if args.live else "replay",
        "max_tool_calls": settings.AGENT_MAX_TOOL_CALLS,
        "runs": [
            {**r["score"].to_dict(), "latency_seconds": round(r["latency"], 2), "diagnosis": r["diagnosis"]}
            for r in results
        ],
    }, indent=2) + "\n")
    print(f"Results saved to {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    sys.exit(main())
