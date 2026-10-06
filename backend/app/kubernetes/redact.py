"""Secret redaction for evidence sent to the LLM.

Container logs and event messages regularly contain credentials:
connection strings, bearer tokens, API keys printed at startup. They are
scrubbed here before the evidence leaves the backend for a third-party
model. Patterns err on the side of over-redacting — a diagnosis never
needs the secret value itself, only that it is present or wrong.
"""

import re

REDACTED = "[REDACTED]"

# Opening group for "<secret-looking key name> <separator>" patterns.
_SECRET_KEY = (
    r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|"
    r"access[_-]?key|private[_-]?key)[A-Za-z0-9_.-]*"
)

_PATTERNS: "list[tuple[re.Pattern[str], str]]" = [
    # PEM private key blocks.
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
        REDACTED,
    ),
    # Credentials embedded in URLs: scheme://user:password@host
    (re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s:/@]+:)[^\s@/]+(@)"), r"\1" + REDACTED + r"\2"),
    # Authorization headers / bearer tokens.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    # JSON Web Tokens.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), REDACTED),
    # Well-known key formats.
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),  # AWS access key id
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), REDACTED),  # GitHub tokens
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),  # Slack tokens
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), REDACTED),  # OpenAI/Anthropic-style keys
    # key=value where the key name looks secret (env dumps, query strings).
    (re.compile(_SECRET_KEY + r"\"?\s*=\s*\"?)([^\s\"',;&]+)"), r"\1" + REDACTED),
    # key: value (YAML/JSON/log style). Only long, space-free values, so prose
    # like "token: expired" keeps its meaning for the diagnosis.
    (re.compile(_SECRET_KEY + r"\"?\s*:\s*\"?)([^\s\"',;&]{12,})"), r"\1" + REDACTED),
]


def redact(text: str) -> str:
    """Return `text` with likely secrets replaced by [REDACTED]."""
    if not text:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
