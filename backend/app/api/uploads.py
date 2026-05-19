from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import desc, select

from app.deps import CurrentUser, DbSession
from app.models.upload import UploadJob, UploadStatus
from app.schemas.upload import UploadCreate, UploadOut
from app.services.jobs import start_job
from app.services.storage import remove_upload, save_upload

log = logging.getLogger(__name__)
router = APIRouter(prefix="/uploads", tags=["uploads"])


def _serialize(job: UploadJob) -> UploadOut:
    """Convert UploadJob → UploadOut, deriving fields that aren't on the model."""
    out = UploadOut.model_validate(job)
    out.has_artwork = bool(job.artwork_storage_path)
    return out


def _parse_metadata(raw: str) -> UploadCreate:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid metadata JSON: {exc}",
        ) from exc
    try:
        return UploadCreate.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def create_upload(
    user: CurrentUser,
    db: DbSession,
    metadata: Annotated[str, Form(description="JSON-encoded UploadCreate payload")],
    master: Annotated[
        UploadFile | None,
        File(description="Optional master file (WAV/FLAC). Required for Premium+"),
    ] = None,
    tagged: Annotated[
        UploadFile | None,
        File(description="MP3 preview. Required for Basic license"),
    ] = None,
    stems: Annotated[
        UploadFile | None,
        File(description="Stems (ZIP/RAR). Required for Exclusive"),
    ] = None,
    artwork: Annotated[
        UploadFile | None,
        File(description="Cover art (PNG/JPG). Optional."),
    ] = None,
    video: Annotated[
        UploadFile | None,
        File(description="Video file (MP4/MOV/WEBM). YouTube only. Optional."),
    ] = None,
) -> UploadOut:
    payload = _parse_metadata(metadata)

    # At least one file must be present
    if (master is None or not master.filename) and (
        tagged is None or not tagged.filename
    ) and (stems is None or not stems.filename) and (video is None or not video.filename):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of master / tagged / stems must be provided",
        )

    # Pick a filename for the job — prefer master, then tagged, then stems
    filename = (
        (master.filename if master and master.filename else None)
        or (tagged.filename if tagged and tagged.filename else None)
        or (stems.filename if stems and stems.filename else None)
        or payload.filename
    )

    job = UploadJob(
        user_id=user.id,
        filename=filename,
        size_bytes=0,
        status=UploadStatus.queued,
        targets={t.value: {"status": "queued", "progress": 0} for t in payload.targets},
        license_type=payload.license_type,
        genre=payload.genre,
        description=payload.description,
        payload_json=payload.model_dump(mode="json"),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    total_bytes = 0
    try:
        if master is not None and master.filename:
            master_path, w = await save_upload(user.id, job.id, master, role="master")
            job.storage_path = str(master_path)
            total_bytes += w
        if tagged is not None and tagged.filename:
            tagged_path, w = await save_upload(user.id, job.id, tagged, role="tagged")
            job.tagged_storage_path = str(tagged_path)
            total_bytes += w
        if stems is not None and stems.filename:
            stems_path, w = await save_upload(user.id, job.id, stems, role="stems")
            job.stems_storage_path = str(stems_path)
            total_bytes += w
        if artwork is not None and artwork.filename:
            artwork_path, w = await save_upload(user.id, job.id, artwork, role="artwork")
            job.artwork_storage_path = str(artwork_path)
            total_bytes += w
        if video is not None and video.filename:
            video_path, w = await save_upload(user.id, job.id, video, role="video")
            job.video_storage_path = str(video_path)
            total_bytes += w
    except HTTPException:
        # save_upload already raised an HTTP-friendly error (size/extension etc.).
        # Roll back any files that did save before the failure, drop the job.
        for path in (
            job.storage_path,
            job.tagged_storage_path,
            job.stems_storage_path,
            job.artwork_storage_path,
            job.video_storage_path,
        ):
            remove_upload(path)
        await db.delete(job)
        await db.commit()
        raise
    except Exception as exc:
        # Unexpected failure — log internally, surface a generic message to client.
        log.exception("save_upload failed for job %s", job.id)
        job.status = UploadStatus.failed
        job.error = "Failed to save file"  # don't expose raw exception text
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        ) from exc

    job.size_bytes = total_bytes
    await db.commit()
    await db.refresh(job)

    # Kick off background processing — DO NOT await
    start_job(job.id, user.id, payload)

    return _serialize(job)


@router.get("", response_model=list[UploadOut])
async def list_uploads(user: CurrentUser, db: DbSession) -> list[UploadOut]:
    rows = await db.scalars(
        select(UploadJob)
        .where(UploadJob.user_id == user.id)
        .order_by(desc(UploadJob.created_at))
        .limit(100)
    )
    return [_serialize(r) for r in rows]


@router.get("/{upload_id}", response_model=UploadOut)
async def get_upload(upload_id: int, user: CurrentUser, db: DbSession) -> UploadOut:
    job = await db.get(UploadJob, upload_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return _serialize(job)


@router.get("/{upload_id}/artwork")
async def get_artwork(upload_id: int, user: CurrentUser, db: DbSession):
    """Serve the artwork file. Requires auth — request from frontend with Bearer
    header, then use the returned blob as a thumbnail URL.
    """
    job = await db.get(UploadJob, upload_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not job.artwork_storage_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No artwork")
    path = Path(job.artwork_storage_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Artwork file missing")
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(path, media_type=mime or "image/jpeg")


@router.post("/{upload_id}/retry", response_model=UploadOut)
async def retry_upload(upload_id: int, user: CurrentUser, db: DbSession) -> UploadOut:
    """Re-run a failed (or done) job with the same files and metadata.

    Resets status + per-target state, then spawns the worker again. The stored
    `payload_json` provides title/tags/bpm/etc. so the client doesn't need to
    resend anything.
    """
    job = await db.get(UploadJob, upload_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if job.status == UploadStatus.uploading:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload is already in progress",
        )
    if not job.payload_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No stored payload to retry from (job created before retry was supported)",
        )

    # Reset state
    job.status = UploadStatus.queued
    job.error = None
    job.progress = 0
    job.targets = {
        provider: {"status": "queued", "progress": 0}
        for provider in (job.targets or {}).keys()
    }
    await db.commit()
    await db.refresh(job)

    # Reconstruct payload and kick off worker
    try:
        payload = UploadCreate.model_validate(job.payload_json)
    except ValidationError as exc:
        log.warning("Stored payload for job %s is invalid: %s", upload_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored payload is invalid",
        ) from exc

    start_job(job.id, user.id, payload)
    return _serialize(job)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(upload_id: int, user: CurrentUser, db: DbSession) -> None:
    job = await db.get(UploadJob, upload_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # Clean up every file the job owns — not just the master.
    for path in (
        job.storage_path,
        job.tagged_storage_path,
        job.stems_storage_path,
        job.artwork_storage_path,
        job.video_storage_path,
    ):
        remove_upload(path)
    await db.delete(job)
    await db.commit()


# Keep dependency reference to silence unused warning
_ = Depends
