import json
import time
import uuid
from collections import defaultdict
from collections.abc import Generator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Candidate, Conversation, CVDocument, Message, Profile
from app.services.agent_prompt import (
    AGENT_SYSTEM_PROMPT,
    build_cv_context,
    extract_text_from_content,
)
from app.services.llm import get_chat_model

router = APIRouter()

# RF-06: 20 mensajes por IP por hora por perfil. En memoria alcanza para el
# MVP (una sola instancia de Railway) -- si se escala a 2+ instancias hay
# que pasar esto a algo compartido (Redis).
RATE_LIMIT_PER_HOUR = 20
_rate_limit_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def _check_rate_limit(ip: str, slug: str) -> None:
    now = time.time()
    key = (ip, slug)
    window_start = now - 3600
    hits = [t for t in _rate_limit_hits[key] if t > window_start]
    if len(hits) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Demasiados mensajes. Probá de nuevo más tarde.")
    hits.append(now)
    _rate_limit_hits[key] = hits


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
        candidate = db.scalar(
            select(Candidate).where(Candidate.slug == slug, Candidate.is_public.is_(True))
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Not found")
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
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip, slug)

    with SessionLocal() as db:
        candidate = db.scalar(
            select(Candidate).where(Candidate.slug == slug, Candidate.is_public.is_(True))
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Not found")

        profile = db.get(Profile, candidate.user_id)
        full_name = (profile.full_name if profile else None) or candidate.slug
        first_name = full_name.split(" ")[0]

        document = db.scalar(
            select(CVDocument).where(
                CVDocument.candidate_id == candidate.id, CVDocument.is_current.is_(True)
            )
        )
        if document is None or not document.extracted:
            raise HTTPException(status_code=409, detail="El perfil todavía no está listo")

        cv_context = build_cv_context(document.extracted)
        agent_language = candidate.agent_language

        conversation_id: uuid.UUID | None = None
        if body.conversation_id:
            try:
                conversation_id = uuid.UUID(body.conversation_id)
            except ValueError:
                conversation_id = None

        conversation = db.get(Conversation, conversation_id) if conversation_id else None
        if conversation is None:
            conversation = Conversation(candidate_id=candidate.id)
            db.add(conversation)
            db.flush()

        db.add(Message(conversation_id=conversation.id, role="user", content=body.message))
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation_id = conversation.id
        db.commit()

    system_prompt = AGENT_SYSTEM_PROMPT.format(
        full_name=full_name,
        first_name=first_name,
        cv_context=cv_context,
        language="español" if agent_language == "es" else "English",
    )

    def event_stream() -> Generator[str, None, None]:
        model = get_chat_model(temperature=0.3)
        full_response = ""
        for chunk in model.stream([("system", system_prompt), ("human", body.message)]):
            token = extract_text_from_content(chunk.content)
            if token:
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        with SessionLocal() as db:
            db.add(
                Message(conversation_id=conversation_id, role="assistant", content=full_response)
            )
            db.commit()

        yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(conversation_id), 'sources': []})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
