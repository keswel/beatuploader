"""Early-release signup from the public landing page. Stores the email only."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import DbSession
from app.models.waitlist import WaitlistSignup
from app.services.rate_limit import limit_dependency, waitlist_limiter

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


class WaitlistJoin(BaseModel):
    email: EmailStr


class WaitlistCount(BaseModel):
    count: int


@router.get("/count", response_model=WaitlistCount)
async def waitlist_count(db: DbSession) -> WaitlistCount:
    count = await db.scalar(select(func.count()).select_from(WaitlistSignup))
    return WaitlistCount(count=count or 0)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_dependency(waitlist_limiter))],
)
async def join_waitlist(payload: WaitlistJoin, db: DbSession) -> None:
    # Same response whether or not the address was already on the list, so the
    # endpoint can't be used to check who signed up.
    email = payload.email.strip().lower()
    exists = await db.scalar(
        select(WaitlistSignup.id).where(WaitlistSignup.email == email)
    )
    if exists:
        return
    db.add(WaitlistSignup(email=email))
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent signup with the same address won the insert.
        await db.rollback()
