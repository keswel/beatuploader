from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.platform import PlatformProvider
from app.models.upload import UploadStatus


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0)
    targets: list[PlatformProvider] = Field(default_factory=list, min_length=1)
    title: str | None = None
    tags: list[str] | None = None
    bpm: int | None = Field(default=None, ge=20, le=400)
    music_key: str | None = Field(default=None, max_length=16)
    price_cents: int | None = Field(default=None, ge=0)
    # BeatStars license tier — 'AUTO' picks the highest tier the uploaded files support
    license_type: str | None = Field(default="AUTO", max_length=32)
    # BeatStars genre — must match one of their known values (autocomplete-only)
    genre: str | None = Field(default=None, max_length=64)
    # Per-upload YouTube description. If None, the user's template is rendered.
    description: str | None = Field(default=None, max_length=5000)


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    size_bytes: int
    progress: int
    status: UploadStatus
    targets: dict
    error: str | None
    created_at: datetime
    updated_at: datetime
    # Set by the API layer when the job has cover art on disk. Lets the client
    # construct the thumbnail URL: GET /api/uploads/{id}/artwork
    has_artwork: bool = False
