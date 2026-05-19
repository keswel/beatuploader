from pathlib import Path

from app.models.platform import PlatformConnection, PlatformProvider
from app.services.platforms.base import (
    AuthMethod,
    BeatMetadata,
    OAuthRedirect,
    PlatformConnector,
    UploadHandle,
    UploadProgress,
)


class SoundCloudConnector(PlatformConnector):
    provider = PlatformProvider.soundcloud
    method = AuthMethod.oauth
    display_name = "SoundCloud"

    async def start_authorize(self, *, user_id: int, redirect_uri: str) -> OAuthRedirect:
        raise NotImplementedError("SoundCloud OAuth start")

    async def complete_authorize(self, *, code: str, state: str, redirect_uri: str) -> dict:
        raise NotImplementedError("SoundCloud OAuth complete")

    async def disconnect(self, connection: PlatformConnection) -> None:
        return None

    async def upload(
        self,
        connection: PlatformConnection,
        *,
        file_path: Path,
        meta: BeatMetadata,
    ) -> UploadHandle:
        raise NotImplementedError("SoundCloud upload")

    async def poll(self, connection: PlatformConnection, handle: UploadHandle) -> UploadProgress:
        raise NotImplementedError("SoundCloud poll")
