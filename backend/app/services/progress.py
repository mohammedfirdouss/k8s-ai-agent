"""In-memory investigation progress tracking.

Lets the frontend poll GET /investigations/{id}/progress while
POST /investigate runs, so users see live step-by-step status. Each
investigation gets its own tracker, owned by the user who started it, so
concurrent investigations never see or overwrite each other's progress.
Finished trackers are kept briefly for the final poll, then dropped.
"""

import threading
import time
from typing import Optional

# Ordered steps of one investigation, matching the UI labels.
STEPS = [
    "Checking Pods",
    "Reading Logs",
    "Analyzing Events",
    "Inspecting Deployments",
    "Checking Networking",
    "AI Reasoning",
]

# How long a finished investigation's progress stays queryable.
FINISHED_RETENTION_SECONDS = 600


class ProgressTracker:
    """Step-by-step progress of one investigation."""

    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.running = True
        self.finished_at: Optional[float] = None
        self._lock = threading.Lock()
        self._steps = [{"name": name, "status": "pending"} for name in STEPS]

    def start_step(self, name: str) -> None:
        """Mark one step as currently running."""
        self._set_status(name, "running")

    def finish_step(self, name: str) -> None:
        """Mark one step as done."""
        self._set_status(name, "done")

    def finish(self) -> None:
        """Mark the whole investigation as finished."""
        with self._lock:
            self.running = False
            self.finished_at = time.monotonic()

    def snapshot(self) -> dict:
        """Current progress, safe to return from the API."""
        with self._lock:
            return {"running": self.running, "steps": [dict(s) for s in self._steps]}

    def _set_status(self, name: str, status: str) -> None:
        with self._lock:
            for step in self._steps:
                if step["name"] == name:
                    step["status"] = status
                    return


_registry_lock = threading.Lock()
_registry: "dict[str, ProgressTracker]" = {}


class InvestigationIdInUse(Exception):
    """Raised when an investigation id is already tracked."""


def create(investigation_id: str, owner_id: str) -> ProgressTracker:
    """Register a fresh tracker for a new investigation."""
    with _registry_lock:
        _prune()
        if investigation_id in _registry:
            raise InvestigationIdInUse(investigation_id)
        tracker = ProgressTracker(owner_id)
        _registry[investigation_id] = tracker
        return tracker


def get(investigation_id: str, owner_id: str) -> Optional[ProgressTracker]:
    """The tracker for an investigation, if it exists and belongs to owner_id."""
    with _registry_lock:
        _prune()
        tracker = _registry.get(investigation_id)
    if tracker is None or tracker.owner_id != owner_id:
        return None
    return tracker


def _prune() -> None:
    """Drop finished trackers past their retention window (lock held)."""
    cutoff = time.monotonic() - FINISHED_RETENTION_SECONDS
    stale = [
        key
        for key, tracker in _registry.items()
        if tracker.finished_at is not None and tracker.finished_at < cutoff
    ]
    for key in stale:
        del _registry[key]
