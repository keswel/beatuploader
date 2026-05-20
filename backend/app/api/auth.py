import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserLogin,
    UserOut,
    UserRegister,
    UserUpdate,
)
from app.security import create_access_token, hash_password, verify_password
from app.services.email import send_email
from app.services.google_signin import (
    authorize_url as google_authorize_url,
    exchange_code as google_exchange_code,
    signin_or_create_user,
    upsert_youtube_connection,
    verify_id_token as google_verify_id_token,
    verify_signin_state,
)
from app.services.password_reset import (
    issue_reset_token,
    reset_link,
    verify_reset_token,
)
from app.services.rate_limit import (
    google_start_limiter,
    limit_dependency,
    login_limiter,
    password_change_limiter,
    password_reset_confirm_limiter,
    password_reset_request_limiter,
    register_limiter,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# A pre-computed bcrypt hash of a constant random password. Used in the login
# branch where the user doesn't exist, so we still pay roughly the same bcrypt
# cost we'd pay for a real user. Prevents timing-side-channel email enumeration.
# (We don't care what value this hash is — its only job is to make verify_password
# do real work in the no-user branch.)
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-constant-time-login")


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_dependency(register_limiter))],
)
async def register(payload: UserRegister, db: DbSession) -> Token:
    existing = await db.scalar(
        select(User).where((User.email == payload.email) | (User.handle == payload.handle))
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or handle already in use",
        )

    now = datetime.now(UTC)
    user = User(
        email=payload.email,
        handle=payload.handle,
        password_hash=hash_password(payload.password),
        # Stamp from the start so password-change-revocation works for the
        # freshly-issued token (iat == password_changed_at, allowed by the
        # 1-second slack in get_current_user).
        password_changed_at=now,
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


@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(limit_dependency(login_limiter))],
)
async def login(payload: UserLogin, db: DbSession) -> Token:
    user = await db.scalar(select(User).where(User.email == payload.email))
    # Constant-time-ish: always run bcrypt, even when the user is unknown or
    # password-less (Google-only). Prevents timing-based email enumeration.
    # The booleans below decide the outcome; verify_password runs either way.
    target_hash = (
        user.password_hash
        if user is not None and user.password_hash is not None
        else _DUMMY_PASSWORD_HASH
    )
    password_ok = verify_password(payload.password, target_hash)
    valid = (
        user is not None
        and user.password_hash is not None
        and password_ok
    )
    if not valid:
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
    # Distinguish "field omitted" (leave alone) from "set to null/empty" (clear).
    if "youtube_description_template" in payload.model_fields_set:
        user.youtube_description_template = payload.youtube_description_template or None
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_dependency(password_change_limiter))],
)
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
    # Bump password_changed_at — invalidates every JWT previously issued for
    # this user (including the one making this request).
    user.password_changed_at = datetime.now(UTC)
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


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_dependency(password_reset_request_limiter))],
)
async def forgot_password(payload: PasswordResetRequest, db: DbSession) -> dict:
    """Email a password-reset link if the address belongs to a real user.

    Response is the same whether the email exists or not — we don't want to
    expose account-existence to anyone hitting this endpoint.
    """
    user = await db.scalar(select(User).where(User.email == payload.email))
    # Only email if the account exists AND has a password (Google-only users
    # don't have one to reset; they should re-sign-in via Google).
    if user is not None and user.password_hash is not None:
        settings = get_settings()
        token = issue_reset_token(user.id)
        link = reset_link(settings.frontend_base_url, token)
        body = (
            f"Hi {user.handle},\n\n"
            f"Someone (hopefully you) asked to reset your Beatuploader password.\n"
            f"Open this link within "
            f"{settings.password_reset_expire_seconds // 60} minutes to choose a "
            f"new one:\n\n{link}\n\n"
            f"If it wasn't you, ignore this email — nothing has changed.\n"
        )
        # Don't await failure-loudly; send_email logs internally and returns.
        await send_email(
            to=user.email,
            subject="Reset your Beatuploader password",
            body=body,
        )
    return {"status": "ok"}


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_dependency(password_reset_confirm_limiter))],
)
async def reset_password(payload: PasswordResetConfirm, db: DbSession) -> None:
    """Consume a reset-token, set the new password, invalidate every JWT."""
    try:
        user_id, token_iat = verify_reset_token(payload.token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Request a new one.",
        ) from exc

    user = await db.get(User, user_id)
    if user is None:
        # Account deleted between request and use. Don't disclose; clients see
        # the same error either way.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired. Request a new one.",
        )

    # Single-use enforcement: if the user already reset their password using
    # this (or any) token, password_changed_at will have advanced past the
    # token's iat. Rejecting here means each link works exactly once.
    if (
        user.password_changed_at is not None
        and token_iat < user.password_changed_at.replace(microsecond=0)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link has already been used. Request a new one.",
        )

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(UTC)
    await db.commit()


@router.post(
    "/google/start",
    dependencies=[Depends(limit_dependency(google_start_limiter))],
)
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
    code: str | None = Query(default=None, max_length=2048),
    state: str | None = Query(default=None, max_length=2048),
    error: str | None = Query(default=None, max_length=256),
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
