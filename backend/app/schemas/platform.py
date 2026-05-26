from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.platform import PlatformProvider, PlatformStatus


class PlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: PlatformProvider
    status: PlatformStatus
    account_label: str | None
    connected_at: datetime | None
    last_error: str | None
    # False when the operator hasn't provisioned this connector's credentials
    # yet (e.g. SoundCloud before SOUNDCLOUD_CLIENT_ID is set). The UI shows
    # these as "Coming soon" instead of an erroring Connect button.
    configured: bool = True


class PlatformOAuthStart(BaseModel):
    """Response from /platforms/{provider}/connect — frontend redirects user here."""

    authorize_url: str
    state: str


class PlatformOAuthCallback(BaseModel):
    code: str = Field(max_length=2048)
    state: str = Field(max_length=2048)


class BeatStarsCredentials(BaseModel):
    # 254 is the max email length per RFC 5321; BeatStars uses email as username.
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class BeatStarsSmsSubmit(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=64)
    # SMS codes are typically 4-8 digits. Cap conservatively.
    code: str = Field(min_length=1, max_length=16)
