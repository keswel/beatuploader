"""BeatStars connector over their private HTTP/GraphQL API.

Reverse-engineered from the studio.beatstars.com web client (captured May 2026).
No browser — pure httpx — so it runs in a tiny footprint on free-tier hosting
(unlike the Playwright path in beatstars.py, which OOMs on 512MB containers).

Flow mirrors the web client exactly:

  Auth   : identifierAvailable (nice "no account" error) → oauth/token
           grant_type=password → {access_token, refresh_token}. Refresh via
           grant_type=refresh_token; re-login with the stored password if that
           fails.
  Upload : AddTrack → (per file) createAssetFile → GET uppy s3/params →
           POST file to S3 presigned form → attach{Stream,MainAudio,Stems}File
           / attachArtwork → SaveTrackForm → PublishTrackForm.

All selectors here are JSON shapes, not CSS — far more stable than the Angular
DOM the Playwright path scrapes. If BeatStars changes a GraphQL field, the
error surfaces as a clean `BeatStarsApiError` naming the operation.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.services.platforms.base import (
    BeatMetadata,
    ProgressCallback,
    UploadHandle,
)

# Pure mapping helpers + SMS challenge types shared with the Playwright path.
# beatstars.py has no top-level import of this module (its dispatch imports us
# lazily), so there's no import cycle.
from app.services.platforms.beatstars import (
    LICENSE_LABEL,
    SmsCancelled,
    SmsHandler,
    clamp_tags,
    normalize_key,
    pick_licenses,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Endpoints + static client credentials
# ─────────────────────────────────────────────────────────────────────────────

API = "https://core.prod.beatstars.net"
TOKEN_URL = f"{API}/auth/oauth/token"
AUTH_GRAPHQL = f"{API}/auth/graphql"
STUDIO_GRAPHQL = f"{API}/studio/graphql"
UPPY_PARAMS_URL = "https://uppy-v4.beatstars.net/s3/params"

STUDIO_ORIGIN = "https://studio.beatstars.com"
OAUTH_ORIGIN = "https://oauth.beatstars.com"

# Static OAuth client creds baked into BeatStars' own web frontend — these are
# shipped to every browser, so they're effectively public (not user secrets).
CLIENT_ID = "5615656127.beatstars.com"
CLIENT_SECRET = "2a$16$b376aMFTHFXoI1XXa$5xXWHjnyZUP61sGr$GKwZjT$ApolQQW"

# Refresh the access token if it's within this many seconds of expiring.
_TOKEN_SKEW_S = 60

# Free-download config. The web client always sends a freeDownloadSettings key,
# so we include it (matching the captured shape) rather than omitting it and
# hoping the field is nullable. We default the feature OFF — a producer can't
# opt into free downloads through our UI yet. If BeatStars rejects this minimal
# shape (i.e. it requires the full `terms` block even when disabled), expand
# this to the full object seen in the capture.
_FREE_DOWNLOAD_OFF = {"enabled": False}

_HTTP_TIMEOUT = httpx.Timeout(600.0, connect=30.0)

# Look like the real web client. A bare httpx UA can trip BeatStars' edge/WAF
# (we saw GATEWAY_TIMEOUTs from the GraphQL gateway), and these headers match
# what studio.beatstars.com actually sends.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) "
        "Gecko/20100101 Firefox/151.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# BeatStars' GraphQL gateway is flaky — these messages/statuses are worth a retry
# on idempotent reads (never on mutations, which could duplicate).
_TRANSIENT_GQL_ERRORS = {"GATEWAY_TIMEOUT", "SERVICE_UNAVAILABLE", "INTERNAL_SERVER_ERROR"}
_TRANSIENT_STATUSES = {502, 503, 504}


def _new_client() -> httpx.AsyncClient:
    """Factory for the HTTP client. A seam so tests can inject a MockTransport."""
    return httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers=_BROWSER_HEADERS)


class BeatStarsApiError(RuntimeError):
    """Any BeatStars HTTP/GraphQL failure. Message is safe to surface to users."""


class _MfaRequired(Exception):
    """Internal signal: the password grant needs an SMS code to complete.

    BeatStars triggers SMS 2FA for logins from unfamiliar devices/IPs (notably
    our server's datacenter IP). The token endpoint returns an error carrying
    code ``MFA_VERIFICATION_ACTION`` and auto-sends the SMS; we then re-POST the
    same grant with an extra ``code`` field.
    """

    def __init__(self, hint: str | None = None):
        super().__init__("MFA required")
        self.hint = hint


# Substring that marks an MFA-required response (from the login bundle's auth
# error-code enum).
_MFA_SIGNAL = "MFA_VERIFICATION_ACTION"


# ─────────────────────────────────────────────────────────────────────────────
# GraphQL operations (literal queries, trimmed to the fields we consume)
# ─────────────────────────────────────────────────────────────────────────────

Q_IDENTIFIER = (
    "query identifierAvailable($identifier: String!) {"
    " identifierAvailable(identifier: $identifier) {"
    " available profileDetails { username } } }"
)
Q_CAN_CREATE = "query canCreateTrack { canCreateTrack }"
M_ADD_TRACK = "mutation AddTrack { addTrack { id } }"
M_CREATE_ASSET = (
    "mutation createAssetFile($file: FileUploadInput!) {"
    " create(file: $file) { id file { assetId type } } }"
)
M_ATTACH_MAIN = (
    "mutation attachMainAudio($id: String!, $assetId: String!) {"
    " attachMainAudioFile(id: $id, assetId: $assetId, encodeRelatedFiles: false) }"
)
M_ATTACH_STREAM = (
    "mutation attachStream($id: String!, $assetId: String!) {"
    " attachStreamFile(id: $id, assetId: $assetId, createHlsFile: false) }"
)
M_ATTACH_STEMS = (
    "mutation attachStems($id: String!, $assetId: String!) {"
    " attachStemsFile(id: $id, assetId: $assetId) }"
)
M_ATTACH_ARTWORK = (
    "mutation trackFormAttachArtwork($itemId: String!, $assetId: String!) {"
    " attachArtwork(itemId: $itemId, assetId: $assetId) }"
)
Q_CONTRACTS = (
    "query GetTrackFormContracts($itemId: String!, $page: Int, $size: Int) {"
    " publishedContracts(itemId: $itemId, page: $page, size: $size) {"
    " content { id title deliverables defaultPrice price enabled category } totalElements } }"
)
Q_METADATA = (
    "query GetMetadataProperties {"
    " metadataProperties { genres { key value } } }"
)
M_SAVE_TRACK = (
    "mutation SaveTrackForm($id: String!, $track: TrackInput!,"
    " $contracts: [ContractAttachmentInput]) {"
    " saveTrack(id: $id, track: $track, contracts: $contracts) { id } }"
)
M_PUBLISH_TRACK = (
    "mutation PublishTrackForm($id: String!, $track: TrackInput!,"
    " $contracts: [ContractAttachmentInput]) {"
    " publishTrack(id: $id, track: $track, contracts: $contracts) {"
    " id status url shareUrl } }"
)

# ─────────────────────────────────────────────────────────────────────────────
# File type mapping
# ─────────────────────────────────────────────────────────────────────────────

_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".zip": "application/x-zip-compressed",
    ".rar": "application/x-rar-compressed",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_AUDIO_EXT = {".mp3", ".wav", ".wave", ".flac", ".aiff", ".aif"}
_BINARY_EXT = {".zip", ".rar"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _bts_type(path: Path) -> str:
    """BeatStars' asset 'type' tag (not a MIME type)."""
    ext = path.suffix.lower()
    if ext in _AUDIO_EXT:
        return "AUDIO"
    if ext in _IMAGE_EXT:
        return "IMAGE"
    return "BINARY"


# ─────────────────────────────────────────────────────────────────────────────
# Token / session handling
# ─────────────────────────────────────────────────────────────────────────────


def _jwt_claims(token: str) -> dict:
    """Decode a JWT payload WITHOUT verifying — we only read claims we already trust."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # restore base64 padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, binascii.Error, ValueError, json.JSONDecodeError):
        return {}


def _session_from_tokens(tokens: dict, *, account_label: str | None = None) -> dict:
    """Build our persisted session dict from an oauth/token response."""
    access = tokens["access_token"]
    claims = _jwt_claims(access)
    return {
        "access_token": access,
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": int(claims.get("exp", 0)),
        "member_id": claims.get("user_name", ""),
        "account_label": account_label or "",
    }


async def _password_grant(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    *,
    code: str | None = None,
) -> dict:
    """Run the OAuth password grant. Pass ``code`` to complete an SMS challenge.

    The same ``client`` (and its cookie jar) must be reused across the initial
    grant and the code-bearing retry — BeatStars ties the MFA session to cookies
    set on the first attempt (the web client sends ``withCredentials: true``).

    Raises ``_MfaRequired`` when BeatStars wants an SMS code.
    """
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "origin": "https://www.beatstars.com/",
    }
    if code:
        data["code"] = code
    try:
        resp = await client.post(TOKEN_URL, data=data, headers={"Origin": OAUTH_ORIGIN})
    except httpx.HTTPError as exc:
        raise BeatStarsApiError(
            "Couldn't reach BeatStars to sign in — try again in a moment."
        ) from exc
    if resp.status_code == 200:
        return resp.json()

    body = resp.text or ""
    if _MFA_SIGNAL in body:
        raise _MfaRequired(_extract_message(resp))
    if resp.status_code in (400, 401):
        # OAuth returns 400 invalid_grant for genuinely bad credentials.
        raise BeatStarsApiError("Wrong BeatStars email or password")
    # 5xx / gateway timeout — NOT a credential problem; don't mislabel it.
    raise BeatStarsApiError(
        f"BeatStars sign-in is temporarily unavailable (HTTP {resp.status_code}) — "
        "try again shortly."
    )


def _extract_message(resp: httpx.Response) -> str | None:
    """Best-effort human hint from an error body (e.g. 'code sent to ***1234')."""
    try:
        j = resp.json()
    except Exception:  # noqa: BLE001
        return None
    for path in (("message",), ("error", "message"), ("response", "data", "message")):
        cur = j
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur.strip():
            return cur.strip()[:160]
    return None


async def _refresh_grant(client: httpx.AsyncClient, refresh_token: str) -> dict:
    try:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            headers={"Origin": STUDIO_ORIGIN},
        )
    except httpx.HTTPError as exc:
        raise BeatStarsApiError("Couldn't reach BeatStars to refresh the session") from exc
    if resp.status_code != 200:
        raise BeatStarsApiError("BeatStars session expired")
    return resp.json()


async def login(
    username: str, password: str, *, sms_handler: SmsHandler | None = None
) -> dict:
    """Authenticate and return a fresh session dict. Raises BeatStarsApiError.

    If BeatStars challenges with SMS 2FA and ``sms_handler`` is provided, we relay
    the challenge through it (the same callbacks the Playwright path uses): notify
    on detection, block for the code, then complete the grant. With no handler a
    challenge is a clean error.
    """
    async with _new_client() as client:
        label: str | None = None
        # Best-effort account-existence check — gives a clean "no account" error
        # instead of a generic "wrong password". It's a nicety, so a transport or
        # gateway error here must NOT block login (we saw GATEWAY_TIMEOUTs). Only
        # a definitive "this email isn't registered" result is allowed to fail.
        info: dict | None = None
        try:
            data = await _graphql(
                client, None, AUTH_GRAPHQL, "identifierAvailable", Q_IDENTIFIER,
                {"identifier": username}, origin=OAUTH_ORIGIN, idempotent=True,
            )
            info = data.get("identifierAvailable") or {}
        except Exception as exc:  # noqa: BLE001 — the check is optional
            log.info("identifierAvailable check skipped: %s", exc)
        if info is not None:
            # available == True means the identifier is FREE → no such account.
            if info.get("available") is True:
                raise BeatStarsApiError("No BeatStars account found for that email")
            label = (info.get("profileDetails") or {}).get("username")

        try:
            tokens = await _password_grant(client, username, password)
        except _MfaRequired as mfa:
            tokens = await _complete_mfa(
                client, username, password, mfa.hint, sms_handler
            )
        session = _session_from_tokens(tokens, account_label=label or username)
        return session


async def _complete_mfa(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    hint: str | None,
    sms_handler: SmsHandler | None,
) -> dict:
    """Relay the SMS challenge through the handler and finish the grant."""
    if sms_handler is None:
        raise BeatStarsApiError(
            "BeatStars wants an SMS verification code, but no handler was available "
            "to relay it."
        )
    # Tell the API layer a code is needed (it returns sms_required to the client),
    # then block — off the event loop — until the code arrives via /beatstars/sms.
    sms_handler.on_detected(hint)
    code = await asyncio.to_thread(sms_handler.get_code)
    if not code or not str(code).strip():
        raise SmsCancelled("SMS challenge was cancelled or timed out")
    try:
        # Same client → the MFA-session cookie from the first attempt is reused.
        return await _password_grant(
            client, username, password, code=str(code).strip()
        )
    except (BeatStarsApiError, _MfaRequired) as exc:
        raise BeatStarsApiError(
            "BeatStars rejected the verification code (or it expired). "
            "Try connecting again for a fresh code."
        ) from exc


async def _ensure_token(
    client: httpx.AsyncClient, session: dict, *, password: str | None
) -> str:
    """Return a valid access token, refreshing (or re-logging-in) if needed.

    Mutates ``session`` in place with any new tokens so the caller can persist
    the rotated refresh token back to the connection.
    """
    now = time.time()
    if session.get("access_token") and session.get("expires_at", 0) - _TOKEN_SKEW_S > now:
        return session["access_token"]

    # Try a refresh first.
    if session.get("refresh_token"):
        try:
            tokens = await _refresh_grant(client, session["refresh_token"])
            session.update(_session_from_tokens(tokens, account_label=session.get("account_label")))
            return session["access_token"]
        except BeatStarsApiError:
            log.info("BeatStars refresh failed; falling back to password re-login")

    # Refresh dead → re-login with the stored password.
    if password and session.get("account_label"):
        tokens = await _password_grant(client, session["account_label"], password)
        session.update(_session_from_tokens(tokens, account_label=session.get("account_label")))
        return session["access_token"]

    raise BeatStarsApiError(
        "BeatStars session expired and couldn't be renewed — reconnect the account."
    )


# ─────────────────────────────────────────────────────────────────────────────
# GraphQL transport
# ─────────────────────────────────────────────────────────────────────────────


async def _graphql(
    client: httpx.AsyncClient,
    token: str | None,
    endpoint: str,
    op: str,
    query: str,
    variables: dict,
    *,
    origin: str = STUDIO_ORIGIN,
    idempotent: bool = False,
) -> dict:
    """POST a GraphQL operation. Set ``idempotent=True`` only for reads — it
    enables a short retry on BeatStars' flaky gateway (5xx / GATEWAY_TIMEOUT).
    Mutations stay single-shot so a timed-out-but-applied write can't duplicate.
    """
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"operationName": op, "variables": variables, "query": query}

    attempts = 3 if idempotent else 1
    transient: BeatStarsApiError | None = None
    for attempt in range(attempts):
        try:
            resp = await client.post(f"{endpoint}?op={op}", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            transient = BeatStarsApiError(f"Couldn't reach BeatStars for {op}")
            if not idempotent:
                raise transient from exc
        else:
            if resp.status_code in _TRANSIENT_STATUSES:
                transient = BeatStarsApiError(
                    f"BeatStars {op} is temporarily unavailable (HTTP {resp.status_code})"
                )
            elif resp.status_code != 200:
                raise BeatStarsApiError(
                    f"BeatStars {op} request failed (HTTP {resp.status_code})"
                )
            else:
                body = resp.json()
                errors = body.get("errors")
                if not errors:
                    return body.get("data") or {}
                msg = (errors[0] or {}).get("message", "unknown error")
                err = BeatStarsApiError(f"BeatStars {op} failed: {msg}")
                if idempotent and msg in _TRANSIENT_GQL_ERRORS:
                    transient = err
                else:
                    raise err
        # Reached only on a transient failure with retries remaining.
        if attempt < attempts - 1:
            await asyncio.sleep(0.6 * (attempt + 1))
    raise transient or BeatStarsApiError(f"BeatStars {op} failed")


# ─────────────────────────────────────────────────────────────────────────────
# Asset upload (createAssetFile → presigned S3 POST)
# ─────────────────────────────────────────────────────────────────────────────


async def _upload_asset(
    client: httpx.AsyncClient, token: str, member_id: str, path: Path
) -> str:
    """Register + upload one file to S3. Returns the BeatStars asset id."""
    content_type = _content_type(path)
    bts_type = _bts_type(path)

    # 1. Register the asset, get its id.
    data = await _graphql(
        client,
        token,
        STUDIO_GRAPHQL,
        "createAssetFile",
        M_CREATE_ASSET,
        {"file": {"fileName": path.name, "contentType": content_type}},
    )
    asset_id = data["create"]["id"]

    # 2. Ask Uppy for a presigned S3 POST (no auth needed — the asset-id is the
    #    capability). Metadata keys mirror the web client exactly.
    params = {
        "filename": path.name,
        "type": bts_type,
        "metadata[asset-id]": asset_id,
        "metadata[name]": path.name,
        "metadata[type]": bts_type,
        "metadata[content-type]": content_type,
        "metadata[version]": "2",
        "metadata[user]": member_id,
        "metadata[env]": "prod",
    }
    pr = await client.get(
        UPPY_PARAMS_URL,
        params=params,
        headers={"Origin": STUDIO_ORIGIN, "Referer": STUDIO_ORIGIN + "/"},
    )
    if pr.status_code != 200:
        raise BeatStarsApiError(f"Couldn't get an upload URL for {path.name}")
    presigned = pr.json()

    # 3. POST the bytes to S3. httpx emits `data` fields before `files`, so the
    #    `file` part lands last — exactly what an AWS presigned POST requires.
    fields = presigned["fields"]
    with path.open("rb") as fh:
        sr = await client.post(
            presigned["url"],
            data=fields,
            files={"file": (path.name, fh, content_type)},
        )
    if sr.status_code not in (200, 201, 204):
        raise BeatStarsApiError(
            f"Upload of {path.name} to storage failed (HTTP {sr.status_code})"
        )
    return asset_id


# ─────────────────────────────────────────────────────────────────────────────
# Track form builders
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso_millis() -> str:
    # BeatStars sends e.g. "2026-05-25T20:57:17.979Z" (millisecond precision).
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _match_genre(genres_menu: list[dict], user_label: str) -> str | None:
    """Map a free-text genre label to BeatStars' enum key, or None if unknown.

    Returning None (and sending no genre) is deliberately safe: an invalid enum
    value would fail the whole publish, so we'd rather skip the genre than risk
    that.
    """
    norm = user_label.strip().lower()
    for pair in genres_menu:
        if str(pair.get("value", "")).strip().lower() == norm:
            return pair.get("key")
    # Fall back to matching the enum-key form ("Hip Hop" → "HIP_HOP").
    key_guess = norm.replace("&", "").replace("-", " ").split()
    key_guess = "_".join(key_guess).upper()
    for pair in genres_menu:
        if pair.get("key") == key_guess:
            return pair.get("key")
    return None


def _build_track(meta: BeatMetadata, genres: list[str]) -> dict:
    return {
        "category": "BEAT",
        "description": meta.description or "",
        "excludeFromBulkDiscounts": False,
        "metadata": {
            "tags": clamp_tags(meta.tags or []),
            "genres": genres,
            "bpmDouble": str(meta.bpm) if meta.bpm else None,
            "instruments": [],
            "keyNote": normalize_key(meta.music_key) or "NONE",
            "moods": [],
        },
        "releaseDate": _now_iso_millis(),
        "thirdPartyLoopsAndSample": [],
        "title": (meta.title or "Untitled")[:60],
        "visibility": "PUBLIC",
        "boostCampaign": False,
        "freeDownloadSettings": dict(_FREE_DOWNLOAD_OFF),
    }


def _build_contracts(track_id: str, meta: BeatMetadata, menu: list[dict]) -> list[dict]:
    """Map our license selection onto BeatStars' per-account contract ids.

    Empty list = leave the account-default licenses (Basic etc.) untouched,
    which is exactly what the web client sends for an MP3-only / AUTO upload.
    """
    has_master_wav = (
        meta.master_path is not None
        and meta.master_path.suffix.lower() in (".wav", ".wave", ".flac")
    )
    has_tagged = meta.tagged_path is not None
    has_stems = meta.stems_path is not None
    choices = pick_licenses(
        meta.license_type,
        has_master_wav=has_master_wav,
        has_tagged=has_tagged,
        has_stems=has_stems,
    )
    if not choices:
        return []

    by_title = {c.get("title"): c for c in menu}
    is_auto = (meta.license_type or "AUTO") == "AUTO"
    priced_license = choices[-1]
    user_price = (
        meta.price_cents / 100 if meta.price_cents and meta.price_cents > 0 else None
    )

    contracts: list[dict] = []
    for lic in choices:
        contract = by_title.get(LICENSE_LABEL.get(lic))
        if contract is None:
            log.warning("No BeatStars contract found for license %s; skipping", lic)
            continue
        if user_price is not None and (not is_auto or lic == priced_license):
            price = user_price
        else:
            price = contract.get("defaultPrice")
            if price is None:
                price = contract.get("price")
        if price is None:
            # A null price would fail the publish — better to skip the tier.
            log.warning("No price for BeatStars license %s; skipping it", lic)
            continue
        contracts.append(
            {
                "itemId": track_id,
                "contractId": contract["id"],
                "price": price,
                "enabled": True,
                "offerOnly": False,
            }
        )
    return contracts


# ─────────────────────────────────────────────────────────────────────────────
# Public entry points (called by BeatStarsConnector via dispatch)
# ─────────────────────────────────────────────────────────────────────────────


async def connect_with_credentials(
    *, username: str, password: str, sms_handler: SmsHandler | None = None
) -> tuple[str, str, str]:
    """Validate creds via the HTTP login. Returns (password_enc, session_enc, label).

    Same return contract as the Playwright connect_with_credentials so the API
    layer is transport-agnostic. ``sms_handler`` relays a 2FA challenge if one
    fires (logins from the server IP usually trigger it).
    """
    from app.security import encrypt_token

    session = await login(username, password, sms_handler=sms_handler)
    label = session.get("account_label") or username
    return (
        encrypt_token(password),
        encrypt_token(json.dumps(session)),
        label,
    )


async def upload(
    connection,
    *,
    file_path: Path,
    meta: BeatMetadata,
    progress_cb: ProgressCallback | None = None,
) -> UploadHandle:
    """Run the full HTTP upload flow. Returns an UploadHandle with the refreshed
    session in ``session_data`` so the job processor persists rotated tokens."""
    from app.security import decrypt_token

    # Load the persisted session + password.
    session: dict = {}
    if connection.session_data_encrypted:
        try:
            session = json.loads(decrypt_token(connection.session_data_encrypted))
        except Exception:  # noqa: BLE001 — stale/garbled session → re-login below
            session = {}
    password: str | None = None
    if connection.access_token_encrypted:
        try:
            password = decrypt_token(connection.access_token_encrypted)
        except Exception:  # noqa: BLE001
            password = None
    if not session and password and connection.account_label:
        session = {"account_label": connection.account_label}

    def _progress(pct: int) -> None:
        if progress_cb:
            try:
                progress_cb(max(0, min(100, pct)))
            except Exception:  # noqa: BLE001 — never let progress break an upload
                pass

    async with _new_client() as client:
        token = await _ensure_token(client, session, password=password)
        member_id = session.get("member_id") or ""

        # Plan gate — surfaces "you've hit your upload limit" clearly.
        try:
            gate = await _graphql(
                client, token, STUDIO_GRAPHQL, "canCreateTrack", Q_CAN_CREATE, {},
                idempotent=True,
            )
            if gate.get("canCreateTrack") is False:
                raise BeatStarsApiError(
                    "BeatStars won't allow a new track — you may have hit your plan's upload limit."
                )
        except BeatStarsApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.info("canCreateTrack check skipped: %s", exc)

        # 1. Create the draft track.
        data = await _graphql(
            client, token, STUDIO_GRAPHQL, "AddTrack", M_ADD_TRACK, {}
        )
        track_id = data["addTrack"]["id"]
        _progress(5)

        # 2. Decide file roles. tagged MP3 = stream/preview (required);
        #    master (WAV/etc) = main download, falling back to the MP3 when
        #    there's no separate master.
        tagged = meta.tagged_path
        master = meta.master_path
        stems = meta.stems_path
        artwork = meta.artwork_path

        # Audio roles: the tagged MP3 is the streamable preview (required by our
        # pipeline); the master (WAV/FLAC/…) is the downloadable main. Cover the
        # three combinations defensively:
        #   both          → stream = MP3,    main = master
        #   MP3 only       → stream = main = the one MP3 (uploaded once)
        #   master only    → stream = main = the master
        if tagged is None and master is None:
            raise BeatStarsApiError("No audio file to upload to BeatStars")

        stream_asset = (
            await _upload_asset(client, token, member_id, tagged)
            if tagged is not None
            else None
        )
        _progress(25)

        if master is not None:
            main_asset = await _upload_asset(client, token, member_id, master)
        else:
            main_asset = stream_asset  # MP3-only: same asset is the main download
        if stream_asset is None:
            stream_asset = main_asset  # master-only: stream from the master
        _progress(50)

        stems_asset = (
            await _upload_asset(client, token, member_id, stems)
            if stems is not None
            else None
        )
        _progress(65)

        artwork_asset = (
            await _upload_asset(client, token, member_id, artwork)
            if artwork is not None
            else None
        )
        _progress(75)

        # 3. Attach the uploaded assets to the track.
        if stream_asset:
            await _graphql(
                client, token, STUDIO_GRAPHQL, "attachStream", M_ATTACH_STREAM,
                {"id": track_id, "assetId": stream_asset},
            )
        if main_asset:
            await _graphql(
                client, token, STUDIO_GRAPHQL, "attachMainAudio", M_ATTACH_MAIN,
                {"id": track_id, "assetId": main_asset},
            )
        if stems_asset:
            await _graphql(
                client, token, STUDIO_GRAPHQL, "attachStems", M_ATTACH_STEMS,
                {"id": track_id, "assetId": stems_asset},
            )
        if artwork_asset:
            await _graphql(
                client, token, STUDIO_GRAPHQL, "trackFormAttachArtwork", M_ATTACH_ARTWORK,
                {"itemId": track_id, "assetId": artwork_asset},
            )
        _progress(85)

        # 4. Resolve genre against the live enum, build the form + contracts.
        genres: list[str] = []
        if meta.genre:
            try:
                md = await _graphql(
                    client, token, STUDIO_GRAPHQL, "GetMetadataProperties", Q_METADATA, {},
                    idempotent=True,
                )
                menu = (md.get("metadataProperties") or {}).get("genres") or []
                enum = _match_genre(menu, meta.genre)
                if enum:
                    genres = [enum]
                else:
                    log.info("Genre %r didn't match a BeatStars enum; skipping", meta.genre)
            except Exception as exc:  # noqa: BLE001 — genre is optional
                log.info("Genre lookup skipped: %s", exc)

        track_input = _build_track(meta, genres)

        contracts: list[dict] = []
        try:
            cdata = await _graphql(
                client, token, STUDIO_GRAPHQL, "GetTrackFormContracts", Q_CONTRACTS,
                {"itemId": track_id, "page": 0, "size": 50}, idempotent=True,
            )
            menu = (cdata.get("publishedContracts") or {}).get("content") or []
            contracts = _build_contracts(track_id, meta, menu)
        except BeatStarsApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Contract lookup failed (publishing with defaults): %s", exc)

        # 5. Save then publish.
        save_vars = {"id": track_id, "track": track_input, "contracts": contracts}
        await _graphql(
            client, token, STUDIO_GRAPHQL, "SaveTrackForm", M_SAVE_TRACK, save_vars
        )
        _progress(92)

        pub = await _graphql(
            client, token, STUDIO_GRAPHQL, "PublishTrackForm", M_PUBLISH_TRACK, save_vars
        )
        published = pub.get("publishTrack") or {}
        public_url = published.get("url") or published.get("shareUrl")
        _progress(100)

        return UploadHandle(
            external_id=str(published.get("id") or track_id),
            public_url=public_url,
            # Persisted back by the job processor — keeps rotated tokens warm.
            session_data=session,
        )
