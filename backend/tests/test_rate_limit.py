"""Rate-limiter tests.

What we're checking:
- The limiter keys off `request.client.host`. Behind a reverse proxy that's
  fed by uvicorn's --proxy-headers, which rewrites request.client to the
  X-Forwarded-For value. The rewrite itself is uvicorn's job (tested by
  uvicorn upstream); we just need to make sure our limiter uses
  request.client and not some other field, AND that two different IPs each
  get their own quota.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.services.rate_limit import RateLimiter, limit_dependency


@pytest.mark.asyncio
async def test_limiter_isolates_per_ip() -> None:
    """Different request.client.host values each get their own quota."""
    limiter = RateLimiter(max_requests=2, window_seconds=60, name="test")

    app = FastAPI()

    @app.get("/", dependencies=[Depends(limit_dependency(limiter))])
    async def hit() -> dict:
        return {"ok": True}

    # ASGITransport.client controls request.client — simulates what uvicorn
    # would set behind --proxy-headers (the real client IP, not the proxy).
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("1.2.3.4", 0)),
        base_url="http://test",
    ) as c_alice:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("5.6.7.8", 0)),
            base_url="http://test",
        ) as c_bob:
            # Alice uses both her hits.
            assert (await c_alice.get("/")).status_code == 200
            assert (await c_alice.get("/")).status_code == 200
            # Third request — limited.
            assert (await c_alice.get("/")).status_code == 429

            # Bob is unaffected — his bucket is empty.
            assert (await c_bob.get("/")).status_code == 200
            assert (await c_bob.get("/")).status_code == 200
            assert (await c_bob.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_limiter_uses_anonymous_when_client_missing() -> None:
    """If request.client is None (test setups without an explicit client tuple,
    or unusual ASGI setups), we fall back to a constant 'anonymous' bucket.
    Not great for production — that's why DEPLOY.md says run with --proxy-headers
    — but the limiter shouldn't crash.
    """
    limiter = RateLimiter(max_requests=1, window_seconds=60, name="anon-test")

    app = FastAPI()

    @app.get("/", dependencies=[Depends(limit_dependency(limiter))])
    async def hit() -> dict:
        return {"ok": True}

    # Default ASGITransport leaves request.client at None.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/")).status_code == 200
        # All anonymous requests share one bucket — second hit is limited.
        assert (await client.get("/")).status_code == 429


@pytest.mark.asyncio
async def test_429_includes_retry_after_header() -> None:
    """Honest clients should back off using Retry-After."""
    limiter = RateLimiter(max_requests=1, window_seconds=60, name="retry-test")

    app = FastAPI()

    @app.get("/", dependencies=[Depends(limit_dependency(limiter))])
    async def hit() -> dict:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("9.9.9.9", 0)),
        base_url="http://test",
    ) as client:
        await client.get("/")
        res = await client.get("/")
        assert res.status_code == 429
        assert "retry-after" in {k.lower() for k in res.headers}
