"""Tests for the SoundCloud OAuth connector.

The OAuth + upload flow is exercised against an httpx MockTransport standing in
for secure.soundcloud.com / api.soundcloud.com. This verifies our request
shaping (PKCE, token exchange, multipart /tracks, token refresh) — it can't
confirm SoundCloud accepts the exact shapes until real credentials exist.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.security import decrypt_token, encrypt_token
from app.services.platforms import soundcloud as sc
from app.services.platforms.base import BeatMetadata


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        sc.httpx, "AsyncClient", lambda **kw: real(transport=transport)
    )


def test_is_configured_reflects_credentials(monkeypatch):
    def fake_settings(client_id):
        return lambda: type("S", (), {"soundcloud_client_id": client_id})()

    monkeypatch.setattr(sc, "get_settings", fake_settings(""))
    assert sc.SoundCloudConnector().is_configured() is False
    monkeypatch.setattr(sc, "get_settings", fake_settings("cid"))
    assert sc.SoundCloudConnector().is_configured() is True


def test_pkce_and_state_roundtrip():
    verifier, challenge = sc._gen_pkce()
    assert verifier != challenge and len(challenge) >= 40
    uid, cv = sc.verify_state(sc.make_state(42, verifier))
    assert uid == 42 and cv == verifier


async def test_complete_authorize_exchanges_code(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            assert b"grant_type=authorization_code" in request.content
            assert b"code_verifier=verifier-abc" in request.content
            return httpx.Response(200, json={
                "access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        if request.url.path == "/me":
            return httpx.Response(200, json={"username": "DJ Test"})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    state = sc.make_state(1, "verifier-abc")
    data = await sc.SoundCloudConnector().complete_authorize(
        code="THE_CODE", state=state, redirect_uri=""
    )
    assert decrypt_token(data["access_token_encrypted"]) == "AT"
    assert decrypt_token(data["refresh_token_encrypted"]) == "RT"
    assert data["account_label"] == "DJ Test"
    assert data["expires_at"] > datetime.now(UTC)


class _Conn:
    def __init__(self, *, expires_in_hours: float = 1.0):
        self.access_token_encrypted = encrypt_token("AT")
        self.refresh_token_encrypted = encrypt_token("RT")
        self.expires_at = datetime.now(UTC) + timedelta(hours=expires_in_hours)


async def test_upload_posts_multipart_track(tmp_path, monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tracks":
            captured["auth"] = request.headers.get("authorization")
            captured["ct"] = request.headers.get("content-type", "")
            captured["body"] = request.content
            return httpx.Response(201, json={
                "id": 12345, "permalink_url": "https://soundcloud.com/dj/beat"})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    mp3 = tmp_path / "beat.mp3"
    mp3.write_bytes(b"audio-bytes")
    art = tmp_path / "cover.jpg"
    art.write_bytes(b"img")
    meta = BeatMetadata(
        title="My Beat", tags=["trap", "dark vibes"], bpm=140, music_key="C# min",
        price_cents=None, tagged_path=mp3, artwork_path=art, genre="Trap",
    )
    handle = await sc.SoundCloudConnector().upload(_Conn(), file_path=mp3, meta=meta)

    assert handle.external_id == "12345"
    assert handle.public_url == "https://soundcloud.com/dj/beat"
    assert captured["auth"] == "OAuth AT"
    assert "multipart/form-data" in captured["ct"]
    body = captured["body"]
    assert b'name="track[title]"' in body
    assert b'name="track[asset_data]"' in body
    assert b'name="track[artwork_data]"' in body
    # multi-word tag gets quoted in the space-separated tag_list
    assert b'"dark vibes"' in body


async def test_upload_refreshes_expired_token(tmp_path, monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            assert b"grant_type=refresh_token" in request.content
            calls.append("refresh")
            return httpx.Response(200, json={
                "access_token": "NEW", "refresh_token": "RT2", "expires_in": 3600})
        if request.url.path == "/tracks":
            calls.append(request.headers.get("authorization", ""))
            return httpx.Response(201, json={"id": 1, "permalink_url": "u"})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    conn = _Conn(expires_in_hours=-0.1)  # already expired
    mp3 = tmp_path / "b.mp3"
    mp3.write_bytes(b"a")
    meta = BeatMetadata(
        title="t", tags=[], bpm=None, music_key=None, price_cents=None, tagged_path=mp3
    )
    await sc.SoundCloudConnector().upload(conn, file_path=mp3, meta=meta)

    assert calls == ["refresh", "OAuth NEW"]  # refreshed first, then used the new token
    assert decrypt_token(conn.access_token_encrypted) == "NEW"  # persisted back
    assert decrypt_token(conn.refresh_token_encrypted) == "RT2"
