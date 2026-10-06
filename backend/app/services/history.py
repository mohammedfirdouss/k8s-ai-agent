"""Investigation history persistence (InsForge).

The backend, not the browser, writes history rows: it uses the server-only
InsForge admin key and stamps each row with the verified user's id, so
users cannot forge entries. Users can only read their own rows (RLS).

Saving is best-effort: a history failure is logged but never fails the
investigation itself.
"""

from typing import Optional

import httpx
from loguru import logger

from app.core.auth import AuthUser, auth_enabled
from app.core.config import settings

SAVE_TIMEOUT_SECONDS = 10


def history_enabled() -> bool:
    """True when investigations can be persisted to InsForge."""
    return auth_enabled() and bool(settings.INSFORGE_API_KEY)


def save_investigation(
    investigation_id: str,
    user: AuthUser,
    context: Optional[str],
    status: str,
    diagnosis: dict,
) -> bool:
    """Insert one history row. Returns True when it was saved."""
    if not history_enabled():
        return False

    row = {
        "id": investigation_id,
        "user_id": user.id,
        "cluster_context": context,
        "status": status,
        "root_cause": diagnosis.get("root_cause"),
        "confidence": diagnosis.get("confidence"),
        "diagnosis": diagnosis,
    }
    url = settings.INSFORGE_URL.rstrip("/") + "/api/database/records/investigations"
    try:
        response = httpx.post(
            url,
            json=[row],
            headers={"Authorization": f"Bearer {settings.INSFORGE_API_KEY}"},
            timeout=SAVE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("Could not save investigation {} to history: {}", investigation_id, exc)
        return False

    if response.status_code >= 300:
        logger.warning(
            "Saving investigation {} to history failed: HTTP {} {}",
            investigation_id,
            response.status_code,
            response.text[:200],
        )
        return False
    return True
