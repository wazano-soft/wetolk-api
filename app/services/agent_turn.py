import time
import uuid
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Candidate, Conversation, CVDocument, Message, Profile
from app.services.agent_prompt import AGENT_SYSTEM_PROMPT, build_cv_context


def get_public_candidate(db: Session, slug: str) -> Candidate:
    """Candidato con perfil público activo, o 404. Compartido por todos
    los endpoints de /api/a/{slug} -- antes duplicado en tres lugares
    (get_public_profile, register_visit, y acá mismo)."""
    candidate = db.scalar(
        select(Candidate).where(Candidate.slug == slug, Candidate.is_public.is_(True))
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Not found")
    return candidate

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
    conversation_pk: int  # id bigint interno -- solo para la FK de Message
    conversation_token: uuid.UUID  # lo que se expone/recibe del cliente


def prepare_turn(
    slug: str,
    client_ip: str,
    message: str,
    conversation_token_raw: str | None,
    visitor_locale: str | None = None,
) -> TurnContext:
    """Resuelve el candidato, arma el system prompt con el CV completo en
    contexto (atajo de MVP, §5) y persiste el mensaje del usuario. Común a
    cualquier contrato de chat que expongamos (custom SSE, Open Responses)."""
    check_rate_limit(client_ip, slug)

    with SessionLocal() as db:
        candidate = get_public_candidate(db, slug)

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
        # El agente responde en el idioma de quien pregunta, no en el que
        # el candidato configuró para sí mismo -- ese campo queda como
        # fallback para contratos que no mandan locale (ej. Open Responses
        # en agent_responses.py) o si el visitante manda algo inválido.
        agent_language = visitor_locale if visitor_locale in ("es", "en") else candidate.agent_language

        conversation_token: uuid.UUID | None = None
        if conversation_token_raw:
            try:
                conversation_token = uuid.UUID(conversation_token_raw)
            except ValueError:
                conversation_token = None

        # El token lo manda el cliente sin autenticar -- si no filtramos
        # también por candidate_id, alguien podría pasar el token de una
        # conversación de OTRO candidato (visto en una respuesta previa, o
        # adivinado) y colarle mensajes a ese hilo ajeno mientras el sistema
        # le contesta con el CV de este candidato.
        conversation = (
            db.scalar(
                select(Conversation).where(
                    Conversation.token == conversation_token,
                    Conversation.candidate_id == candidate.id,
                )
            )
            if conversation_token
            else None
        )
        if conversation is None:
            conversation = Conversation(candidate_id=candidate.id)
            db.add(conversation)
            db.flush()

        db.add(Message(conversation_id=conversation.id, role="user", content=message))
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation_pk = conversation.id
        conversation_token = conversation.token
        db.commit()

    system_prompt = AGENT_SYSTEM_PROMPT.format(
        full_name=full_name,
        first_name=first_name,
        cv_context=cv_context,
        language="español" if agent_language == "es" else "English",
    )
    return TurnContext(
        system_prompt=system_prompt,
        conversation_pk=conversation_pk,
        conversation_token=conversation_token,
    )


def save_assistant_message(conversation_pk: int, content: str) -> None:
    with SessionLocal() as db:
        db.add(Message(conversation_id=conversation_pk, role="assistant", content=content))
        db.commit()
