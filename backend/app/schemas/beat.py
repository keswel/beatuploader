from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    bpm: int | None
    music_key: str | None
    tags: list[str]
    price_cents: int | None
    plays: int
    platform_statuses: dict
    released_at: datetime | None
    created_at: datetime
