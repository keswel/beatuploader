from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Beat(Base):
    __tablename__ = "beats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    bpm: Mapped[int | None] = mapped_column(nullable=True)
    music_key: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_cents: Mapped[int | None] = mapped_column(nullable=True)

    # Aggregate counters refreshed by background jobs
    plays: Mapped[int] = mapped_column(BigInteger, default=0)

    # Per-platform status snapshot — see BeatPlatformStatus
    platform_statuses: Mapped[dict] = mapped_column(JSON, default=dict)

    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="beats")  # noqa: F821
    uploads: Mapped[list["UploadJob"]] = relationship(back_populates="beat")  # noqa: F821


class BeatPlatformStatus:
    """Allowed values inside Beat.platform_statuses[provider]."""

    live = "live"
    uploading = "uploading"
    failed = "failed"
    none = "none"
