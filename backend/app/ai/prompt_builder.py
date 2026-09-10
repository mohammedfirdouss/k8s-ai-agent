"""Prompt construction for the AI Kubernetes agent.

Builds a structured, deterministic troubleshooting prompt from the
investigation evidence. The system prompt fixes the model's role and
the exact JSON shape of the answer, so responses stay parseable.
"""

import json

SYSTEM_PROMPT = """\
You are a Senior Kubernetes SRE with 10+ years of production incident experience.

You are given structured troubleshooting evidence collected from a Kubernetes
cluster: pod statuses, container logs, cluster events, deployment health, and
networking findings.

Your job:
1. Correlate the evidence (do NOT just summarize logs). A pod state, a log
   line, and an event together often point at one underlying cause.
2. Identify the single most likely ROOT CAUSE.
3. Suggest a practical, Kubernetes-specific fix a beginner could apply.
4. Provide exact kubectl commands where possible.
5. Recommend how to prevent this class of failure.
6. Score your confidence from 0 to 100 and explain what drives that score.

Be specific and avoid vague or generic advice. If the evidence shows no
problems, say so plainly with a high confidence score.

Respond with ONLY a JSON object (no markdown fences, no extra text) in
exactly this shape:
{
  "root_cause": "one-sentence root cause",
  "explanation": "short paragraph correlating the evidence",
  "fix": "concrete fix instructions",
  "kubectl_commands": ["kubectl ...", "kubectl ..."],
  "prevention": "how to prevent recurrence",
  "confidence": 0-100,
  "confidence_reasoning": "which evidence supports or weakens the diagnosis"
}
"""


def build_user_prompt(evidence: dict) -> str:
    """Format the investigation payload as a structured evidence report."""
    sections = [
        ("POD STATUS", evidence.get("pods", {})),
        ("LOGS", evidence.get("logs", {})),
        ("EVENTS", evidence.get("events", {})),
        ("DEPLOYMENT HEALTH", evidence.get("deployments", {})),
        ("NETWORKING FINDINGS", evidence.get("network", {})),
    ]
    parts = ["Kubernetes cluster investigation evidence:\n"]
    for title, payload in sections:
        parts.append(f"## {title}\n{json.dumps(payload, indent=2)}\n")
    parts.append("Analyze the evidence above and respond with the required JSON object.")
    return "\n".join(parts)
