from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(32), default="free")
    # Optional YouTube description template. Supports placeholders:
    # {title} {bpm} {key} {tags} {beatstars_link}
    # Per-upload UploadJob.description overrides this when set.
    youtube_description_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    platforms: Mapped[list["PlatformConnection"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    uploads: Mapped[list["UploadJob"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    beats: Mapped[list["Beat"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
