import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PlatformProvider(str, enum.Enum):
    beatstars = "beatstars"
    youtube = "youtube"
    soundcloud = "soundcloud"
    spotify = "spotify"
    audiomack = "audiomack"
    bandcamp = "bandcamp"


class PlatformStatus(str, enum.Enum):
    connected = "connected"
    disconnected = "disconnected"
    error = "error"


class PlatformConnection(Base):
    __tablename__ = "platform_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[PlatformProvider] = mapped_column(Enum(PlatformProvider))
    status: Mapped[PlatformStatus] = mapped_column(
        Enum(PlatformStatus), default=PlatformStatus.disconnected
    )
    account_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For headless providers: encrypted JSON blob holding Playwright storage_state (cookies + localStorage)
    session_data_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="platforms")  # noqa: F821
