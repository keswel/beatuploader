import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

log = logging.getLogger(__name__)

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models.platform import PlatformConnection, PlatformProvider, PlatformStatus
from app.schemas.platform import BeatStarsCredentials, PlatformOut
from app.services.platforms import get_connector, list_connectors
from app.services.platforms.beatstars import (
    connect_with_credentials as beatstars_connect_with_credentials,
)
from app.services.platforms.youtube import verify_state

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("", response_model=list[PlatformOut])
async def list_user_platforms(user: CurrentUser, db: DbSession) -> list[PlatformOut]:
    rows = await db.scalars(
        select(PlatformConnection).where(PlatformConnection.user_id == user.id)
    )
    by_provider = {row.provider: row for row in rows}

    out: list[PlatformOut] = []
    for connector in list_connectors():
        existing = by_provider.get(connector.provider)
        if existing is not None:
            out.append(PlatformOut.model_validate(existing))
        else:
            out.append(
                PlatformOut(
                    id=0,
                    provider=connector.provider,
                    status=PlatformStatus.disconnected,
                    account_label=None,
                    connected_at=None,
                    last_error=None,
                )
            )
    return out


@router.post("/{provider}/connect")
async def start_connect(provider: PlatformProvider, user: CurrentUser) -> dict:
    """Begin OAuth flow. Frontend redirects user to authorize_url."""
    connector = get_connector(provider)
    try:
        redirect = await connector.start_authorize(
            user_id=user.id,
            redirect_uri="",  # connectors compute their own callback URL from settings
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    return {"authorize_url": redirect.authorize_url, "state": redirect.state}


@router.get("/youtube/callback")
async def youtube_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    frontend = settings.frontend_base_url.rstrip("/")

    def _redirect(params: dict[str, str]) -> RedirectResponse:
        return RedirectResponse(f"{frontend}/platforms?{urlencode(params)}", status_code=302)

    if error:
        return _redirect({"status": "error", "provider": "youtube", "detail": error})

    if not code or not state:
        return _redirect({"status": "error", "provider": "youtube", "detail": "missing_code"})

    try:
        user_id = verify_state(state)
    except Exception:
        return _redirect({"status": "error", "provider": "youtube", "detail": "invalid_state"})

    connector = get_connector(PlatformProvider.youtube)
    try:
        token_data = await connector.complete_authorize(code=code, state=state, redirect_uri="")
    except Exception:
        log.exception("YouTube OAuth complete_authorize failed")
        return _redirect(
            {"status": "error", "provider": "youtube", "detail": "exchange_failed"}
        )

    # Upsert connection
    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == PlatformProvider.youtube,
        )
    )
    if existing is None:
        existing = PlatformConnection(
            user_id=user_id, provider=PlatformProvider.youtube
        )
        db.add(existing)

    existing.access_token_encrypted = token_data["access_token_encrypted"]
    existing.refresh_token_encrypted = token_data.get("refresh_token_encrypted")
    existing.expires_at = token_data.get("expires_at")
    existing.account_label = token_data.get("account_label")
    existing.status = PlatformStatus.connected
    existing.last_error = None
    existing.connected_at = datetime.now(UTC)

    await db.commit()
    return _redirect({"status": "connected", "provider": "youtube"})


@router.post("/beatstars/credentials")
async def beatstars_credentials(
    payload: BeatStarsCredentials,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    """Validate BeatStars credentials by logging in via Playwright, then persist them encrypted."""
    try:
        password_enc, session_enc, label = await beatstars_connect_with_credentials(
            username=payload.username, password=payload.password
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id,
            PlatformConnection.provider == PlatformProvider.beatstars,
        )
    )
    if existing is None:
        existing = PlatformConnection(
            user_id=user.id, provider=PlatformProvider.beatstars
        )
        db.add(existing)

    existing.account_label = label
    existing.access_token_encrypted = password_enc  # password lives here for headless providers
    existing.session_data_encrypted = session_enc
    existing.status = PlatformStatus.connected
    existing.last_error = None
    existing.connected_at = datetime.now(UTC)
    await db.commit()

    return {"status": "connected", "account_label": label}


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    provider: PlatformProvider,
    user: CurrentUser,
    db: DbSession,
) -> None:
    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id,
            PlatformConnection.provider == provider,
        )
    )
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not connected")

    connector = get_connector(provider)
    await connector.disconnect(existing)
    await db.delete(existing)
    await db.commit()
