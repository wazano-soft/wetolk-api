import hashlib
import secrets
from datetime import date

from app.core.config import settings

# RF-08 §8: umbrales de "Aporta o Comparte"
IMPULSO_SHARE_THRESHOLD = 3
ALCANCE_VISIT_THRESHOLD = 27

BOT_MARKERS = (
    "bot", "crawler", "spider", "preview", "curl",
    "python-requests", "facebookexternalhit", "linkedinbot",
)


def visitor_hash(ip: str, user_agent: str) -> str:
    # Sal rotada por día: deduplica dentro del día, imposible seguir a un
    # visitante a lo largo del tiempo. Nunca se guarda la IP en claro.
    raw = f"{ip}|{user_agent}|{settings.visit_salt}|{date.today().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_bot(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(marker in ua for marker in BOT_MARKERS)


def new_ref_token() -> str:
    return secrets.token_urlsafe(8)[:10]


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
