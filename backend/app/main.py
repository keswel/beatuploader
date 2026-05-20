import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# On Windows, set the Proactor event loop policy BEFORE importing anything that
# might create a loop. Playwright launches Chromium as a subprocess, and the
# default Selector loop doesn't support subprocesses on Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
    await init_db()
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
        if not settings.debug:
            # 1-year HSTS, includeSubDomains. Prod only — see class docstring.
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)
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
    return {"status": "ok"}
