import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# On Windows, set the Proactor event loop policy BEFORE importing anything that
# might create a loop. Playwright launches Chromium as a subprocess, and the
# default Selector loop doesn't support subprocesses on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import hmac
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.db import init_db
from app.services.diagnostics_cleanup import prune_diagnostics

log = logging.getLogger(__name__)
settings = get_settings()


def _init_sentry() -> None:
    """Initialize Sentry if SENTRY_DSN is set. No-op otherwise.

    Late-imported so the dependency stays optional — `pip install sentry-sdk`
    isn't required to run the app, only to actually ship events upstream.
    """
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        log.warning(
            "SENTRY_DSN is set but sentry-sdk isn't installed. "
            "Run: pip install 'sentry-sdk[fastapi]'"
        )
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        # Don't sample traces unless explicitly asked — traces are noisy and
        # expensive on the free tier. Errors are the main value.
        traces_sample_rate=0.0,
        # Send PII-stripped events. The FastAPI integration auto-attaches
        # request URL/headers; turn off body capture in case any sensitive
        # payloads slip in (login passwords etc.).
        send_default_pii=False,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    log.info("Sentry initialized (environment=%s)", settings.sentry_environment)


_init_sentry()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Migrations on boot are safe in single-worker mode (Dockerfile default) but
    # would race the alembic version lock when scaled to multiple workers /
    # instances. Operators flip RUN_MIGRATIONS_ON_BOOT=false and run
    # `python -m app.migrate` as a pre-deploy job instead.
    if settings.run_migrations_on_boot:
        await init_db()
    else:
        log.info(
            "RUN_MIGRATIONS_ON_BOOT=false — skipping migrations. "
            "Ensure they were applied by a pre-deploy job."
        )
    # Best-effort: keep going if the prune fails.
    try:
        prune_diagnostics()
    except Exception:
        log.exception("diagnostics cleanup failed at startup")
    yield


app = FastAPI(
    title="Beatuploader API",
    version="0.0.1",
    lifespan=lifespan,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply baseline security response headers to every response.

    HSTS is only sent when DEBUG=False because dev runs over http://localhost
    and an HSTS pin from a self-signed/loopback origin can wedge browser state.
    Desktop (local) mode is plain-http loopback too, so it never sends HSTS.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Block MIME-sniffing so an attacker-uploaded artwork can't be served
        # as JS, etc.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Clickjacking protection — we have no need for the API to ever be
        # iframed.
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Don't leak full URLs (including query params) to third-party origins.
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        # Disable powerful browser features we don't use.
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), usb=(), payment=()",
        )
        if not settings.debug and not settings.local_mode:
            # 1-year HSTS, includeSubDomains. Prod only — see class docstring.
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


class LocalSessionMiddleware(BaseHTTPMiddleware):
    """Desktop-mode gate: only the app's own window may call the local API.

    1. Host must be our loopback origin — defeats DNS rebinding, where a
       hostile site re-points its own hostname at 127.0.0.1 to become
       "same-origin" with us.
    2. /api/* must carry the per-launch session token, which only reaches the
       app's own page (injected into index.html, unreadable cross-origin).

    OAuth callbacks are exempt from (2): the system browser lands on them
    without the token, and their signed `state` JWT is the credential.
    """

    _CALLBACKS = ("/api/platforms/youtube/callback", "/api/platforms/soundcloud/callback")

    async def dispatch(self, request: Request, call_next):
        port = settings.local_port
        if request.headers.get("host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return PlainTextResponse("Forbidden host", status_code=403)
        path = request.url.path
        if path.startswith("/api/") and path not in self._CALLBACKS:
            supplied = request.headers.get("x-beatuploader-session", "")
            if not hmac.compare_digest(supplied, settings.local_session_token):
                return PlainTextResponse("Unauthorized", status_code=401)
        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
if settings.local_mode:
    if not settings.local_session_token:
        raise RuntimeError("LOCAL_MODE requires LOCAL_SESSION_TOKEN (set by the desktop shell)")
    app.add_middleware(LocalSessionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe — always returns ok if the process is up.

    Use /health/ready instead if you need the DB checked too. Render's default
    health check hits /health; a failing DB shouldn't take the container down
    (the DB might recover and we want the request loop alive to retry).
    """
    return {"status": "ok"}


@app.get("/health/ready", tags=["meta"])
async def health_ready() -> dict:
    """Readiness probe — checks the DB is reachable.

    Use this for deploy gates / blue-green cutover so traffic doesn't shift
    to a container whose DB connection is broken.
    """
    from sqlalchemy import text

    from app.db import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        log.warning("readiness probe failed: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="database unreachable")
    return {"status": "ok"}


if settings.local_mode and settings.frontend_dist_dir:
    _dist = Path(settings.frontend_dist_dir).resolve()
    _index_html = (_dist / "index.html").read_text(encoding="utf-8").replace(
        "</head>",
        f'<meta name="beatuploader-session" content="{settings.local_session_token}"></head>',
        1,
    )

    @app.get("/{path:path}", include_in_schema=False)
    async def desktop_frontend(path: str):
        """Serve the built SPA. Real files as-is; every other path gets
        index.html (client-side routing) with the session token injected."""
        if path.startswith("api/"):
            return PlainTextResponse("Not found", status_code=404)
        if path:
            candidate = (_dist / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(_dist):
                return FileResponse(candidate)
        return HTMLResponse(_index_html, headers={"Cache-Control": "no-store"})
