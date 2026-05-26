"""Tests for the httpx-based BeatStars connector.

The full upload flow is exercised end-to-end against an httpx MockTransport that
stands in for BeatStars' GraphQL + S3 endpoints — so we verify the orchestration
(create → upload → attach → save → publish), the contract/price mapping, and the
genre enum resolution without touching the network.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx
import pytest

from app.security import encrypt_token
from app.services.platforms import _beatstars_http as bh
from app.services.platforms.base import BeatMetadata


async def _noop_sleep(*_args, **_kwargs):
    """Stand-in for asyncio.sleep so retry-backoff doesn't slow tests."""
    return None

# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_content_type_and_bts_type():
    assert bh._content_type(Path("a.mp3")) == "audio/mpeg"
    assert bh._content_type(Path("a.wav")) == "audio/wav"
    assert bh._bts_type(Path("a.mp3")) == "AUDIO"
    assert bh._bts_type(Path("a.zip")) == "BINARY"
    assert bh._bts_type(Path("cover.jpg")) == "IMAGE"


def test_match_genre():
    menu = [
        {"key": "HIP_HOP", "value": "Hip Hop"},
        {"key": "ALTERNATIVE_RNB", "value": "Alternative R&B"},
        {"key": "TRAP", "value": "Trap"},
    ]
    assert bh._match_genre(menu, "hip hop") == "HIP_HOP"  # case-insensitive value match
    assert bh._match_genre(menu, "Trap") == "TRAP"
    assert bh._match_genre(menu, "HIP_HOP") == "HIP_HOP"  # enum-key fallback
    assert bh._match_genre(menu, "Polka") is None  # unknown → skip, never guess


def test_build_contracts_auto_prices_highest_tier_only(tmp_path):
    master = tmp_path / "beat.wav"
    tagged = tmp_path / "beat.mp3"
    stems = tmp_path / "beat.zip"
    for f in (master, tagged, stems):
        f.write_bytes(b"x")
    meta = BeatMetadata(
        title="t", tags=[], bpm=140, music_key=None, price_cents=5000,
        master_path=master, tagged_path=tagged, stems_path=stems,
        license_type="AUTO",
    )
    menu = [
        {"id": "C_PREM", "title": "Premium License", "defaultPrice": 34.99},
        {"id": "C_UNL", "title": "Unlimited License", "defaultPrice": 49.99},
        {"id": "C_EXC", "title": "Exclusive License", "defaultPrice": 129.99},
    ]
    contracts = bh._build_contracts("TK1", meta, menu)
    by_id = {c["contractId"]: c for c in contracts}
    # AUTO with WAV + stems enables Premium, Unlimited, Exclusive
    assert set(by_id) == {"C_PREM", "C_UNL", "C_EXC"}
    # User's $50 applies to the highest tier (Exclusive) only; others keep defaults
    assert by_id["C_EXC"]["price"] == 50.0
    assert by_id["C_PREM"]["price"] == 34.99
    assert by_id["C_UNL"]["price"] == 49.99
    assert all(c["enabled"] and c["itemId"] == "TK1" for c in contracts)


def test_build_contracts_mp3_only_is_empty(tmp_path):
    tagged = tmp_path / "beat.mp3"
    tagged.write_bytes(b"x")
    meta = BeatMetadata(
        title="t", tags=[], bpm=None, music_key=None, price_cents=None,
        tagged_path=tagged, license_type="AUTO",
    )
    # MP3-only AUTO → Basic is account-default; send nothing.
    assert bh._build_contracts("TK1", meta, []) == []


# ─────────────────────────────────────────────────────────────────────────────
# Full upload flow against a mock transport
# ─────────────────────────────────────────────────────────────────────────────


