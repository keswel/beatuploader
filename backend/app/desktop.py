"""Desktop sidecar entrypoint.

The Tauri shell (desktop/src-tauri) launches this — as the PyInstaller-built
`beatuploader-backend.exe` in a release, or `python -m app.desktop` in dev —
with:

  BEATUPLOADER_PORT     loopback port to bind (picked free by the shell)
  BEATUPLOADER_SESSION  per-launch API secret (see main.LocalSessionMiddleware)
  YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET   Google "Desktop app" OAuth client,
                        baked into the shell at build time

and keeps our stdin open. When the shell exits — even if it crashes — stdin
hits EOF and we exit too, so a backend is never orphaned holding the port or
the install dir's file locks (which would break the auto-updater).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path


def _bundle_dir() -> Path:
    # PyInstaller unpacks data files under sys._MEIPASS; in dev it's the repo.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _configure_env() -> None:
    port = os.environ.get("BEATUPLOADER_PORT")
    session = os.environ.get("BEATUPLOADER_SESSION")
    if not port or not session:
        sys.exit("app.desktop must be launched by the Beatuploader shell")

    os.environ["LOCAL_MODE"] = "true"
    os.environ["LOCAL_PORT"] = port
    os.environ["LOCAL_SESSION_TOKEN"] = session
    os.environ.setdefault("DEBUG", "false")
    os.environ.setdefault("BEATSTARS_USE_HTTP", "true")

    if not os.environ.get("FRONTEND_DIST_DIR"):
        bundled = _bundle_dir() / "frontend_dist"
        dev = _bundle_dir().parent / "frontend" / "dist-desktop"
        os.environ["FRONTEND_DIST_DIR"] = str(bundled if bundled.is_dir() else dev)


def _configure_logging(data_dir: Path) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _exit_when_parent_dies() -> None:
    def watch() -> None:
        try:
            while sys.stdin.read(1024):
                pass
        except Exception:
            pass
        os._exit(0)

    if sys.stdin is not None:
        threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()


def main() -> None:
    _configure_env()

    from app.config import get_settings

    settings = get_settings()
    _configure_logging(Path(settings.data_dir))
    _exit_when_parent_dies()

    import uvicorn

    from app.main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=settings.local_port,
        log_config=None,  # keep our file handler; uvicorn logs propagate to root
        access_log=False,
    )


if __name__ == "__main__":
    main()
