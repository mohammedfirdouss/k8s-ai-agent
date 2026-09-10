"""Investigation service.

This is the orchestrator: it will call the Kubernetes inspectors to
gather data, then hand that data to the AI agent for root-cause
analysis and fix recommendations. Placeholder for now.
"""


def run_investigation():
    """Run a full troubleshooting investigation.

    Planned flow:
    1. Gather cluster data (pods, logs, events, deployments, network).
    2. Build a prompt from that data.
    3. Ask the AI for a root cause and a suggested fix.
    4. Return an InvestigationResult.

    Not implemented yet.
    """
    raise NotImplementedError
