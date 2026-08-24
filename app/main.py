import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    account,
    agent,
    agent_responses,
    contact_requests,
    cv,
    donate,
    profile,
    push,
    questions,
    recruiter_profile,
    search,
    share,
    stats,
)
from app.core.config import settings
from app.core.db import engine
from app.core.tasks import task_app

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Worker de Procrastinate embebido en el mismo proceso -- a esta escala
    # no justifica un deploy aparte. Si el volumen de CVs lo pide más
    # adelante, esto se reemplaza por `procrastinate worker` como servicio
    # propio sin tocar las tasks (viven en app/api/cv.py, ya persistidas en
    # Postgres, sobreviven al reinicio de este proceso).
    await task_app.open_async()
    worker_task = asyncio.create_task(task_app.run_worker_async(concurrency=1))
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await task_app.close_async()
    engine.dispose()


app = FastAPI(title="Wetölk API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cv.router, prefix="/api/cv", tags=["cv"])
app.include_router(agent.router, prefix="/api/a", tags=["agent"])
app.include_router(agent_responses.router, prefix="/api/a", tags=["agent-responses"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(questions.router, prefix="/api/questions", tags=["questions"])
app.include_router(share.router, prefix="/api", tags=["share"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(account.router, prefix="/api/account", tags=["account"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(
    recruiter_profile.router, prefix="/api/recruiter/profile", tags=["recruiter"]
)
app.include_router(donate.router, prefix="/api/donate", tags=["donate"])
app.include_router(
    contact_requests.router, prefix="/api/contact-requests", tags=["contact-requests"]
)
app.include_router(push.router, prefix="/api/push", tags=["push"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# A2A Agent Card (RFC 8615 well-known) -- una sola card describiendo la
# plataforma, no una por candidato (ver decisión: la convención well-known
# asume un agente por origen). Cada candidato es una "skill" invocable vía
# su propio /api/a/{slug}/chat o /api/a/{slug}/responses, no un agente A2A
# separado todavía -- eso queda para cuando haya un caso de uso real que lo
# necesite (ej. un reclutador-agente hablando directo con el de un candidato).
@app.get("/.well-known/agent-card.json")
def agent_card() -> dict:
    return {
        "protocolVersion": "0.3.0",
        "name": "Wetölk",
        "description": (
            "Convierte el CV de un candidato en un agente conversacional "
            "con URL propia. Cada candidato tiene un agente público que "
            "responde preguntas sobre su trayectoria profesional."
        ),
        "url": settings.public_api_url,
        "version": "0.1.0",
        "preferredTransport": "HTTP+JSON",
        "provider": {"organization": "Wetölk", "url": settings.frontend_url},
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
            "extensions": [],
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "candidate-agent-chat",
                "name": "Chat con el agente de un candidato",
                "description": (
                    "Responde preguntas sobre la trayectoria profesional de "
                    "un candidato específico, en tercera persona, basado "
                    "únicamente en su CV. Requiere el slug público del "
                    "candidato."
                ),
                "tags": ["cv", "recruiting", "chat"],
                "examples": ["¿Qué experiencia tiene con Kubernetes?"],
                "inputModes": ["application/json"],
                "outputModes": ["text/event-stream", "application/json"],
            }
        ],
        "supportsAuthenticatedExtendedCard": False,
    }
