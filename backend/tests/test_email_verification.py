"""Email verification flow.

The send_email service no-ops to stdout when SMTP_HOST is empty (conftest sets
this), so we don't need to mock SMTP — we just exercise the endpoints.
"""

from __future__ import annotations

import pytest

from app.services.email_verification import issue_verify_token

VALID = "Str0ng!Password"


@pytest.mark.asyncio
async def test_fresh_register_is_unverified(client) -> None:
    res = await client.post(
        "/api/auth/register",
        json={"email": "x@example.com", "handle": "xxx", "password": VALID},
    )
    assert res.status_code == 201
    assert res.json()["user"]["email_verified_at"] is None


@pytest.mark.asyncio
async def test_verify_email_token_stamps_user(client) -> None:
    reg = await client.post(
        "/api/auth/register",
        json={"email": "y@example.com", "handle": "yyy", "password": VALID},
    )
    user_id = reg.json()["user"]["id"]
    token = issue_verify_token(user_id)

    # Endpoint is unauthenticated — the token is the credential.
    res = await client.post("/api/auth/verify-email", json={"token": token})
    assert res.status_code == 204

    # User now has email_verified_at set.
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await client.get("/api/auth/me", headers=headers)
    assert me.json()["email_verified_at"] is not None


@pytest.mark.asyncio
async def test_verify_email_invalid_token(client) -> None:
    res = await client.post(
        "/api/auth/verify-email", json={"token": "not-a-jwt"}
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_verify_email_idempotent(client) -> None:
    """Clicking an old link after already verifying shouldn't error."""
    reg = await client.post(
        "/api/auth/register",
        json={"email": "z@example.com", "handle": "zzz", "password": VALID},
    )
    user_id = reg.json()["user"]["id"]
    token = issue_verify_token(user_id)

    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 204
    # Same token again — still succeeds (no-op on already-verified user).
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 204


@pytest.mark.asyncio
async def test_resend_when_already_verified(client) -> None:
    reg = await client.post(
        "/api/auth/register",
        json={"email": "w@example.com", "handle": "www", "password": VALID},
    )
    user_id = reg.json()["user"]["id"]
    token_jwt = reg.json()["access_token"]
    verify_token = issue_verify_token(user_id)
    await client.post("/api/auth/verify-email", json={"token": verify_token})

    res = await client.post(
        "/api/auth/resend-verification",
        headers={"Authorization": f"Bearer {token_jwt}"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "already_verified"


@pytest.mark.asyncio
async def test_resend_when_unverified(client) -> None:
    reg = await client.post(
        "/api/auth/register",
        json={"email": "u@example.com", "handle": "uuu", "password": VALID},
    )
    token_jwt = reg.json()["access_token"]

    res = await client.post(
        "/api/auth/resend-verification",
        headers={"Authorization": f"Bearer {token_jwt}"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "sent"
