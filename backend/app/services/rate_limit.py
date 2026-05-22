"""Tiny in-memory sliding-window rate limiter.

Suitable for single-process MVP. For multi-worker or multi-instance deploys,
swap for a Redis-backed limiter (slowapi + limits) — the in-memory dict here
isn't shared across processes, so each worker enforces the limit independently.

Each `RateLimiter` keeps a deque of hit timestamps per key. On every check it
drops timestamps older than `window_seconds` and refuses the request if the
remaining count is at or above `max_requests`. O(window-bound) per call;
fine at the request volumes a hosted auth endpoint sees.

Memory: the per-key deque is bounded by `max_requests`. We don't periodically
prune unused keys; under sustained abuse the dict grows with unique IPs. The
abuse cap is the limit itself — if you're getting hammered to OOM, you have a
bigger problem than this limiter and should put a real WAF in front.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: float, name: str):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Behind a reverse proxy you MUST run uvicorn with
    --proxy-headers (or equivalent) so request.client reflects the real source
    rather than the proxy. Fallback handles tests where client is None."""
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"


def limit_dependency(limiter: RateLimiter):
    """Build a FastAPI dependency that enforces `limiter` per client IP."""

    async def _check(request: Request) -> None:
        key = _client_ip(request)
        if not await limiter.check(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many requests. Try again in a minute."
                ),
                headers={"Retry-After": str(int(limiter.window_seconds))},
            )

    return _check


# ─── Limiter instances ──────────────────────────────────────────────────────
# Tune these conservatively. Honest users should never hit them; an attacker
# trying to brute-force a password should. Numbers below allow normal retry
# flows (mistyped password) but block credential stuffing.

# Auth: login is the highest-value brute-force target.
login_limiter = RateLimiter(max_requests=10, window_seconds=60, name="login")
register_limiter = RateLimiter(max_requests=5, window_seconds=60, name="register")
password_change_limiter = RateLimiter(
    max_requests=5, window_seconds=60, name="password_change"
)
# Password reset request — tight because each call queues an outbound email and
# is unauthenticated. Cap prevents using us as an email-bomb relay.
password_reset_request_limiter = RateLimiter(
    max_requests=3, window_seconds=300, name="password_reset_request"
)
# Reset confirm — looser because legitimate users may mistype a new password
# before getting it past the complexity check.
password_reset_confirm_limiter = RateLimiter(
    max_requests=10, window_seconds=300, name="password_reset_confirm"
)
google_start_limiter = RateLimiter(
    max_requests=20, window_seconds=60, name="google_start"
)
# Email-verification resends: a determined attacker hitting /resend-verification
# is trying to use us as a mail relay against a single recipient. Tight cap.
email_verify_resend_limiter = RateLimiter(
    max_requests=3, window_seconds=300, name="email_verify_resend"
)

# BeatStars: each call spins up a real Playwright browser — much tighter cap
# both to prevent abuse and to keep the box from OOMing.
beatstars_credentials_limiter = RateLimiter(
    max_requests=3, window_seconds=60, name="beatstars_credentials"
)
beatstars_sms_limiter = RateLimiter(
    max_requests=5, window_seconds=60, name="beatstars_sms"
)
