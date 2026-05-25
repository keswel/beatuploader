"""Shared Playwright browser helpers for headless providers (BeatStars, Bandcamp, etc.).

Uses the **sync** Playwright API offloaded to a thread via asyncio.to_thread.
Async Playwright doesn't work cleanly under uvicorn on Windows (it relies on
ProactorEventLoop for subprocesses, but uvicorn sets the Selector policy on
Windows for socket I/O). Sync-in-a-thread sidesteps the whole issue.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from playwright.sync_api import Browser, BrowserContext, sync_playwright

# Cap concurrent browsers. Each Chromium uses ~300MB RAM.
_browser_semaphore = threading.Semaphore(3)

# Realistic UA — default 'HeadlessChrome' triggers bot detection.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

T = TypeVar("T")


@contextmanager
def browser_session(
    *,
    storage_state: dict[str, Any] | None = None,
    headless: bool = True,
) -> Iterator[tuple[Browser, BrowserContext]]:
    """Yield a Playwright Browser + Context with anti-detection basics applied.

    Restore a saved session by passing storage_state (cookies + localStorage).
    Capture the current state after the operation with context.storage_state().
    """
    with _browser_semaphore, sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                # Footprint-reduction flags for containerized Chromium. These
                # are safe and standard for headless scrapes.
                #   --disable-dev-shm-usage: Docker gives /dev/shm only 64MB;
                #     this routes shared memory to /tmp instead so Chromium
                #     doesn't crash/balloon when it fills. Most important one.
                #   The rest disable subsystems we never use headless.
                # NOTE: --single-process/--no-zygote were tried here to fit
                # Render's 512MB free tier but made BeatStars' heavy Angular
                # SPA hang on 0.1 CPU. Removed — the real fix is a >=1GB host.
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        try:
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1366, "height": 800},
                locale="en-US",
                storage_state=storage_state,
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            try:
                yield browser, context
            finally:
                context.close()
        finally:
            browser.close()


def run_in_browser(fn: Callable[[BrowserContext], T], **kwargs: Any) -> T:
    """Convenience: run a function inside a browser_session and return its result."""
    with browser_session(**kwargs) as (_, ctx):
        return fn(ctx)


def serialize_storage_state(state: dict[str, Any]) -> str:
    return json.dumps(state)


def deserialize_storage_state(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return json.loads(raw)
