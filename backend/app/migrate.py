"""Standalone migration runner.

Run as `python -m app.migrate` from the `backend/` directory. Exits non-zero
on failure so deploy gates can read the exit code. Used by Render's
preDeployCommand and by multi-worker deploys where running migrations on app
boot would race the alembic version lock.

This shares the same DB-URL normalization (postgres:// → postgresql+asyncpg://,
sslmode stripping) as the running app so an operator doesn't have to remember
which scheme alembic specifically wants.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.db import init_db

log = logging.getLogger("app.migrate")


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Running alembic upgrade head...")
    await init_db()
    log.info("Migrations complete.")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except Exception:
        log.exception("Migration failed")
        sys.exit(1)
