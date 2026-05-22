"""Pytest fixtures.

Each test gets a fresh in-memory SQLite DB shared between every connection of
the *same* test (StaticPool) but isolated from other tests. We construct the
schema with `Base.metadata.create_all` rather than running Alembic — it's
faster and the migrations themselves should be tested separately.

The httpx AsyncClient uses ASGITransport so requests never hit the network.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator

# Force a dev-safe config BEFORE app modules import. The tests share the
# settings singleton with the running app and we don't want a developer's
# real .env (with prod-shaped secrets, real DB URL, etc.) to leak into them.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-long-enough-to-pass-validation-32+chars")
# Same valid dev Fernet key the app falls back to — silence the warning.
os.environ.setdefault(
    "TOKEN_ENCRYPTION_KEY", "ZGV2LW9ubHktY2hhbmdlLW1lLTMyLWJ5dGVzLWJhc2U="
)
os.environ.setdefault("SMTP_HOST", "")  # logs emails to stdout

# On Windows, force the proactor loop policy at module import — uvicorn does
# this in app.main but pytest invokes test code before main runs.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import rate_limit  # noqa: E402

# Importing the models package registers every table on Base.metadata. Without
# this, create_all is a no-op on freshly-imported test runs.
from app import models  # noqa: E402, F401


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """The auth limiters are module-level singletons shared by every test.
    Without resetting, running >5 registers in a row trips the per-minute cap
    and downstream tests get 429s. Wipe the in-memory hit dicts between tests.
    """
    for name in dir(rate_limit):
        obj = getattr(rate_limit, name)
        if isinstance(obj, rate_limit.RateLimiter):
            obj._hits.clear()
    yield


@pytest_asyncio.fixture
async def db_engine():
    """Per-test in-memory SQLite engine.

    StaticPool ensures every connection sees the same in-memory DB (without it,
    each new connection gets its own empty DB and create_all writes vanish).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """An httpx AsyncClient wired to the FastAPI app with a clean DB."""
    sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def valid_password() -> str:
    """A password that satisfies the server-side complexity policy."""
    return "Str0ng!Password"
