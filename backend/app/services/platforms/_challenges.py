"""In-memory store for in-flight headless-login challenges that need user input.

When BeatStars (or any future headless provider) blocks our login on an SMS code
or similar interactive step, the worker thread holding the live Playwright
session parks on `code_queue.get()` while the API endpoint returns a
`challenge_id` to the frontend. The frontend then POSTs the code, which is put
on the queue, unblocking the worker so it can submit the code and finish the
login.

Thread-safe by design — the queue is the handoff between the asyncio side and
the Playwright thread. Challenges expire after `_TTL` to avoid leaking browsers.
"""

from __future__ import annotations

import asyncio
import queue
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

_TTL = timedelta(minutes=10)
_CANCEL_SENTINEL = object()


@dataclass
class BeatStarsChallenge:
    id: str
    user_id: int
    username: str
    created_at: datetime
    code_queue: queue.Queue[Any] = field(default_factory=lambda: queue.Queue(maxsize=1))
    sms_event: asyncio.Event = field(default_factory=asyncio.Event)
    sms_hint: str | None = None
    worker_task: asyncio.Task | None = None

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) - self.created_at > _TTL


_challenges: dict[str, BeatStarsChallenge] = {}
_lock = threading.Lock()


def create_challenge(*, user_id: int, username: str) -> BeatStarsChallenge:
    challenge = BeatStarsChallenge(
        id=secrets.token_urlsafe(16),
        user_id=user_id,
        username=username,
        created_at=datetime.now(UTC),
    )
    with _lock:
        _drop_expired_locked()
        _challenges[challenge.id] = challenge
    return challenge


def get_challenge(challenge_id: str) -> BeatStarsChallenge | None:
    with _lock:
        c = _challenges.get(challenge_id)
        if c is None:
            return None
        if c.expired:
            _challenges.pop(challenge_id, None)
            return None
        return c


def remove_challenge(challenge_id: str) -> None:
    with _lock:
        _challenges.pop(challenge_id, None)


def cancel_challenge(challenge_id: str) -> bool:
    """Signal the worker to abort. Returns True if the challenge existed."""
    with _lock:
        c = _challenges.get(challenge_id)
        if c is None:
            return False
    try:
        c.code_queue.put_nowait(_CANCEL_SENTINEL)
    except queue.Full:
        pass
    return True


def is_cancel_sentinel(value: Any) -> bool:
    return value is _CANCEL_SENTINEL


def _drop_expired_locked() -> None:
    expired = [k for k, v in _challenges.items() if v.expired]
    for k in expired:
        _challenges.pop(k, None)
