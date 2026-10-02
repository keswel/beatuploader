# PyInstaller spec for the desktop sidecar (`beatuploader-backend.exe`).
#
# Build (from backend/, after `npm run build:desktop` in frontend/):
#   .venv\Scripts\pyinstaller desktop.spec --noconfirm
# Output: dist/beatuploader-backend/  — bundled by Tauri as a resource dir.
#
# onedir, not onefile: onefile re-extracts ~40MB to %TEMP% on every launch
# (slow cold start, and antivirus loves to flag it).

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
FRONTEND_DIST = ROOT.parent / "frontend" / "dist-desktop"
if not (FRONTEND_DIST / "index.html").exists():
    raise SystemExit("Build the desktop frontend first: cd frontend && npm run build:desktop")

GOOGLEAPI_DOCS = (
    Path(__import__("googleapiclient").__file__).parent / "discovery_cache" / "documents"
)

datas = [
    (str(FRONTEND_DIST), "frontend_dist"),
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / "alembic"), "alembic"),
    # Only the YouTube discovery doc — the full cache is ~70MB of other APIs.
    (str(GOOGLEAPI_DOCS / "youtube.v3.json"), "googleapiclient/discovery_cache/documents"),
]

hiddenimports = [
    *collect_submodules("app"),
    "aiosqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "alembic.op",
    "alembic.context",
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

excludes = [
    # Hosted-only: the desktop app uses the BeatStars HTTP transport, SQLite,
    # and no Sentry. Playwright alone would add ~100MB of Node driver.
    "playwright",
    "asyncpg",
    "sentry_sdk",
    "tkinter",
    "pytest",
]

a = Analysis(
    [str(ROOT / "app" / "desktop.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
# PyInstaller's googleapiclient hook bundles every discovery doc (~96MB).
# We only call YouTube; drop the rest.
_DOCS = "googleapiclient/discovery_cache/documents/"
a.datas = [
    d for d in a.datas
    if not d[0].replace("\\", "/").startswith(_DOCS) or d[0].endswith("youtube.v3.json")
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="beatuploader-backend",
    console=True,  # the shell spawns it with CREATE_NO_WINDOW; console keeps stdin/stdout sane
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="beatuploader-backend", upx=False)
