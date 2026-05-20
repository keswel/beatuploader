from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

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
