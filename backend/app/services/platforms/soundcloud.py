"""SoundCloud connector via SoundCloud's official OAuth2 API.

Our use case is explicitly permitted by SoundCloud's API terms ("sale of an app
with an Upload to SoundCloud integration" + "services that allow a user to
promote their content via authenticated access to the user's account"). Each
producer connects their OWN SoundCloud account via OAuth; we upload the beats
they own. We never download/store SoundCloud audio.

Auth: OAuth2 authorization-code with PKCE via secure.soundcloud.com.
Upload: multipart POST to api.soundcloud.com/tracks.

⚠️ Built against SoundCloud's documented API but NOT yet verified end-to-end
(needs real client credentials — Artist Pro required to register the app). The
bits most likely to need a tweak against the live API are flagged inline:
the Authorization scheme ("OAuth" vs "Bearer"), whether `scope` is needed, and
the exact /tracks field names. Iterate once credentials exist.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from jose import jwt as jose_jwt

from app.config import get_settings
from app.models.platform import PlatformConnection, PlatformProvider
from app.security import decrypt_token, encrypt_token
from app.services.platforms.base import (
    AuthMethod,
    BeatMetadata,
    OAuthRedirect,
    PlatformConnector,
    ProgressCallback,
    UploadHandle,
    UploadProgress,
)

SC_AUTH_URL = "https://secure.soundcloud.com/authorize"
SC_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"
SC_API = "https://api.soundcloud.com"

# Audio/image MIME types SoundCloud accepts.
_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _mime(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/octet-stream")


def _callback_url() -> str:
    settings = get_settings()
    return f"{settings.backend_base_url.rstrip('/')}/api/platforms/soundcloud/callback"


def _gen_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for the PKCE S256 flow."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def make_state(user_id: int, code_verifier: str) -> str:
    """Signed state JWT carrying the user id + PKCE verifier (stateless callback).

    The verifier rides in our own signed token. It's belt-and-suspenders here —
    we're a confidential client (we also send client_secret) — so exposing it in
    the round-tripped state doesn't weaken the exchange.
    """
    settings = get_settings()
    payload = {
        "uid": user_id,
        "provider": "soundcloud",
        "cv": code_verifier,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(UTC) + timedelta(seconds=settings.oauth_state_expire_seconds),
    }
    return jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> tuple[int, str]:
    """Return (user_id, code_verifier) from a state JWT. Raises on bad/expired."""
    settings = get_settings()
    payload = jose_jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return int(payload["uid"]), str(payload["cv"])


class SoundCloudConnector(PlatformConnector):
    provider = PlatformProvider.soundcloud
    method = AuthMethod.oauth
    display_name = "SoundCloud"

    def is_configured(self) -> bool:
        return bool(get_settings().soundcloud_client_id)

    async def start_authorize(self, *, user_id: int, redirect_uri: str) -> OAuthRedirect:
        settings = get_settings()
        if not settings.soundcloud_client_id:
            raise RuntimeError(
                "SOUNDCLOUD_CLIENT_ID not set. Register an app at "
                "soundcloud.com/you/apps (Artist Pro required) and set the creds."
            )
        verifier, challenge = _gen_pkce()
        state = make_state(user_id, verifier)
        from urllib.parse import urlencode

        params = {
            "client_id": settings.soundcloud_client_id,
            "redirect_uri": _callback_url(),
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        return OAuthRedirect(
            authorize_url=f"{SC_AUTH_URL}?{urlencode(params)}", state=state
        )

    async def complete_authorize(
        self, *, code: str, state: str, redirect_uri: str
    ) -> dict[str, Any]:
        settings = get_settings()
        _user_id, code_verifier = verify_state(state)

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                SC_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.soundcloud_client_id,
                    "client_secret": settings.soundcloud_client_secret,
                    "redirect_uri": _callback_url(),
                    "code_verifier": code_verifier,
                    "code": code,
                },
            )
            res.raise_for_status()
            tokens = res.json()

            # Friendly account label from the authed user's profile.
            label: str | None = None
            try:
                me = await client.get(
                    f"{SC_API}/me",
                    headers={"Authorization": f"OAuth {tokens['access_token']}"},
                )
                if me.is_success:
                    body = me.json()
                    label = body.get("username") or body.get("permalink")
            except Exception:  # noqa: BLE001 — label is best-effort
                pass

        expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens.get("expires_in", 3600))
        )
        return {
            "access_token_encrypted": encrypt_token(tokens["access_token"]),
            "refresh_token_encrypted": (
                encrypt_token(tokens["refresh_token"])
                if tokens.get("refresh_token")
                else None
            ),
            "expires_at": expires_at,
            "account_label": label or "SoundCloud",
        }

    async def disconnect(self, connection: PlatformConnection) -> None:
        return None

    async def _ensure_access_token(
        self, client: httpx.AsyncClient, connection: PlatformConnection
    ) -> str:
        """Return a valid access token, refreshing + persisting if near expiry.

        Mutates the connection in place; the job processor commits the session
        after the upload, so the rotated token is saved.
        """
        if not connection.access_token_encrypted:
            raise RuntimeError("No SoundCloud access token on connection")
        access = decrypt_token(connection.access_token_encrypted)

        expires_at = connection.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        still_valid = expires_at is None or expires_at - timedelta(seconds=60) > datetime.now(UTC)
        if still_valid:
            return access

        if not connection.refresh_token_encrypted:
            return access  # nothing to refresh with; let the API reject if stale
        settings = get_settings()
        res = await client.post(
            SC_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.soundcloud_client_id,
                "client_secret": settings.soundcloud_client_secret,
                "refresh_token": decrypt_token(connection.refresh_token_encrypted),
            },
        )
        if not res.is_success:
            raise RuntimeError("SoundCloud token refresh failed — reconnect the account")
        tokens = res.json()
        access = tokens["access_token"]
        connection.access_token_encrypted = encrypt_token(access)
        if tokens.get("refresh_token"):
            connection.refresh_token_encrypted = encrypt_token(tokens["refresh_token"])
        connection.expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens.get("expires_in", 3600))
        )
        return access

    async def upload(
        self,
        connection: PlatformConnection,
        *,
        file_path: Path,
        meta: BeatMetadata,
        progress_cb: ProgressCallback | None = None,
    ) -> UploadHandle:
        # Promote the streamable preview if there is one, else the master.
        audio = meta.tagged_path or meta.master_path or file_path

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            token = await self._ensure_access_token(client, connection)
            if progress_cb:
                progress_cb(10)

            # SoundCloud /tracks takes bracketed multipart fields.
            data = {
                "track[title]": (meta.title or audio.stem)[:100],
                "track[sharing]": "public",
            }
            if meta.description:
                data["track[description]"] = meta.description[:4000]
            if meta.tags:
                # SoundCloud tag_list is space-separated; multi-word tags quoted.
                data["track[tag_list]"] = " ".join(
                    f'"{t}"' if " " in t else t for t in meta.tags[:30]
                )
            if meta.genre:
                data["track[genre]"] = meta.genre

            with audio.open("rb") as audio_fh:
                files = {
                    "track[asset_data]": (audio.name, audio_fh, _mime(audio)),
                }
                artwork_fh = None
                if meta.artwork_path is not None:
                    artwork_fh = meta.artwork_path.open("rb")
                    files["track[artwork_data]"] = (
                        meta.artwork_path.name, artwork_fh, _mime(meta.artwork_path),
                    )
                try:
                    res = await client.post(
                        f"{SC_API}/tracks",
                        headers={"Authorization": f"OAuth {token}"},
                        data=data,
                        files=files,
                    )
                finally:
                    if artwork_fh is not None:
                        artwork_fh.close()

        if res.status_code not in (200, 201):
            raise RuntimeError(
                f"SoundCloud upload failed (HTTP {res.status_code}): {res.text[:300]}"
            )
        track = res.json()
        if progress_cb:
            progress_cb(100)
        return UploadHandle(
            external_id=str(track.get("id") or ""),
            public_url=track.get("permalink_url"),
        )

    async def poll(self, connection: PlatformConnection, handle: UploadHandle) -> UploadProgress:
        # /tracks returns synchronously with the finished track, so by the time we
        # have a handle the upload is done. (Transcoding continues server-side but
        # the track is already live at permalink_url.)
        return UploadProgress(progress=100, status="done", public_url=handle.public_url)
