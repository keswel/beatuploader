import ssl
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _async_database_url(url: str) -> str:
    """Normalize an arbitrary Postgres/SQLite URL into one async SQLAlchemy accepts.

    Two things to fix:

    1. Driver. Render (and most managed Postgres providers) hand out
       `postgres://` or `postgresql://` URLs. The async engine needs an explicit
       `+asyncpg`; SQLite likewise needs `+aiosqlite`.

    2. SSL params. Render/Heroku/etc. append `?sslmode=require`. That's a libpq
       (sync psycopg2) keyword and asyncpg silently ignores it — meaning the
       connection succeeds without TLS, breaking your encrypted-in-transit
       expectation. Strip it from the URL and we let asyncpg's default SSL
       handling kick in (TLS for any non-localhost target).
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        # Drop sslmode / channel_binding / target_session_attrs etc. — these
        # are libpq parameters asyncpg doesn't understand.
        parts = urlsplit(url)
        q = parse_qs(parts.query, keep_blank_values=True)
        for k in ("sslmode", "channel_binding", "target_session_attrs", "gssencmode"):
            q.pop(k, None)
        url = urlunsplit(
            parts._replace(query=urlencode(q, doseq=True))
        )
        return url
    if url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    return url


_engine_kwargs: dict = {"echo": False, "future": True, "pool_pre_ping": True}

# asyncpg wants SSL configured via connect_args when talking to a remote DB.
# Two cases to handle:
#
#   1. Public hosts (Neon, Supabase, Render *external* URL) — verify normally.
#   2. Single-label hostnames like Render's internal `dpg-<id>-a` — these run
#      over Render's private network with self-signed certs. We want TLS
#      (asyncpg defaults to plaintext if ssl is unset) but verification fails.
#      Build a context that does TLS without verification.
#
# Localhost / 127.0.0.1 skip SSL entirely so dev keeps working without certs.
_db_url = _async_database_url(settings.database_url)
if _db_url.startswith("postgresql+asyncpg://"):
    _host = urlsplit(_db_url).hostname or ""
    if _host and _host not in ("localhost", "127.0.0.1"):
        if "." not in _host:
            # Internal/private hostname — self-signed cert is expected.
            _ssl_ctx = ssl.create_default_context()
            _ssl_ctx.check_hostname = False
            _ssl_ctx.verify_mode = ssl.CERT_NONE
            _engine_kwargs["connect_args"] = {"ssl": _ssl_ctx}
        else:
            _engine_kwargs["connect_args"] = {"ssl": True}

engine = create_async_engine(_db_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Run pending Alembic migrations against the configured database.

    Idempotent: re-running on an already-current DB is a no-op. We run on every
    boot because the Dockerfile is single-worker — for multi-worker deploys,
    move this out of startup and into a one-shot job (otherwise every worker
    races to grab the alembic version lock).
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))

    async with engine.begin() as conn:
        # Hand alembic the sync facade of our async connection. env.py picks it
        # up from cfg.attributes["connection"] and skips opening its own engine.
        def _upgrade(sync_conn) -> None:
            cfg.attributes["connection"] = sync_conn
            command.upgrade(cfg, "head")

        await conn.run_sync(_upgrade)
