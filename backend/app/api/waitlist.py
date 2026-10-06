"""Early-release signup from the public landing page. Stores the email only."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.deps import DbSession
from app.models.waitlist import WaitlistSignup
from app.services.rate_limit import limit_dependency, waitlist_limiter

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

# The public count is rounded down to this step. An exact count would reveal
# whether an address was already on the list: sign it up and see if the number
# moves. Rounding means only the signup that crosses a step changes it.
COUNT_STEP = 5


class WaitlistJoin(BaseModel):
    email: EmailStr


class WaitlistCount(BaseModel):
    count: int  # rounded down to a multiple of COUNT_STEP


@router.get("/count", response_model=WaitlistCount)
async def waitlist_count(db: DbSession) -> WaitlistCount:
    count = await db.scalar(select(func.count()).select_from(WaitlistSignup)) or 0
    return WaitlistCount(count=count - count % COUNT_STEP)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_dependency(waitlist_limiter))],
)
async def join_waitlist(payload: WaitlistJoin, db: DbSession) -> None:
    # A repeat address gets the same response as a new one, and goes through
    # the same single INSERT ... ON CONFLICT DO NOTHING, so neither the reply
    # nor its timing shows whether someone is already on the list.
    email = payload.email.strip().lower()
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    await db.execute(
        insert(WaitlistSignup)
        .values(email=email)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    await db.commit()
