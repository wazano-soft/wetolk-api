import time
import uuid
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Candidate, Conversation, CVDocument, Message, Profile
from app.services.agent_prompt import AGENT_SYSTEM_PROMPT, build_cv_context

# RF-06: 20 mensajes por IP por hora por perfil. En memoria alcanza para el
# MVP (una sola instancia de Railway) -- si se escala a 2+ instancias hay
# que pasar esto a algo compartido (Redis). Compartido entre el endpoint de
# chat original y el de Open Responses: es el mismo agente público, el
# límite tiene que aplicar sin importar por qué contrato entrás.
RATE_LIMIT_PER_HOUR = 20
_rate_limit_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def check_rate_limit(ip: str, slug: str) -> None:
    now = time.time()
    key = (ip, slug)
    window_start = now - 3600
    hits = [t for t in _rate_limit_hits[key] if t > window_start]
    if len(hits) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Demasiados mensajes. Probá de nuevo más tarde.")
    hits.append(now)
    _rate_limit_hits[key] = hits


@dataclass
class TurnContext:
    system_prompt: str
    conversation_id: uuid.UUID


def prepare_turn(
    slug: str, client_ip: str, message: str, conversation_id_raw: str | None
) -> TurnContext:
    """Resuelve el candidato, arma el system prompt con el CV completo en
    contexto (atajo de MVP, §5) y persiste el mensaje del usuario. Común a
    cualquier contrato de chat que expongamos (custom SSE, Open Responses)."""
    check_rate_limit(client_ip, slug)

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
        if conversation_id_raw:
            try:
                conversation_id = uuid.UUID(conversation_id_raw)
            except ValueError:
                conversation_id = None

        conversation = db.get(Conversation, conversation_id) if conversation_id else None
        if conversation is None:
            conversation = Conversation(candidate_id=candidate.id)
            db.add(conversation)
            db.flush()

        db.add(Message(conversation_id=conversation.id, role="user", content=message))
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation_id = conversation.id
        db.commit()

    system_prompt = AGENT_SYSTEM_PROMPT.format(
        full_name=full_name,
        first_name=first_name,
        cv_context=cv_context,
        language="español" if agent_language == "es" else "English",
    )
    return TurnContext(system_prompt=system_prompt, conversation_id=conversation_id)


def save_assistant_message(conversation_id: uuid.UUID, content: str) -> None:
    with SessionLocal() as db:
        db.add(Message(conversation_id=conversation_id, role="assistant", content=content))
        db.commit()
