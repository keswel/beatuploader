from app.models.platform import PlatformProvider
from app.services.platforms.base import PlatformConnector
from app.services.platforms.beatstars import BeatStarsConnector
from app.services.platforms.soundcloud import SoundCloudConnector
from app.services.platforms.youtube import YouTubeConnector

_REGISTRY: dict[PlatformProvider, PlatformConnector] = {
    PlatformProvider.youtube: YouTubeConnector(),
    PlatformProvider.soundcloud: SoundCloudConnector(),
    PlatformProvider.beatstars: BeatStarsConnector(),
}


def get_connector(provider: PlatformProvider) -> PlatformConnector:
    connector = _REGISTRY.get(provider)
    if connector is None:
        raise ValueError(f"No connector registered for provider: {provider}")
    return connector


def list_connectors() -> list[PlatformConnector]:
    return list(_REGISTRY.values())
