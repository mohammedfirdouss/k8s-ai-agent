"""In-memory investigation progress tracking.

Lets the frontend poll GET /investigate/progress while POST /investigate
runs, so users see live step-by-step status. Deliberately simple: one
investigation at a time, stored in module state — enough for this app,
no external dependencies.
"""

import threading

# Ordered steps of one investigation, matching the UI labels.
STEPS = [
    "Checking Pods",
    "Reading Logs",
    "Analyzing Events",
    "Inspecting Deployments",
    "Checking Networking",
    "AI Reasoning",
]

_lock = threading.Lock()
_state: dict = {"running": False, "steps": []}


def reset() -> None:
    """Start a fresh investigation: all steps pending."""
    with _lock:
        _state["running"] = True
        _state["steps"] = [{"name": name, "status": "pending"} for name in STEPS]


def start_step(name: str) -> None:
    """Mark one step as currently running."""
    _set_status(name, "running")


def finish_step(name: str) -> None:
    """Mark one step as done."""
    _set_status(name, "done")


def finish() -> None:
    """Mark the whole investigation as finished."""
    with _lock:
        _state["running"] = False


def snapshot() -> dict:
    """Current progress, safe to return from the API."""
    with _lock:
        return {"running": _state["running"], "steps": [dict(s) for s in _state["steps"]]}


def _set_status(name: str, status: str) -> None:
    with _lock:
        for step in _state["steps"]:
            if step["name"] == name:
                step["status"] = status
                return
