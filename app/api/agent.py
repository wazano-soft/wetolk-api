import json
from collections.abc import Generator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.core.http import get_client_ip
from app.models import Profile, ReferralVisit, Share
from app.services.agent_prompt import extract_text_from_content
from app.services.agent_turn import get_public_candidate, prepare_turn, save_assistant_message
from app.services.llm import get_chat_model
from app.services.referral import (
    ALCANCE_VISIT_THRESHOLD,
    advance_tier,
    get_or_create_tier,
    is_bot,
    visitor_hash,
)

router = APIRouter()


class PublicProfileResponse(BaseModel):
    slug: str
    full_name: str | None
    headline: str | None
    overview: str | None
    skills: list[str]
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    agent_language: str


@router.get("/{slug}", response_model=PublicProfileResponse)
def get_public_profile(slug: str) -> PublicProfileResponse:
    with SessionLocal() as db:
        candidate = get_public_candidate(db, slug)
        profile = db.get(Profile, candidate.user_id)
        return PublicProfileResponse(
            slug=candidate.slug,
            full_name=profile.full_name if profile else None,
            headline=candidate.headline,
            overview=candidate.overview,
            skills=candidate.skills,
            linkedin_url=candidate.linkedin_url,
            github_url=candidate.github_url,
            portfolio_url=candidate.portfolio_url,
            agent_language=candidate.agent_language,
        )


class ChatRequest(BaseModel):
    message: str = Field(max_length=500)
    conversation_id: str | None = None


@router.post("/{slug}/chat")
def chat(slug: str, body: ChatRequest, request: Request) -> StreamingResponse:
    client_ip = get_client_ip(request)
    ctx = prepare_turn(slug, client_ip, body.message, body.conversation_id)

    def event_stream() -> Generator[str, None, None]:
        model = get_chat_model(temperature=0.3)
        full_response = ""
        for chunk in model.stream([("system", ctx.system_prompt), ("human", body.message)]):
            token = extract_text_from_content(chunk.content)
            if token:
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        save_assistant_message(ctx.conversation_pk, full_response)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(ctx.conversation_token), 'sources': []})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class VisitRequest(BaseModel):
    ref: str
    dwell_ms: int


class VisitResponse(BaseModel):
    registered: bool
    valid: bool = False


@router.post("/{slug}/visit", response_model=VisitResponse)
def register_visit(slug: str, body: VisitRequest, request: Request) -> VisitResponse:
    with SessionLocal() as db:
        candidate = get_public_candidate(db, slug)

        share = db.scalar(
            select(Share).where(Share.ref_token == body.ref, Share.candidate_id == candidate.id)
        )
        if share is None:
            raise HTTPException(status_code=404, detail="Invalid ref token")

        ip = get_client_ip(request)
        ua = request.headers.get("user-agent", "")
        vh = visitor_hash(ip, ua)

        # RF-08: válida a partir de 10s de permanencia real, filtrando bots.
        # El chequeo de auto-referido (visitor_hash == hash del dueño) que
        # menciona el doc técnico §8 queda pendiente -- no tenemos forma de
        # conocer el hash del dueño sin pedirle que visite su propio link
        # una vez para registrarlo, y el doc tampoco lo especifica.
        valid = body.dwell_ms >= 10_000 and not is_bot(ua)

        try:
            db.add(
                ReferralVisit(
                    share_id=share.id,
                    candidate_id=candidate.id,
                    visitor_hash=vh,
                    is_valid=valid,
                    dwell_ms=body.dwell_ms,
                )
            )
            db.flush()
        except IntegrityError:
            # ya existe una visita VÁLIDA de este visitante hoy para este
            # candidato (el índice referral_visits_daily_unique es parcial,
            # solo cubre is_valid=true) -- no es un error, es el caso
            # esperado de deduplicación.
            db.rollback()
            return VisitResponse(registered=False)

        if valid:
            tier = get_or_create_tier(db, candidate.id)
            tier.referral_count += 1
            if tier.referral_count >= ALCANCE_VISIT_THRESHOLD:
                advance_tier(tier, "alcance", "referrals")

        db.commit()
        return VisitResponse(registered=True, valid=valid)
