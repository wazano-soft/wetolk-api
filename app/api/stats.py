from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Conversation, Message, ReferralVisit

router = APIRouter()


class StatsResponse(BaseModel):
    visits_this_month: int
    conversations: int
    questions_answered: int


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> StatsResponse:
    candidate = _get_candidate(db, user)
    month_start = date.today().replace(day=1)

    visits_this_month = db.scalar(
        select(func.count())
        .select_from(ReferralVisit)
        .where(
            ReferralVisit.candidate_id == candidate.id,
            ReferralVisit.is_valid.is_(True),
            ReferralVisit.visit_date >= month_start,
        )
    )

    conversations = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.candidate_id == candidate.id)
    )

    questions_answered = db.scalar(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.candidate_id == candidate.id,
            Message.role == "assistant",
        )
    )

    return StatsResponse(
        visits_this_month=visits_this_month or 0,
        conversations=conversations or 0,
        questions_answered=questions_answered or 0,
    )
