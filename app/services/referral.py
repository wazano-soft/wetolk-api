import hashlib
import secrets
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import CandidateTier

# RF-08 §8: umbrales de "Aporta o Comparte"
IMPULSO_SHARE_THRESHOLD = 3
ALCANCE_VISIT_THRESHOLD = 27

# Nunca se revoca un nivel ya alcanzado (regla explícita del doc de marca:
# quitarle algo a alguien desempleado por no ser "lo bastante viral" es
# justo el tipo de cosa que hunde una marca). advance_tier() solo sube.
_TIER_ORDER = {"base": 0, "impulso": 1, "alcance": 2}

BOT_MARKERS = (
    "bot", "crawler", "spider", "preview", "curl",
    "python-requests", "facebookexternalhit", "linkedinbot",
)


def get_or_create_tier(db: Session, candidate_id: int) -> CandidateTier:
    tier = db.get(CandidateTier, candidate_id)
    if tier is not None:
        return tier
    try:
        tier = CandidateTier(candidate_id=candidate_id)
        db.add(tier)
        db.flush()
        return tier
    except IntegrityError:
        # otra request concurrente (share + visit casi simultáneos, por
        # ejemplo) ya la creó primero -- usamos la que ganó la carrera en
        # vez de dejar que el IntegrityError tumbe el request con un 500.
        db.rollback()
        tier = db.get(CandidateTier, candidate_id)
        if tier is None:
            raise
        return tier


def advance_tier(tier: CandidateTier, new_tier: str, unlocked_by: str) -> None:
    if _TIER_ORDER[new_tier] > _TIER_ORDER[tier.tier]:
        tier.tier = new_tier
        tier.unlocked_by = unlocked_by
        tier.unlocked_at = datetime.now(timezone.utc)


def visitor_hash(ip: str, user_agent: str) -> str:
    # Sal rotada por día: deduplica dentro del día, imposible seguir a un
    # visitante a lo largo del tiempo. Nunca se guarda la IP en claro.
    raw = f"{ip}|{user_agent}|{settings.visit_salt}|{date.today().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_bot(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(marker in ua for marker in BOT_MARKERS)


def new_ref_token() -> str:
    # token_urlsafe(n) da longitud fija (~1.3*n chars) -- 7 bytes ya dan
    # los 10 caracteres que pide RF-08, sin truncar y tirar entropía.
    return secrets.token_urlsafe(7)


SHARE_TEXTS = {
    ("linkedin", "es"): (
        "Estoy en búsqueda de nuevas oportunidades. Armé un asistente que "
        "responde cualquier duda sobre mi experiencia profesional — "
        "preguntale lo que quieras:"
    ),
    ("whatsapp", "es"): "Te comparto mi CV, pero este contesta preguntas 👇",
    ("x", "es"): "Mi CV ahora responde preguntas. Probalo:",
    ("linkedin", "en"): (
        "I'm exploring new opportunities. I built an assistant that answers "
        "any question about my professional background — ask it anything:"
    ),
    ("whatsapp", "en"): "Here's my CV — this one answers questions 👇",
    ("x", "en"): "My CV answers questions now. Try it:",
}


def share_text(channel: str, language: str) -> str | None:
    return SHARE_TEXTS.get((channel, language)) or SHARE_TEXTS.get((channel, "es"))
