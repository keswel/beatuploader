"""Landing-page early-release signup."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.waitlist import WaitlistSignup


@pytest.mark.asyncio
async def test_join_stores_normalized_email_once(client, db_session) -> None:
    for addr in ("Producer@Example.com", "producer@example.com"):
        res = await client.post("/api/waitlist", json={"email": addr})
        assert res.status_code == 204
    rows = (await db_session.scalars(select(WaitlistSignup.email))).all()
    assert rows == ["producer@example.com"]


@pytest.mark.asyncio
async def test_join_rejects_invalid_email(client) -> None:
    res = await client.post("/api/waitlist", json={"email": "not-an-email"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_join_is_rate_limited(client) -> None:
    codes = [
        (await client.post("/api/waitlist", json={"email": f"u{i}@example.com"})).status_code
        for i in range(6)
    ]
    assert codes[:5] == [204] * 5
    assert codes[5] == 429


@pytest.mark.asyncio
async def test_count_reflects_unique_signups(client) -> None:
    assert (await client.get("/api/waitlist/count")).json() == {"count": 0}
    for addr in ("a@example.com", "b@example.com", "A@example.com"):
        await client.post("/api/waitlist", json={"email": addr})
    assert (await client.get("/api/waitlist/count")).json() == {"count": 2}
