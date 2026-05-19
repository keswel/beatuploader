import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

log = logging.getLogger(__name__)

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models.user import User
from app.schemas.user import (
    AccountDelete,
    PasswordChange,
    Token,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)
from app.security import create_access_token, hash_password, verify_password
from app.services.google_signin import (
    authorize_url as google_authorize_url,
    exchange_code as google_exchange_code,
    signin_or_create_user,
    upsert_youtube_connection,
    verify_id_token as google_verify_id_token,
    verify_signin_state,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: DbSession) -> Token:
    existing = await db.scalar(
        select(User).where((User.email == payload.email) | (User.handle == payload.handle))
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or handle already in use",
        )

    user = User(
        email=payload.email,
        handle=payload.handle,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Race condition: someone else grabbed the email/handle between our
        # SELECT above and the INSERT here. Treat as a normal conflict.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or handle already in use",
        ) from exc
    await db.refresh(user)

    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, db: DbSession) -> Token:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if (
        user is None
        or user.password_hash is None
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate, user: CurrentUser, db: DbSession
) -> UserOut:
    if payload.handle is not None and payload.handle != user.handle:
        clash = await db.scalar(select(User).where(User.handle == payload.handle))
        if clash is not None and clash.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Handle already taken"
            )
        user.handle = payload.handle
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange, user: CurrentUser, db: DbSession
) -> None:
    # Users with an existing password must verify it before changing.
    # Google-only users (password_hash is None) can set one without verification.
    if user.password_hash is not None:
        if not payload.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password required",
            )
        if not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )
    user.password_hash = hash_password(payload.new_password)
    await db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    payload: AccountDelete, user: CurrentUser, db: DbSession
) -> None:
    if payload.confirm_handle != user.handle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Handle confirmation didn't match",
        )
    # Cascade deletes platform connections, uploads, beats (configured in models)
    await db.delete(user)
    await db.commit()


@router.post("/google/start")
async def google_signin_start() -> dict:
    try:
        url, state = google_authorize_url()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"authorize_url": url, "state": state}


@router.get("/google/callback")
async def google_signin_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    settings = get_settings()
    frontend = settings.frontend_base_url.rstrip("/")

    def _fragment_redirect(params: dict[str, str]) -> RedirectResponse:
        # Put params in the URL fragment so they don't go to server logs
        return RedirectResponse(f"{frontend}/auth/google#{urlencode(params)}", status_code=302)

    if error:
        return _fragment_redirect({"status": "error", "detail": error})

    if not code or not state:
        return _fragment_redirect({"status": "error", "detail": "missing_code"})

    try:
        verify_signin_state(state)
    except Exception:
        return _fragment_redirect({"status": "error", "detail": "invalid_state"})

    try:
        tokens = await google_exchange_code(code)
    except Exception:
        log.exception("Google OAuth code exchange failed")
        return _fragment_redirect({"status": "error", "detail": "exchange_failed"})

    try:
        claims = google_verify_id_token(tokens["id_token"])
    except Exception:
        log.exception("Google ID token verification failed")
        return _fragment_redirect({"status": "error", "detail": "id_token_invalid"})

    if not claims.get("email_verified", False):
        return _fragment_redirect({"status": "error", "detail": "email_not_verified"})

    user = await signin_or_create_user(db, claims=claims)

    await upsert_youtube_connection(
        db,
        user=user,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        expires_in=int(tokens.get("expires_in", 3600)),
    )

    jwt_token = create_access_token(subject=str(user.id))
    return _fragment_redirect({"status": "ok", "token": jwt_token})
