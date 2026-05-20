"""Prune old BeatStars diagnostic dumps so they don't fill the disk.

`./storage/diagnostics/` accumulates a screenshot + HTML pair on every BeatStars
failure (selector drift, SMS challenge, bad creds). On a busy day that's tens
of MB; over months, gigabytes. We delete files older than `MAX_AGE_DAYS` at
app startup — cheap, no scheduler needed.

If you wanted continuous pruning between restarts, wrap _prune in an asyncio
task that sleeps 24h and loops. For our restart cadence, once-at-boot is fine.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_AGE_DAYS = 7


def prune_diagnostics() -> None:
    settings = get_settings()
    root = Path(settings.storage_dir) / "diagnostics"
    if not root.exists():
        return

    cutoff = time.time() - (MAX_AGE_DAYS * 86400)
    deleted = 0
    for path in root.iterdir():
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except OSError:
            # File gone between iterdir and stat/unlink (concurrent worker, etc.)
            # — not worth crashing startup over.
            continue
    if deleted:
        log.info("diagnostics cleanup: removed %d files older than %d days",
                 deleted, MAX_AGE_DAYS)