def _fake_jwt(member_id: str = "MR123", ttl: int = 3600) -> str:
    def seg(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    payload = {"exp": int(time.time()) + ttl, "user_name": member_id}
    return f"{seg({'alg': 'RS256'})}.{seg(payload)}.sig"


class _FakeConn:
    def __init__(self, session: dict, password: str, label: str):
        self.session_data_encrypted = encrypt_token(json.dumps(session))
        self.access_token_encrypted = encrypt_token(password)
        self.account_label = label


def _make_handler(calls: list[str], captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "s3-accelerate.amazonaws.com" in url:
            calls.append("S3_PUT")
            return httpx.Response(201, text="<PostResponse><Key>k</Key></PostResponse>")
        if "uppy-v4.beatstars.net/s3/params" in url:
            calls.append("s3/params")
            return httpx.Response(
                200,
                json={
                    "method": "POST",
                    "url": "https://bts-content.s3-accelerate.amazonaws.com/",
                    "fields": {"key": "k", "Policy": "p", "X-Amz-Signature": "s"},
                },
            )
        # GraphQL
        body = json.loads(request.content)
        op = body.get("operationName")
        calls.append(op)
        variables = body.get("variables", {})
        captured[op] = variables
        data: dict
        if op == "canCreateTrack":
            data = {"canCreateTrack": True}
        elif op == "AddTrack":
            data = {"addTrack": {"id": "TK1"}}
        elif op == "createAssetFile":
            name = variables["file"]["fileName"]
            aid = f"AID:{name}"
            data = {"create": {"id": aid, "file": {"assetId": aid, "type": "AUDIO"}}}
        elif op == "attachStream":
            data = {"attachStreamFile": "Ok"}
        elif op == "attachMainAudio":
            data = {"attachMainAudioFile": "Ok"}
        elif op == "attachStems":
            data = {"attachStemsFile": "Ok"}
        elif op == "trackFormAttachArtwork":
            data = {"attachArtwork": "Ok"}
        elif op == "GetMetadataProperties":
            data = {"metadataProperties": {"genres": [{"key": "TRAP", "value": "Trap"}]}}
        elif op == "GetTrackFormContracts":
            data = {"publishedContracts": {"content": [
                {"id": "C_PREM", "title": "Premium License", "defaultPrice": 34.99},
                {"id": "C_UNL", "title": "Unlimited License", "defaultPrice": 49.99},
            ], "totalElements": 2}}
        elif op == "SaveTrackForm":
            data = {"saveTrack": {"id": "TK1"}}
        elif op == "PublishTrackForm":
            data = {"publishTrack": {
                "id": "TK1", "status": "PUBLISHED",
                "url": "https://www.beatstars.com/beat/1",
                "shareUrl": "https://bsta.rs/x",
            }}
        else:
            return httpx.Response(200, json={"errors": [{"message": f"unexpected op {op}"}]})
        return httpx.Response(200, json={"data": data})

    return handler


class _Mock:
    def __init__(self):
        self.calls: list[str] = []
        self.captured: dict = {}


@pytest.fixture
def mock_client(monkeypatch):
    mock = _Mock()
    transport = httpx.MockTransport(_make_handler(mock.calls, mock.captured))
    monkeypatch.setattr(
        bh, "_new_client", lambda: httpx.AsyncClient(transport=transport)
    )
    return mock


async def test_full_upload_flow(tmp_path, mock_client):
    master = tmp_path / "beat.wav"
    tagged = tmp_path / "beat.mp3"
    artwork = tmp_path / "cover.jpg"
    for f in (master, tagged, artwork):
        f.write_bytes(b"audio-bytes")

    session = {
        "access_token": _fake_jwt(),
        "refresh_token": "r",
        "expires_at": int(time.time()) + 3600,
        "member_id": "MR123",
        "account_label": "keswel",
    }
    conn = _FakeConn(session, password="pw", label="keswel")

    seen_pct: list[int] = []
    meta = BeatMetadata(
        title="My Beat", tags=["trap", "dark"], bpm=140, music_key="C# min",
        price_cents=4000, master_path=master, tagged_path=tagged,
        artwork_path=artwork, license_type="AUTO", genre="Trap",
    )

    handle = await bh.upload(
        conn, file_path=tagged, meta=meta, progress_cb=seen_pct.append
    )

    assert handle.public_url == "https://www.beatstars.com/beat/1"
    assert handle.external_id == "TK1"
    # Session is returned (loaded fresh from the connection) so the job processor
    # can persist any rotated tokens back.
    assert handle.session_data is not None
    assert handle.session_data["member_id"] == "MR123"

    # The full sequence ran, in order, with the right attach calls
    calls = mock_client.calls
    assert calls.index("AddTrack") < calls.index("PublishTrackForm")
    assert "attachStream" in calls  # tagged mp3
    assert "attachMainAudio" in calls  # master wav
    assert "trackFormAttachArtwork" in calls
    assert "attachStems" not in calls  # none provided
    assert calls.count("S3_PUT") == 3  # mp3 + wav + jpg
    # Progress climbed to 100
    assert seen_pct and seen_pct[-1] == 100

    # Publish payload is shaped right: freeDownloadSettings present (off),
    # genre resolved to the enum, and AUTO licenses priced.
    pub = mock_client.captured["PublishTrackForm"]
    track = pub["track"]
    assert track["freeDownloadSettings"] == {"enabled": False}
    assert track["metadata"]["genres"] == ["TRAP"]
    assert track["metadata"]["keyNote"] == "C_SHARP_MINOR"
    assert {c["contractId"] for c in pub["contracts"]} == {"C_PREM", "C_UNL"}


async def test_mp3_only_attaches_one_asset_to_both_roles(tmp_path, mock_client):
    """No master WAV: the single MP3 is uploaded once and attached as both the
    stream preview and the main download."""
    tagged = tmp_path / "beat.mp3"
    tagged.write_bytes(b"mp3")

    session = {
        "access_token": _fake_jwt(),
        "refresh_token": "r",
        "expires_at": int(time.time()) + 3600,
        "member_id": "MR123",
        "account_label": "keswel",
    }
    conn = _FakeConn(session, password="pw", label="keswel")
    meta = BeatMetadata(
        title="MP3 Only", tags=[], bpm=None, music_key=None, price_cents=None,
        tagged_path=tagged, license_type="AUTO",
    )

    await bh.upload(conn, file_path=tagged, meta=meta)

    # Only one file uploaded, but both stream + main attached to its asset
    assert mock_client.calls.count("S3_PUT") == 1
    assert mock_client.captured["attachStream"]["assetId"] == "AID:beat.mp3"
    assert mock_client.captured["attachMainAudio"]["assetId"] == "AID:beat.mp3"
    # MP3-only AUTO sends no explicit contracts (Basic is the account default)
    assert mock_client.captured["PublishTrackForm"]["contracts"] == []


async def test_login_password_grant(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/auth/graphql") or "auth/graphql" in url:
            calls.append("identifierAvailable")
            return httpx.Response(200, json={"data": {"identifierAvailable": {
                "available": False, "profileDetails": {"username": "keswel"}}}})
        if "/auth/oauth/token" in url:
            calls.append("token")
            assert b"grant_type=password" in request.content
            return httpx.Response(200, json={
                "access_token": _fake_jwt("MR999"),
                "token_type": "bearer",
                "refresh_token": "refresh-xyz",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(bh, "_new_client", lambda: httpx.AsyncClient(transport=transport))

    session = await bh.login("keswel@example.com", "secret")
    assert session["member_id"] == "MR999"
    assert session["refresh_token"] == "refresh-xyz"
    assert session["account_label"] == "keswel"
    assert "token" in calls


async def test_login_survives_identifier_gateway_timeout(monkeypatch):
    """A GATEWAY_TIMEOUT on the optional identifierAvailable check must NOT block
    login — we fall through to the password grant."""
    monkeypatch.setattr(bh.asyncio, "sleep", _noop_sleep)  # skip retry backoff

    def handler(request: httpx.Request) -> httpx.Response:
        if "auth/graphql" in str(request.url):
            return httpx.Response(200, json={"errors": [{"message": "GATEWAY_TIMEOUT"}]})
        if "/auth/oauth/token" in str(request.url):
            return httpx.Response(200, json={
                "access_token": _fake_jwt("MR42"), "refresh_token": "r"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(bh, "_new_client", lambda: httpx.AsyncClient(transport=transport))

    session = await bh.login("real@example.com", "correct-pw")
    assert session["member_id"] == "MR42"  # login succeeded despite the timeout


async def test_password_grant_5xx_is_not_bad_credentials(monkeypatch):
    """A 5xx from the token endpoint must not be reported as 'wrong password'."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "auth/graphql" in str(request.url):
            return httpx.Response(200, json={"data": {"identifierAvailable": {
                "available": False, "profileDetails": {"username": "x"}}}})
        return httpx.Response(503, text="upstream timeout")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(bh, "_new_client", lambda: httpx.AsyncClient(transport=transport))

    with pytest.raises(bh.BeatStarsApiError, match="temporarily unavailable"):
        await bh.login("real@example.com", "correct-pw")


async def test_login_no_account(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if "auth/graphql" in str(request.url):
            return httpx.Response(200, json={"data": {"identifierAvailable": {
                "available": True, "profileDetails": None}}})
        return httpx.Response(200, json={"access_token": _fake_jwt()})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(bh, "_new_client", lambda: httpx.AsyncClient(transport=transport))

    with pytest.raises(bh.BeatStarsApiError, match="No BeatStars account"):
        await bh.login("ghost@example.com", "secret")
