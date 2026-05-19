from fastapi import APIRouter
from sqlalchemy import desc, select

from app.deps import CurrentUser, DbSession
from app.models.beat import Beat
from app.schemas.beat import BeatOut

router = APIRouter(prefix="/library", tags=["library"])


@router.get("", response_model=list[BeatOut])
async def list_beats(
    user: CurrentUser,
    db: DbSession,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BeatOut]:
    stmt = select(Beat).where(Beat.user_id == user.id)
    if q:
        stmt = stmt.where(Beat.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(desc(Beat.created_at)).limit(limit).offset(offset)
    rows = await db.scalars(stmt)
    return [BeatOut.model_validate(r) for r in rows]
