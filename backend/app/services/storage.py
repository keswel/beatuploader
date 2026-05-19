from __future__ import annotations

from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

# Per-role limits + allowed extensions. The frontend already enforces these via
# its dropzone, but never trust the client.
ROLE_LIMITS: dict[str, tuple[int, frozenset[str]]] = {
    "master":  (250 * 1024 * 1024, frozenset({".wav", ".wave", ".flac"})),
    "tagged":  (100 * 1024 * 1024, frozenset({".mp3"})),
    "stems":   (1024 * 1024 * 1024, frozenset({".zip", ".rar"})),  # stems can be big
    "artwork": (10 * 1024 * 1024,  frozenset({".png", ".jpg", ".jpeg", ".webp"})),
    "video":   (2 * 1024 * 1024 * 1024, frozenset({".mp4", ".mov", ".webm", ".m4v"})),
}


def storage_root() -> Path:
    root = Path(get_settings().storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate(file: UploadFile, role: str) -> None:
    limit, allowed = ROLE_LIMITS.get(role, (0, frozenset()))
    name = (file.filename or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{role}: extension {ext or 'unknown'!r} not allowed (expected one of {sorted(allowed)})",
        )
    # Best-effort size check via the Content-Length / .size attribute. The real
    # check happens in save_upload below, which aborts if the stream grows past
    # the limit.
    declared = getattr(file, "size", None)
    if declared is not None and declared > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{role} exceeds size limit ({limit // (1024*1024)} MB)",
        )


def upload_path(user_id: int, job_id: int, filename: str, role: str = "master") -> Path:
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ").strip() or "upload.bin"
    user_dir = storage_root() / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{job_id}_{role}_{safe}"


async def save_upload(
    user_id: int, job_id: int, file: UploadFile, role: str = "master"
) -> tuple[Path, int]:
    """Stream incoming UploadFile to disk. Returns (path, bytes_written).

    `role` is one of 'master' | 'tagged' | 'stems' | 'artwork' — affects the
    filename so multiple files for the same job don't collide.

    Validates extension before saving and enforces the per-role byte limit
    while streaming. If the stream exceeds the limit, the partial file is
    deleted before raising.
    """
    _validate(file, role)
    limit = ROLE_LIMITS[role][0]

    target = upload_path(user_id, job_id, file.filename or "upload.bin", role=role)
    written = 0
    try:
        async with aiofiles.open(target, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"{role} exceeds size limit ({limit // (1024 * 1024)} MB)",
                    )
                await out.write(chunk)
    except Exception:
        # Clean up the partial file so we don't leak disk on rejection
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        raise
    return target, written


def remove_upload(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    if p.exists():
        p.unlink()
