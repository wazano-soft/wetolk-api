import json
from collections.abc import Generator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Candidate, Profile
from app.services.agent_turn import prepare_turn, save_assistant_message
from app.services.agent_prompt import extract_text_from_content
from app.services.llm import get_chat_model

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
    ctx = prepare_turn(slug, client_ip, body.message, body.conversation_id)

    def event_stream() -> Generator[str, None, None]:
        model = get_chat_model(temperature=0.3)
        full_response = ""
        for chunk in model.stream([("system", ctx.system_prompt), ("human", body.message)]):
            token = extract_text_from_content(chunk.content)
            if token:
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        save_assistant_message(ctx.conversation_id, full_response)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(ctx.conversation_id), 'sources': []})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
