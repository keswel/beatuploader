import asyncio
import logging
import queue
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

log = logging.getLogger(__name__)

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models.platform import PlatformConnection, PlatformProvider, PlatformStatus
from app.schemas.platform import (
    BeatStarsCredentials,
    BeatStarsSmsSubmit,
    PlatformOut,
)
from app.services.platforms import get_connector, list_connectors
from app.services.platforms._challenges import (
    cancel_challenge as cancel_bs_challenge,
    create_challenge as create_bs_challenge,
    get_challenge as get_bs_challenge,
    is_cancel_sentinel,
    remove_challenge as remove_bs_challenge,
)
from app.services.platforms.beatstars import (
    SmsCancelled,
    SmsHandler,
    connect_with_credentials as beatstars_connect_with_credentials,
)
from app.services.platforms.youtube import verify_state
from app.services.rate_limit import (
    beatstars_credentials_limiter,
    beatstars_sms_limiter,
    limit_dependency,
)

# Per-user worker stays parked on the SMS page for this long before timing out.
# Matches the in-memory challenge TTL (10 min) loosely; the queue timeout below
# is what actually kills the browser.
_SMS_WAIT_TIMEOUT_S = 300

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


async def _persist_beatstars_connection(
    *, db, user_id: int, password_enc: str, session_enc: str, label: str
) -> None:
    existing = await db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == PlatformProvider.beatstars,
        )
    )
    if existing is None:
        existing = PlatformConnection(
            user_id=user_id, provider=PlatformProvider.beatstars
        )
        db.add(existing)

    existing.account_label = label
    existing.access_token_encrypted = password_enc  # password lives here for headless providers
    existing.session_data_encrypted = session_enc
    existing.status = PlatformStatus.connected
    existing.last_error = None
    existing.connected_at = datetime.now(UTC)
    await db.commit()


@router.post(
    "/beatstars/credentials",
    dependencies=[Depends(limit_dependency(beatstars_credentials_limiter))],
)
async def beatstars_credentials(
    payload: BeatStarsCredentials,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    """Validate BeatStars credentials by logging in via Playwright, then persist them encrypted.

    If BeatStars challenges us with SMS 2FA, the response is
    ``{"status": "sms_required", "challenge_id": ...}`` and the live login
    session is parked server-side waiting for the code. Follow up with
    POST /beatstars/sms to submit it.
    """
    challenge = create_bs_challenge(user_id=user.id, username=payload.username)
    loop = asyncio.get_running_loop()

    def on_sms_detected(hint: str | None) -> None:
        # Called from the worker thread. Schedule the asyncio Event set + hint
        # update on the main loop.
        def _set() -> None:
            challenge.sms_hint = hint
            challenge.sms_event.set()

        loop.call_soon_threadsafe(_set)

    def get_code_blocking() -> str | None:
        try:
            item = challenge.code_queue.get(timeout=_SMS_WAIT_TIMEOUT_S)
        except queue.Empty:
            return None
        if is_cancel_sentinel(item):
            return None
        return str(item)

    handler = SmsHandler(on_detected=on_sms_detected, get_code=get_code_blocking)

    worker_task = asyncio.create_task(
        beatstars_connect_with_credentials(
            username=payload.username,
            password=payload.password,
            sms_handler=handler,
        )
    )
    sms_wait = asyncio.create_task(challenge.sms_event.wait())

    try:
        done, pending = await asyncio.wait(
            {worker_task, sms_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
    except BaseException:
        # Best-effort cleanup if our own awaiting is cancelled.
        sms_wait.cancel()
        worker_task.cancel()
        remove_bs_challenge(challenge.id)
        raise

    if worker_task in done:
        # Login completed (or failed) without ever reaching SMS.
        sms_wait.cancel()
        remove_bs_challenge(challenge.id)
        try:
            password_enc, session_enc, label = worker_task.result()
        except (RuntimeError, SmsCancelled) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception as exc:
            # TEMPORARY DEBUG: Render free-tier log pipeline is swallowing our
            # tracebacks, so surface the real exception in the HTTP response to
            # debug remotely. REVERT to the generic message once diagnosed —
            # exposing exception internals to clients is a security smell.
            import sys
            import traceback
            print(
                f"[beatstars-credentials] worker failed: {type(exc).__name__}: {exc}",
                file=sys.stdout,
                flush=True,
            )
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            log.exception("BeatStars credentials login failed")
            tb = traceback.format_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"DEBUG {type(exc).__name__}: {exc}\n{tb[-1500:]}",
            )

        await _persist_beatstars_connection(
            db=db,
            user_id=user.id,
            password_enc=password_enc,
            session_enc=session_enc,
            label=label,
        )
        return {"status": "connected", "account_label": label}

    # SMS branch — worker is parked at the verify page waiting for a code.
    # Stash the task on the challenge; the /beatstars/sms endpoint awaits it.
    challenge.worker_task = worker_task
    return {
        "status": "sms_required",
        "challenge_id": challenge.id,
        "hint": challenge.sms_hint
        or "BeatStars sent a verification code to your phone.",
    }


@router.post(
    "/beatstars/sms",
    dependencies=[Depends(limit_dependency(beatstars_sms_limiter))],
)
async def beatstars_sms_submit(
    payload: BeatStarsSmsSubmit,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    """Submit the SMS verification code for an in-flight BeatStars login."""
    code = payload.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Code is required"
        )

    challenge = get_bs_challenge(payload.challenge_id)
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge expired — start over from the Connect dialog.",
        )
    if challenge.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if challenge.worker_task is None:
        # SMS event never fired or another SMS submit already consumed the task.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This challenge is not awaiting an SMS code.",
        )

    try:
        challenge.code_queue.put_nowait(code)
    except queue.Full:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A code is already being verified for this challenge.",
        )

    worker_task = challenge.worker_task
    try:
        password_enc, session_enc, label = await worker_task
    except (RuntimeError, SmsCancelled) as exc:
        remove_bs_challenge(challenge.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception:
        remove_bs_challenge(challenge.id)
        log.exception("BeatStars SMS submission failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Couldn't complete BeatStars verification",
        )

    await _persist_beatstars_connection(
        db=db,
        user_id=user.id,
        password_enc=password_enc,
        session_enc=session_enc,
        label=label,
    )
    remove_bs_challenge(challenge.id)
    return {"status": "connected", "account_label": label}


@router.delete("/beatstars/sms/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def beatstars_sms_cancel(
    challenge_id: str,
    user: CurrentUser,
) -> None:
    """Abort an in-flight BeatStars SMS challenge (closes the parked browser)."""
    challenge = get_bs_challenge(challenge_id)
    if challenge is None:
        return  # already gone
    if challenge.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    cancel_bs_challenge(challenge_id)
    # We don't await the worker_task here — it will exit on its own as the
    # code_queue receives the cancel sentinel and the login raises SmsCancelled.
    return None


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
