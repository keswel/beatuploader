"""Email verification token issuance and verification.

Same shape as password_reset.py: short-lived JWT with purpose="email_verify",
subject=user_id, and `iat`. Unlike reset tokens we don't need single-use
enforcement — once `email_verified_at` is set, the verify endpoint short-
circuits and re-verifying with the same link is a no-op.

The endpoint deliberately accepts re-verification rather than rejecting
already-verified accounts: it's a better UX for users who click an old link.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError
from jose import jwt as jose_jwt

from app.config import get_settings

_PURPOSE = "email_verify"


def issue_verify_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": _PURPOSE,
        "iat": now,
        "exp": now + timedelta(seconds=s.email_verify_expire_seconds),
    }
    return jose_jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_verify_token(token: str) -> int:
    """Return user_id for a valid verify token. Raises ValueError otherwise."""
    s = get_settings()
    try:
        payload = jose_jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired verification token") from exc
    if payload.get("purpose") != _PURPOSE:
        raise ValueError("Wrong token purpose")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Malformed token") from exc


def verify_link(frontend_base_url: str, token: str) -> str:
    """Compose the URL the user clicks to land on the verify page."""
    base = frontend_base_url.rstrip("/")
    return f"{base}/verify-email?token={token}"
