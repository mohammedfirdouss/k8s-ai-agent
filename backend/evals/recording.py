"""Record and replay raw kubectl output.

Fixtures store what kubectl printed for every command an investigation ran,
keyed by its arguments. Replaying them runs the real inspectors offline, so
inspector changes are evaluated too. A command missing from a fixture fails
loudly: the inspectors changed what they ask for, so re-record.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.kubernetes.kubectl import Kubectl, KubectlResult

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
# Fixture key holding when it was recorded (not a kubectl command).
RECORDED_AT_KEY = "__recorded_at__"


def _key(args: "list[str]") -> str:
    return " ".join(args)


class RecordingKubectl(Kubectl):
    """Runs kubectl for real and remembers every result."""

    def __init__(self, context: Optional[str] = None):
        super().__init__(context)
        self.recorded: "dict[str, dict]" = {}
        self.recorded_at = super().now()

    def now(self) -> datetime:
        return self.recorded_at

    def run(self, args: "list[str]") -> KubectlResult:
        result = super().run(args)
        self.recorded[_key(args)] = {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        return result

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {RECORDED_AT_KEY: self.recorded_at.isoformat(), **self.recorded}
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


class MissingFixture(Exception):
    """An investigation ran a command the fixture has no recording of."""


class ReplayKubectl(Kubectl):
    """Answers kubectl commands from a recorded fixture."""

    def __init__(self, path: Path):
        super().__init__(None)
        self.path = path
        data = json.loads(path.read_text())
        self.recorded_at = datetime.fromisoformat(data.pop(RECORDED_AT_KEY))
        self.recorded: "dict[str, dict]" = data

    def now(self) -> datetime:
        # Replays see the cluster as it was when recorded.
        return self.recorded_at

    def run(self, args: "list[str]") -> KubectlResult:
        entry = self.recorded.get(_key(args))
        if entry is None:
            raise MissingFixture(
                f"{self.path.name} has no recording of `kubectl {_key(args)}`. "
                "Re-record with: python -m evals.run --live --record"
            )
        return KubectlResult(command=["kubectl", *args], **entry)


def fixture_path(scenario_id: str) -> Path:
    return FIXTURE_DIR / f"{scenario_id}.json"
