from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.models.platform import PlatformConnection, PlatformProvider


class AuthMethod(str, enum.Enum):
    oauth = "oauth"
    api_key = "api_key"
    headless = "headless"  # username/password via browser automation


@dataclass
class OAuthRedirect:
    authorize_url: str
    state: str


@dataclass
class UploadHandle:
    """Returned after kicking off an upload — used to poll status.

    For headless connectors, `session_data` carries the post-upload storage_state
    so the caller can write it back to the PlatformConnection. This means the
    next upload reuses warm cookies (skips BeatStars's onboarding carousel,
    keeps the session "trusted" for longer, etc.). Opaque to the API layer.
    """

    external_id: str
    public_url: str | None = None
    session_data: dict | None = None


@dataclass
class UploadProgress:
    progress: int  # 0–100
    status: str  # 'uploading' | 'done' | 'failed'
    error: str | None = None
    public_url: str | None = None


@dataclass
class BeatMetadata:
    title: str
    tags: list[str]
    bpm: int | None
    music_key: str | None
    price_cents: int | None
    # Original file paths by role — ALL optional, set by the job processor
    # based on what the user uploaded. Connectors should use these to decide
    # which slots/licenses are eligible. `file_path` (positional arg on
    # PlatformConnector.upload) is the "primary" file chosen by the processor
    # for connectors that only handle a single audio file (like YouTube).
    master_path: "Path | None" = None  # noqa: F821
    tagged_path: "Path | None" = None  # noqa: F821
    stems_path: "Path | None" = None  # noqa: F821
    artwork_path: "Path | None" = None  # noqa: F821 — cover art (PNG/JPG)
    video_path: "Path | None" = None  # noqa: F821 — MP4/MOV/WEBM, YouTube only
    # 'AUTO' | 'EXCLUSIVE' | 'PREMIUM_PLUS' | 'PREMIUM' | 'UNLIMITED' | None
    license_type: str | None = None
    # User-picked genre label (e.g. "Hip Hop", "Trap"). Must match BeatStars's enum.
    genre: str | None = None
    # Pre-rendered YouTube description. Job processor handles template substitution
    # (including {beatstars_link}) before passing here.
    description: str | None = None


class PlatformConnector(ABC):
    """Each upload target implements this contract. The API layer is provider-agnostic."""

    provider: PlatformProvider
    method: AuthMethod
    display_name: str

    @abstractmethod
    async def start_authorize(self, *, user_id: int, redirect_uri: str) -> OAuthRedirect:
        """Begin connection flow. For OAuth: return authorize URL + state."""

    @abstractmethod
    async def complete_authorize(
        self, *, code: str, state: str, redirect_uri: str
    ) -> dict:
        """Exchange code for tokens. Returns dict to persist on PlatformConnection."""

    @abstractmethod
    async def disconnect(self, connection: PlatformConnection) -> None:
        """Revoke tokens on the platform side if supported."""

    @abstractmethod
    async def upload(
        self,
        connection: PlatformConnection,
        *,
        file_path: Path,
        meta: BeatMetadata,
    ) -> UploadHandle:
        """Kick off an upload. Should not block on completion — return a handle."""

    @abstractmethod
    async def poll(self, connection: PlatformConnection, handle: UploadHandle) -> UploadProgress:
        """Poll status of an in-flight upload."""
