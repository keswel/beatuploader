"""Google Sign-In flow that also grants YouTube upload scopes.

One OAuth round-trip creates/links a Beatuploader account AND saves a YouTube
PlatformConnection. The user clicks one button.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import jwt as jose_jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.platform import PlatformConnection, PlatformProvider, PlatformStatus
from app.models.user import User
from app.security import encrypt_token
from app.services.platforms.youtube import (
    YOUTUBE_AUTH_URL,
    YOUTUBE_SCOPES,
    YOUTUBE_TOKEN_URL,
)

SIGNIN_SCOPES = [
    "openid",
    "email",
    "profile",
    *YOUTUBE_SCOPES,
]


def _callback_url() -> str:
    settings = get_settings()
    return f"{settings.backend_base_url.rstrip('/')}/api/auth/google/callback"


def make_signin_state() -> str:
    """State for the sign-in flow. No user_id (we don't know who they are yet)."""
    settings = get_settings()
    payload = {
        "purpose": "signin",
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(seconds=settings.oauth_state_expire_seconds),
    }
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_signin_state(state: str) -> None:
    settings = get_settings()
    payload = jose_jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != "signin":
        raise ValueError("Wrong state purpose")


def authorize_url() -> tuple[str, str]:
    settings = get_settings()
    if not settings.youtube_client_id:
        raise RuntimeError("YOUTUBE_CLIENT_ID not set - can't run Google sign-in")
    state = make_signin_state()
    params = {
        "client_id": settings.youtube_client_id,
        "redirect_uri": _callback_url(),
        "response_type": "code",
        "scope": " ".join(SIGNIN_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{YOUTUBE_AUTH_URL}?{urlencode(params)}", state


async def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        res = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "redirect_uri": _callback_url(),
                "grant_type": "authorization_code",
            },
            timeout=30.0,
        )
    res.raise_for_status()
    return res.json()


def verify_id_token(id_token_str: str) -> dict[str, Any]:
    """Returns the decoded ID token claims (sub, email, email_verified, name, picture)."""
    settings = get_settings()
    return google_id_token.verify_oauth2_token(
        id_token_str,
        google_requests.Request(),
        settings.youtube_client_id,
    )


_HANDLE_ALLOWED = re.compile(r"[^a-zA-Z0-9_.\-]")


def _derive_handle_base(email: str, name: str | None) -> str:
    candidate = name or email.split("@", 1)[0]
    cleaned = _HANDLE_ALLOWED.sub("", candidate).strip("._-")
    cleaned = cleaned[:48] or "producer"
    return cleaned.lower()


async def _unique_handle(db: AsyncSession, base: str) -> str:
    handle = base
    suffix = 0
    while True:
        existing = await db.scalar(select(User).where(User.handle == handle))
        if existing is None:
            return handle
        suffix += 1
        handle = f"{base}{suffix}"


async def signin_or_create_user(
    db: AsyncSession, *, claims: dict[str, Any]
) -> User:
    """Auto-link by email per user's product decision.

    Google already verified the email (we check email_verified upstream of this
    function), so any user we touch here gets email_verified_at stamped. Either
    sets it on a freshly-created user or back-fills it on an existing one that
    happened to register via email/password first.
    """
    email: str = claims["email"]
    sub: str = claims["sub"]
    name: str | None = claims.get("name")
    now = datetime.now(UTC)

    # Match by google_sub first (fast path for returning users)
    user = await db.scalar(select(User).where(User.google_sub == sub))
    if user is not None:
        if user.email_verified_at is None:
            user.email_verified_at = now
            await db.commit()
            await db.refresh(user)
        return user

    # Auto-link by email
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None:
        user.google_sub = sub
        if user.email_verified_at is None:
            user.email_verified_at = now
        await db.commit()
        await db.refresh(user)
        return user

    # Create
    handle = await _unique_handle(db, _derive_handle_base(email, name))
    user = User(
        email=email,
        handle=handle,
        password_hash=None,
        google_sub=sub,
        email_verified_at=now,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def upsert_youtube_connection(
    db: AsyncSession,
    *,
    user: User,
    access_token: str,
    refresh_token: str | None,
    expires_in: int,
) -> None:
    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id,
            PlatformConnection.provider == PlatformProvider.youtube,
        )
    )
    if existing is None:
        existing = PlatformConnection(user_id=user.id, provider=PlatformProvider.youtube)
        db.add(existing)

    # Fetch channel name for account_label
    label: str | None = None
    async with httpx.AsyncClient() as client:
        ch = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
    if ch.is_success:
        items = ch.json().get("items") or []
        if items:
            label = items[0].get("snippet", {}).get("title")

    existing.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        existing.refresh_token_encrypted = encrypt_token(refresh_token)
    existing.expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    existing.account_label = label or "YouTube channel"
    existing.status = PlatformStatus.connected
    existing.last_error = None
    existing.connected_at = datetime.now(UTC)
    await db.commit()
