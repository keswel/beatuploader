from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except ValueError as exc:
        raise credentials_exc from exc

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError) as exc:
        raise credentials_exc from exc

    user = await db.get(User, user_id_int)
    if user is None:
        raise credentials_exc

    # Password-change revocation: any JWT issued before the user's most recent
    # password change is invalid. Uses iat (issued-at) from the token vs.
    # password_changed_at on the user row.
    if user.password_changed_at is not None:
        iat = payload.get("iat")
        # iat from python-jose comes back as int (seconds since epoch).
        if iat is None:
            raise credentials_exc
        try:
            iat_dt = datetime.fromtimestamp(int(iat), tz=UTC)
        except (TypeError, ValueError, OSError) as exc:
            raise credentials_exc from exc
        # SQLite (dev) loses tzinfo on round-trip for DateTime(timezone=True).
        # Postgres preserves it. We always *write* UTC-aware values via
        # datetime.now(UTC), so a naive value coming back is safe to treat
        # as UTC. Coerce so the comparison below works in both backends.
        changed_at = user.password_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=UTC)
        # Allow 1s slack to absorb sub-second clock differences when a token
        # is issued in the same request that sets password_changed_at.
        if iat_dt < changed_at.replace(microsecond=0):
            raise credentials_exc

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def db_generator() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session
