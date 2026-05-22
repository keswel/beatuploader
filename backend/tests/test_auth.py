"""End-to-end tests for the auth endpoints.

These hit the real router through the FastAPI ASGI app with a fresh in-memory
SQLite per test. Rate-limit dependencies still run — fine here because each
test starts with a clean process-local limiter state via the AsyncClient
shared session, well under the per-minute caps.
"""

from __future__ import annotations

import asyncio

import pytest

VALID = "Str0ng!Password"
NEW_VALID = "An0ther!Password"


@pytest.mark.asyncio
async def test_register_then_me(client) -> None:
    res = await client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "handle": "alice", "password": VALID},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    token = body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["handle"] == "alice"
    assert body["user"]["plan"] == "free"

    # The token from register should authenticate /me.
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_register_login_roundtrip(client) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "handle": "bob", "password": VALID},
    )
    res = await client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": VALID},
    )
    assert res.status_code == 200, res.text
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "carol@example.com", "handle": "carol", "password": VALID},
    )
    res = await client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "WrongPass1!"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client) -> None:
    res = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": VALID},
    )
    # Same status as wrong-password so the response shape can't be used to
    # enumerate registered emails.
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_register_returns_409(client) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "handle": "dave", "password": VALID},
    )
    res = await client.post(
        "/api/auth/register",
        json={"email": "dave@example.com", "handle": "dave2", "password": VALID},
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_me_rejects_missing_token(client) -> None:
    res = await client.get("/api/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_garbage_token(client) -> None:
    res = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_change_password_revokes_old_jwt(client) -> None:
    """Changing a password must invalidate all previously-issued JWTs."""
    reg = await client.post(
        "/api/auth/register",
        json={"email": "eve@example.com", "handle": "eve", "password": VALID},
    )
    old_token = reg.json()["access_token"]
    headers_old = {"Authorization": f"Bearer {old_token}"}

    # The iat→changed_at check rounds to whole seconds (see deps.get_current_user).
    # Without this sleep, register + change-password land in the same second and
    # the token would still validate. Realistically there's always >1s between
    # actions — the sleep just forces the comparison off the slack boundary.
    await asyncio.sleep(1.1)

    res = await client.post(
        "/api/auth/change-password",
        json={"current_password": VALID, "new_password": NEW_VALID},
        headers=headers_old,
    )
    assert res.status_code == 204

    # The old token is now stale — password_changed_at moved past its iat.
    me = await client.get("/api/auth/me", headers=headers_old)
    assert me.status_code == 401

    # A fresh login with the new password works.
    login = await client.post(
        "/api/auth/login",
        json={"email": "eve@example.com", "password": NEW_VALID},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current(client) -> None:
    reg = await client.post(
        "/api/auth/register",
        json={"email": "frank@example.com", "handle": "frank", "password": VALID},
    )
    token = reg.json()["access_token"]
    res = await client.post(
        "/api/auth/change-password",
        json={"current_password": "Wrong!Pass1", "new_password": NEW_VALID},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
