"""Request authentication against InsForge.

When INSFORGE_URL is configured, every protected route requires an
`Authorization: Bearer <access token>` header carrying an InsForge user
session. The token is checked by asking InsForge who it belongs to
(GET /api/auth/sessions/current); valid answers are cached briefly so a
polling frontend does not hit InsForge on every request.

When INSFORGE_URL is empty the app runs in local single-user mode and
these checks are skipped.
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Header, HTTPException, status
from loguru import logger

from app.core.config import settings

VERIFY_TIMEOUT_SECONDS = 10
# How long a verified token is trusted before asking InsForge again.
CACHE_TTL_SECONDS = 60

# User id used for ownership checks in local single-user mode.
LOCAL_USER_ID = "local"


@dataclass(frozen=True)
class AuthUser:
    """The caller of an API request."""

    id: str
    email: Optional[str] = None


_cache_lock = threading.Lock()
_cache: "dict[str, tuple[AuthUser, float]]" = {}


def auth_enabled() -> bool:
    """True when requests must carry an InsForge user token."""
    return bool(settings.INSFORGE_URL)


def get_current_user(authorization: Optional[str] = Header(default=None)) -> AuthUser:
    """FastAPI dependency: the authenticated caller, or 401."""
    if not auth_enabled():
        return AuthUser(id=LOCAL_USER_ID)

    token = _bearer_token(authorization)
    if token is None:
        raise _unauthorized("Missing bearer token. Sign in and try again.")

    cached = _cached_user(token)
    if cached is not None:
        return cached

    user = _verify_with_insforge(token)
    with _cache_lock:
        _cache[token] = (user, time.monotonic() + CACHE_TTL_SECONDS)
    return user


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _cached_user(token: str) -> Optional[AuthUser]:
    now = time.monotonic()
    with _cache_lock:
        # Drop expired entries so the cache cannot grow without bound.
        for key in [k for k, (_, expires) in _cache.items() if expires <= now]:
            del _cache[key]
        entry = _cache.get(token)
    return entry[0] if entry else None


def _verify_with_insforge(token: str) -> AuthUser:
    url = settings.INSFORGE_URL.rstrip("/") + "/api/auth/sessions/current"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.error("Could not reach InsForge to verify token: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unreachable. Try again shortly.",
        )

    if response.status_code in (401, 403):
        raise _unauthorized("Session expired or invalid. Sign in again.")
    if response.status_code != 200:
        logger.error("InsForge token check returned HTTP {}", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service error. Try again shortly.",
        )

    try:
        user = response.json().get("user") or {}
    except ValueError:
        user = {}
    if not user.get("id"):
        raise _unauthorized("Session expired or invalid. Sign in again.")
    return AuthUser(id=str(user["id"]), email=user.get("email"))


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
