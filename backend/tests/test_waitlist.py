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
async def test_repeat_signup_looks_like_a_new_one(client) -> None:
    first = await client.post("/api/waitlist", json={"email": "dup@example.com"})
    again = await client.post("/api/waitlist", json={"email": "DUP@example.com"})
    assert (first.status_code, first.content) == (again.status_code, again.content) == (204, b"")


@pytest.mark.asyncio
async def test_count_is_rounded_down_and_ignores_duplicates(client, db_session) -> None:
    assert (await client.get("/api/waitlist/count")).json() == {"count": 0}
    # Insert directly so the signup rate limit doesn't get in the way.
    db_session.add_all(WaitlistSignup(email=f"u{i}@example.com") for i in range(7))
    await db_session.commit()
    assert (await client.get("/api/waitlist/count")).json() == {"count": 5}
    await client.post("/api/waitlist", json={"email": "U0@example.com"})  # duplicate
    assert (await client.get("/api/waitlist/count")).json() == {"count": 5}
