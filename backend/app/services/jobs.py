from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.beat import Beat, BeatPlatformStatus
from app.models.platform import PlatformConnection, PlatformProvider, PlatformStatus
from app.models.upload import UploadJob, UploadStatus
from app.models.user import User
from app.schemas.upload import UploadCreate
from app.services.platforms import get_connector
from app.services.platforms.base import BeatMetadata

log = logging.getLogger(__name__)

# Hold references so asyncio doesn't garbage-collect in-flight tasks.
_in_flight: set[asyncio.Task] = set()

# Run order for upload targets. BeatStars must run before YouTube so its
# public_url can be substituted into {beatstars_link} in YouTube descriptions.
# Anything not listed runs after the known ones in alphabetical order.
_TARGET_ORDER = ["beatstars", "soundcloud", "spotify", "audiomack", "bandcamp", "youtube"]


def _target_sort_key(provider: str) -> tuple[int, str]:
    try:
        return (_TARGET_ORDER.index(provider), provider)
    except ValueError:
        return (len(_TARGET_ORDER), provider)


def _render_description(
    template: str | None,
    *,
    meta: BeatMetadata,
    beatstars_url: str | None,
) -> str | None:
    if not template:
        return None
    return template.format_map(
        _SafeFormatDict(
            title=meta.title,
            bpm=str(meta.bpm) if meta.bpm is not None else "",
            key=meta.music_key or "",
            tags=", ".join(meta.tags) if meta.tags else "",
            beatstars_link=beatstars_url or "",
        )
    )


class _SafeFormatDict(dict):
    """Leaves unknown {placeholders} in the rendered string instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def start_job(job_id: int, user_id: int, payload: UploadCreate) -> None:
    """Spawn the job in the running event loop. Returns immediately."""
    task = asyncio.create_task(_run_job(job_id, user_id, payload))
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


async def _run_job(job_id: int, user_id: int, payload: UploadCreate) -> None:
    try:
        await _process(job_id, user_id, payload)
    except Exception:
        log.exception("Job %s failed unexpectedly", job_id)
        # Mark failed in DB
        async with AsyncSessionLocal() as db:
            job = await db.get(UploadJob, job_id)
            if job is not None:
                job.status = UploadStatus.failed
                job.error = "Internal worker error"
                await db.commit()


async def _process(job_id: int, user_id: int, payload: UploadCreate) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(UploadJob, job_id)
        if job is None:
            log.warning("Job %s not found", job_id)
            return
        if not (
            job.storage_path or job.tagged_storage_path or job.stems_storage_path
        ):
            log.warning("Job %s has no files attached", job_id)
            job.status = UploadStatus.failed
            job.error = "No files attached"
            await db.commit()
            return

        job.status = UploadStatus.uploading
        await db.commit()

        # Master is optional — primary file falls through master → tagged → stems
        master_path = Path(job.storage_path) if job.storage_path else None
        tagged_path = Path(job.tagged_storage_path) if job.tagged_storage_path else None
        stems_path = Path(job.stems_storage_path) if job.stems_storage_path else None

        primary_path = master_path or tagged_path or stems_path
        if primary_path is None:
            job.status = UploadStatus.failed
            job.error = "No files attached"
            await db.commit()
            return

        artwork_path = (
            Path(job.artwork_storage_path) if job.artwork_storage_path else None
        )
        video_path = (
            Path(job.video_storage_path) if job.video_storage_path else None
        )
        meta = BeatMetadata(
            title=payload.title or job.filename,
            tags=payload.tags or [],
            bpm=payload.bpm,
            music_key=payload.music_key,
            price_cents=payload.price_cents,
            master_path=master_path,
            tagged_path=tagged_path,
            stems_path=stems_path,
            artwork_path=artwork_path,
            video_path=video_path,
            license_type=job.license_type,
            genre=job.genre,
        )

        # Load the user's saved YouTube description template (if any). Per-upload
        # job.description overrides this when set.
        user = await db.get(User, user_id)
        description_template = job.description or (
            user.youtube_description_template if user else None
        )

        # Snapshot targets — we'll mutate this and write back
        targets: dict = dict(job.targets or {})
        any_succeeded = False
        any_failed = False
        platform_statuses: dict[str, str] = {}
        first_public_url: str | None = None
        beatstars_url: str | None = None

        # Sort: BeatStars before YouTube so its URL can fill {beatstars_link}.
        ordered_providers = sorted(targets.keys(), key=_target_sort_key)
        for provider_str in ordered_providers:
            provider = PlatformProvider(provider_str)
            connector = get_connector(provider)

            # Find the user's connection for this provider
            connection = await db.scalar(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == user_id,
                    PlatformConnection.provider == provider,
                    PlatformConnection.status == PlatformStatus.connected,
                )
            )
            if connection is None:
                targets[provider_str] = {
                    "status": "failed",
                    "progress": 0,
                    "error": "Platform not connected",
                }
                platform_statuses[provider_str] = BeatPlatformStatus.failed
                any_failed = True
                continue

            targets[provider_str] = {"status": "uploading", "progress": 0}
            job.targets = dict(targets)
            await db.commit()

            # Render the description for this target. We re-render per-target
            # because {beatstars_link} only becomes available after BeatStars
            # succeeds — earlier targets see an empty link, YouTube (run last)
            # sees the real one.
            meta.description = _render_description(
                description_template, meta=meta, beatstars_url=beatstars_url
            )

            try:
                handle = await connector.upload(
                    connection, file_path=primary_path, meta=meta
                )
                targets[provider_str] = {
                    "status": "done",
                    "progress": 100,
                    "external_id": handle.external_id,
                    "public_url": handle.public_url,
                }
                platform_statuses[provider_str] = BeatPlatformStatus.live
                first_public_url = first_public_url or handle.public_url
                any_succeeded = True
                if provider == PlatformProvider.beatstars and handle.public_url:
                    beatstars_url = handle.public_url

                # Persist any fresh session/cookie state the connector captured
                # (BeatStars rotates cookies; keeping them current means next
                # upload skips re-login and the onboarding carousel).
                if handle.session_data is not None:
                    from app.security import encrypt_token
                    from app.services.platforms._browser import (
                        serialize_storage_state,
                    )

                    connection.session_data_encrypted = encrypt_token(
                        serialize_storage_state(handle.session_data)
                    )
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                log.exception("Upload to %s failed for job %s", provider, job_id)
                targets[provider_str] = {
                    "status": "failed",
                    "progress": 0,
                    "error": str(exc)[:500],
                }
                platform_statuses[provider_str] = BeatPlatformStatus.failed
                any_failed = True

            job.targets = dict(targets)
            await db.commit()

        # Final status — make sure latest target snapshot is persisted
        job.targets = dict(targets)
        if any_succeeded and not any_failed:
            job.status = UploadStatus.done
            job.progress = 100
        elif any_succeeded:
            job.status = UploadStatus.done  # partial success — still done overall
            job.progress = 100
        else:
            job.status = UploadStatus.failed
            job.error = "All targets failed"

        # Create a Beat record so it shows in Library
        if any_succeeded:
            beat = Beat(
                user_id=user_id,
                title=meta.title,
                bpm=meta.bpm,
                music_key=meta.music_key,
                tags=meta.tags,
                price_cents=meta.price_cents,
                plays=0,
                platform_statuses=platform_statuses,
                released_at=datetime.now(UTC),
            )
            db.add(beat)
            await db.flush()
            job.beat_id = beat.id

        await db.commit()
