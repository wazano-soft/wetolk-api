from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Conversation, Message, ReferralVisit, Search, Share

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


class ChannelBreakdown(BaseModel):
    channel: str
    shares: int
    visits: int
    valid_visits: int


class FrequentQuestion(BaseModel):
    question: str
    count: int


class DetailedStatsResponse(BaseModel):
    visits_total: int
    visits_valid: int
    conversion_rate: float
    knowledge_gaps: int
    recruiter_search_appearances: int
    channels: list[ChannelBreakdown]
    frequent_questions: list[FrequentQuestion]


# El agente responde con esta frase exacta (ver AGENT_SYSTEM_PROMPT en
# agent_prompt.py) cuando le preguntan algo que no está en el CV -- contar
# cuántas veces aparece es una señal aproximada, no exacta, de qué le
# falta completar al candidato en su perfil.
_KNOWLEDGE_GAP_PATTERN = "%no aparece en su perfil%"


@router.get("/stats/detailed", response_model=DetailedStatsResponse)
def get_detailed_stats(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> DetailedStatsResponse:
    candidate = _get_candidate(db, user)

    visits_total = db.scalar(
        select(func.count())
        .select_from(ReferralVisit)
        .where(ReferralVisit.candidate_id == candidate.id)
    ) or 0
    visits_valid = db.scalar(
        select(func.count())
        .select_from(ReferralVisit)
        .where(ReferralVisit.candidate_id == candidate.id, ReferralVisit.is_valid.is_(True))
    ) or 0

    conversations = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.candidate_id == candidate.id)
    ) or 0
    conversion_rate = (conversations / visits_valid) if visits_valid else 0.0

    knowledge_gaps = db.scalar(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.candidate_id == candidate.id,
            Message.role == "assistant",
            Message.content.ilike(_KNOWLEDGE_GAP_PATTERN),
        )
    ) or 0

    # Escaneo en Python sobre todas las búsquedas del sistema -- MVP a
    # propósito (dataset chico, sin índice JSONB dedicado todavía). Si el
    # volumen de búsquedas de reclutador crece, esto necesita moverse a
    # una consulta JSONB (@>) o a una tabla de attribution dedicada.
    all_searches = db.scalars(select(Search.results)).all()
    recruiter_search_appearances = sum(
        1
        for results in all_searches
        if results and any(r.get("slug") == candidate.slug for r in results)
    )

    share_rows = db.execute(
        select(Share.channel, func.count())
        .where(Share.candidate_id == candidate.id)
        .group_by(Share.channel)
    ).all()
    visit_rows = db.execute(
        select(Share.channel, ReferralVisit.is_valid, func.count())
        .select_from(ReferralVisit)
        .join(Share, ReferralVisit.share_id == Share.id)
        .where(Share.candidate_id == candidate.id)
        .group_by(Share.channel, ReferralVisit.is_valid)
    ).all()

    visits_by_channel: dict[str, int] = defaultdict(int)
    valid_visits_by_channel: dict[str, int] = defaultdict(int)
    for channel, is_valid, count in visit_rows:
        visits_by_channel[channel] += count
        if is_valid:
            valid_visits_by_channel[channel] += count

    channels = [
        ChannelBreakdown(
            channel=channel,
            shares=share_count,
            visits=visits_by_channel.get(channel, 0),
            valid_visits=valid_visits_by_channel.get(channel, 0),
        )
        for channel, share_count in share_rows
    ]

    # Dedup exacto por texto -- no es clustering semántico (dos frases
    # distintas que preguntan lo mismo cuentan separado). Aproximación
    # honesta para MVP, no un motor de NLP.
    frequent_rows = db.execute(
        select(Message.content, func.count().label("cnt"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.candidate_id == candidate.id, Message.role == "user")
        .group_by(Message.content)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    frequent_questions = [
        FrequentQuestion(question=content, count=count) for content, count in frequent_rows
    ]

    return DetailedStatsResponse(
        visits_total=visits_total,
        visits_valid=visits_valid,
        conversion_rate=conversion_rate,
        knowledge_gaps=knowledge_gaps,
        recruiter_search_appearances=recruiter_search_appearances,
        channels=channels,
        frequent_questions=frequent_questions,
    )
