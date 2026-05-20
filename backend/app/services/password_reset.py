"""Password-reset token issuance and verification.

Reset tokens are short-lived JWTs (~30 min) with purpose="pwd_reset", subject=
user_id, and `iat`. We deliberately reuse the JWT-revocation machinery from
deps.get_current_user: once the user actually changes their password,
`User.password_changed_at` advances past the token's `iat`, so the same token
can't be replayed to set the password again. No DB-side single-use tracking
required.

Forgot-password endpoint always returns the same 200, whether the email exists
or not, so we don't leak account existence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError
from jose import jwt as jose_jwt

from app.config import get_settings

_PURPOSE = "pwd_reset"


def issue_reset_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": _PURPOSE,
        "iat": now,
        "exp": now + timedelta(seconds=s.password_reset_expire_seconds),
    }
    return jose_jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_reset_token(token: str) -> tuple[int, datetime]:
    """Return (user_id, iat) for a valid reset token. Raises ValueError otherwise.

    Caller is responsible for checking iat against the user's
    password_changed_at to enforce single-use.
    """
    s = get_settings()
    try:
        payload = jose_jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired reset token") from exc
    if payload.get("purpose") != _PURPOSE:
        raise ValueError("Wrong token purpose")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Malformed token") from exc
    iat_raw = payload.get("iat")
    if iat_raw is None:
        raise ValueError("Malformed token")
    try:
        iat = datetime.fromtimestamp(int(iat_raw), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("Malformed token") from exc
    return user_id, iat


def reset_link(frontend_base_url: str, token: str) -> str:
    """Compose the frontend URL the user clicks to land on the reset page."""
    base = frontend_base_url.rstrip("/")
    return f"{base}/reset-password?token={token}"
