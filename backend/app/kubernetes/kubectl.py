"""Safe kubectl command execution.

Every inspector goes through this module instead of calling subprocess
directly, so command building, timeouts, error handling, and logging
live in one place.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from app.core.config import settings

# Hard limit so a hanging kubectl call can never freeze an investigation.
KUBECTL_TIMEOUT_SECONDS = 30


@dataclass
class KubectlResult:
    """Structured result of one kubectl invocation."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)

    @property
    def error(self) -> str:
        """Concise error text for reporting.

        kubectl often prints many repeated client-go error lines; the last
        line ("The connection to the server ... was refused") is the
        human-readable summary, so report that one.
        """
        lines = [line for line in self.stderr.strip().splitlines() if line.strip()]
        return lines[-1] if lines else "kubectl command failed"


def run_kubectl(args: list[str]) -> KubectlResult:
    """Run a kubectl command and return a structured result.

    `args` are the arguments after `kubectl`, e.g. ["get", "pods", "-A"].
    Never raises on command failure — check `result.success` instead.
    """
    command = ["kubectl", *args]
    if settings.KUBECONFIG_PATH:
        command += ["--kubeconfig", settings.KUBECONFIG_PATH]

    logger.debug("Running: {}", " ".join(command))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=KUBECTL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.error("kubectl binary not found on PATH")
        return KubectlResult(success=False, stderr="kubectl is not installed or not on PATH", command=command)
    except subprocess.TimeoutExpired:
        logger.error("kubectl timed out after {}s: {}", KUBECTL_TIMEOUT_SECONDS, " ".join(command))
        return KubectlResult(success=False, stderr=f"kubectl timed out after {KUBECTL_TIMEOUT_SECONDS}s", command=command)

    if completed.returncode != 0:
        logger.warning("kubectl failed ({}): {}", completed.returncode, completed.stderr.strip())
        return KubectlResult(success=False, stdout=completed.stdout, stderr=completed.stderr, command=command)

    return KubectlResult(success=True, stdout=completed.stdout, stderr=completed.stderr, command=command)


def run_kubectl_json(args: list[str]) -> "tuple[Optional[dict], Optional[str]]":
    """Run a kubectl command with `-o json` and parse the output.

    Returns (parsed_json, None) on success or (None, error_message) on failure.
    """
    result = run_kubectl([*args, "-o", "json"])
    if not result.success:
        return None, result.error
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        logger.error("kubectl returned invalid JSON for: {}", " ".join(result.command))
        return None, "kubectl returned output that could not be parsed as JSON"
