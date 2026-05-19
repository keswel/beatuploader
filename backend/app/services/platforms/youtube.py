from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from jose import jwt as jose_jwt

from app.config import get_settings
from app.models.platform import PlatformConnection, PlatformProvider
from app.security import decrypt_token, encrypt_token
from app.services.platforms.base import (
    AuthMethod,
    BeatMetadata,
    OAuthRedirect,
    PlatformConnector,
    UploadHandle,
    UploadProgress,
)

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _callback_url() -> str:
    settings = get_settings()
    return f"{settings.backend_base_url.rstrip('/')}/api/platforms/youtube/callback"


def make_state(user_id: int) -> str:
    settings = get_settings()
    payload = {
        "uid": user_id,
        "provider": "youtube",
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(seconds=settings.oauth_state_expire_seconds),
    }
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> int:
    settings = get_settings()
    payload = jose_jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["uid"])


class YouTubeConnector(PlatformConnector):
    provider = PlatformProvider.youtube
    method = AuthMethod.oauth
    display_name = "YouTube"

    async def start_authorize(self, *, user_id: int, redirect_uri: str) -> OAuthRedirect:
        settings = get_settings()
        if not settings.youtube_client_id:
            raise RuntimeError(
                "YOUTUBE_CLIENT_ID not set. See README for Google Cloud setup steps."
            )
        state = make_state(user_id)
        # Always use OUR callback URL — Google must match the one registered in console.
        # The redirect_uri argument is ignored for OAuth providers; we control the URL.
        params = {
            "client_id": settings.youtube_client_id,
            "redirect_uri": _callback_url(),
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # force refresh_token issuance every time
            "state": state,
        }
        from urllib.parse import urlencode

        authorize_url = f"{YOUTUBE_AUTH_URL}?{urlencode(params)}"
        return OAuthRedirect(authorize_url=authorize_url, state=state)

    async def complete_authorize(
        self, *, code: str, state: str, redirect_uri: str
    ) -> dict[str, Any]:
        import httpx

        settings = get_settings()
        async with httpx.AsyncClient() as client:
            res = await client.post(
                YOUTUBE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.youtube_client_id,
                    "client_secret": settings.youtube_client_secret,
                    "redirect_uri": _callback_url(),
                    "grant_type": "authorization_code",
                },
                timeout=30.0,
            )
        res.raise_for_status()
        tokens = res.json()

        # Fetch channel info for a friendlier account label
        access_token = tokens["access_token"]
        async with httpx.AsyncClient() as client:
            ch = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
        label: str | None = None
        if ch.is_success:
            items = ch.json().get("items") or []
            if items:
                label = items[0].get("snippet", {}).get("title")

        expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        return {
            "access_token_encrypted": encrypt_token(access_token),
            "refresh_token_encrypted": (
                encrypt_token(tokens["refresh_token"]) if tokens.get("refresh_token") else None
            ),
            "expires_at": expires_at,
            "account_label": label or "YouTube channel",
        }

    async def disconnect(self, connection: PlatformConnection) -> None:
        # Optional: call https://oauth2.googleapis.com/revoke. Skipping to keep this MVP simple.
        return None

    def _credentials(self, connection: PlatformConnection) -> Credentials:
        settings = get_settings()
        if not connection.access_token_encrypted:
            raise RuntimeError("No access token on connection")
        access = decrypt_token(connection.access_token_encrypted)
        refresh = (
            decrypt_token(connection.refresh_token_encrypted)
            if connection.refresh_token_encrypted
            else None
        )
        return Credentials(
            token=access,
            refresh_token=refresh,
            token_uri=YOUTUBE_TOKEN_URL,
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            scopes=YOUTUBE_SCOPES,
        )

    async def upload(
        self,
        connection: PlatformConnection,
        *,
        file_path: Path,
        meta: BeatMetadata,
    ) -> UploadHandle:
        creds = self._credentials(connection)

        def _do_upload() -> dict:
            # Build the YouTube client and perform a resumable upload.
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
            body = {
                "snippet": {
                    "title": meta.title[:100],
                    "description": _description(meta),
                    "tags": meta.tags[:30],
                    "categoryId": "10",  # Music
                },
                "status": {
                    "privacyStatus": "private",  # safer default — user can publish later
                    "selfDeclaredMadeForKids": False,
                },
            }
            media = MediaFileUpload(
                str(file_path),
                chunksize=1024 * 1024 * 4,
                resumable=True,
                mimetype="audio/mpeg",
            )
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )
            response = None
            # next_chunk blocks; loop until done. We could surface progress but keep simple here.
            while response is None:
                _, response = request.next_chunk()
            return response

        # google-api-python-client is sync, so offload to a thread
        try:
            response = await asyncio.to_thread(_do_upload)
        except HttpError as exc:
            raise RuntimeError(f"YouTube upload failed: {exc}") from exc

        video_id = response["id"]
        return UploadHandle(
            external_id=video_id,
            public_url=f"https://www.youtube.com/watch?v={video_id}",
        )

    async def poll(self, connection: PlatformConnection, handle: UploadHandle) -> UploadProgress:
        creds = self._credentials(connection)

        def _check() -> dict:
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
            res = (
                youtube.videos()
                .list(part="processingDetails,status", id=handle.external_id)
                .execute()
            )
            items = res.get("items", [])
            return items[0] if items else {}

        try:
            item = await asyncio.to_thread(_check)
        except HttpError as exc:
            return UploadProgress(progress=0, status="failed", error=str(exc))

        if not item:
            return UploadProgress(progress=0, status="failed", error="Video not found")

        processing = item.get("processingDetails", {}).get("processingStatus", "")
        if processing in ("succeeded", "terminated"):
            upload_status = item.get("status", {}).get("uploadStatus", "")
            if upload_status == "processed":
                return UploadProgress(
                    progress=100, status="done", public_url=handle.public_url
                )
        if processing == "failed":
            return UploadProgress(
                progress=0,
                status="failed",
                error=item.get("processingDetails", {}).get("processingFailureReason"),
            )
        return UploadProgress(progress=50, status="uploading")


def _description(meta: BeatMetadata) -> str:
    parts: list[str] = []
    if meta.bpm:
        parts.append(f"BPM: {meta.bpm}")
    if meta.music_key:
        parts.append(f"Key: {meta.music_key}")
    if meta.tags:
        parts.append("Tags: " + ", ".join(meta.tags))
    return "\n".join(parts) if parts else ""
