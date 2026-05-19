from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.platform import PlatformProvider, PlatformStatus


class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: PlatformProvider
    status: PlatformStatus
    account_label: str | None
    connected_at: datetime | None
    last_error: str | None


class PlatformOAuthStart(BaseModel):
    """Response from /platforms/{provider}/connect — frontend redirects user here."""

    authorize_url: str
    state: str


class PlatformOAuthCallback(BaseModel):
    code: str
    state: str


class BeatStarsCredentials(BaseModel):
    username: str
    password: str
