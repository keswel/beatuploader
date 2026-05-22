"""Alembic environment.

Schema source of truth is `app.models` — every model module must be imported
here (transitively via `app.models.__init__`) so its tables are registered on
`Base.metadata` before autogenerate compares it against the live DB.

DB URL comes from `app.config.get_settings()` at runtime, not from alembic.ini,
so this works the same in dev (sqlite+aiosqlite) and prod (postgresql+asyncpg)
without editing config files. The alembic.ini `sqlalchemy.url` is left blank.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import the app's Base + every model. The unused-import noqa is load-bearing —
# importing the package registers all tables on Base.metadata.
from app.config import get_settings
from app.db import Base, _async_database_url
from app import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the DB URL from app settings at runtime, overriding whatever (empty)
# value is in alembic.ini. Keeps secrets out of alembic.ini. The CLI path
# (`alembic upgrade head` from a shell) opens its own engine and needs an
# explicit async driver — normalize the URL the same way db.py does.
config.set_main_option(
    "sqlalchemy.url", _async_database_url(get_settings().database_url)
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render migrations as raw SQL (no DBAPI required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Detect column type changes (e.g. String(64) → String(128)) in
        # autogenerate. Default is conservative — for our small schema we want
        # the noisier behavior.
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    # App-startup path: db.init_db() opens an async engine, then hands us the
    # sync facade of one of its connections via config.attributes — reuse it
    # so we don't open a second pool. CLI path (`alembic upgrade head` from the
    # shell): no connection attached, build one ourselves.
    connection = config.attributes.get("connection", None)
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
