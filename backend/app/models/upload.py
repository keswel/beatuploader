import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UploadStatus(str, enum.Enum):
    queued = "queued"
    uploading = "uploading"
    done = "done"
    failed = "failed"


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    beat_id: Mapped[int | None] = mapped_column(
        ForeignKey("beats.id", ondelete="SET NULL"), nullable=True, index=True
    )

    filename: Mapped[str] = mapped_column(String(512))
    # storage_path = master file (required, typically WAV)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Optional companion files. tagged = preview MP3, stems = ZIP/RAR of project stems
    tagged_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    stems_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    progress: Mapped[int] = mapped_column(default=0)
    status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus), default=UploadStatus.queued)

    # Which BeatStars license tier to enable. 'AUTO' = highest tier the files support.
    # Other values: EXCLUSIVE | PREMIUM_PLUS | PREMIUM | UNLIMITED | None (no license)
    license_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default="AUTO")

    # User-supplied genre. BeatStars's genre field is autocomplete-only — must
    # match one of their known values (e.g. "Hip Hop", "Trap", "R&B").
    genre: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Cover art path (PNG/JPG). Optional but improves listing appearance.
    artwork_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Which platforms this upload targets, plus per-platform state
    targets: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Original UploadCreate payload (title, tags, bpm, etc.) serialized as JSON.
    # Lets retry re-run a failed job without the client having to resubmit metadata.
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="uploads")  # noqa: F821
    beat: Mapped["Beat | None"] = relationship(back_populates="uploads")  # noqa: F821
