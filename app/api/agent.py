import json
import re
import unicodedata
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.search import _get_recruiter
from app.core.auth import AuthUser, get_current_user
from app.core.db import SessionLocal, get_db
from app.core.http import get_client_ip
from app.models import ContactRequest, CVDocument, Profile, QuickQuestion, ReferralVisit, Share
from app.services.agent_prompt import extract_text_from_content
from app.services.agent_turn import get_public_candidate, prepare_turn, save_assistant_message
from app.services.llm import get_chat_model
from app.services.cache import cached
from app.services import pdf, push, r2
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
    years_experience: float | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    youtube_url: str | None
    agent_language: str
    work_mode: str | None
    location_city: str | None
    location_country: str | None
    quick_questions: list[str]
    tier: str
    experiences: list[dict]
    education: list[dict]
    projects: list[dict]


# `end_date`/`start_date` son texto libre salido del LLM (puede ser null,
# "Present", "Actual", "2020", "2020-01", "Jan 2020", etc.) -- no hay forma
# de parsearlos de forma confiable, así que esto es un ORDEN aproximado
# best-effort, no una fecha real. "Ongoing" (sin end_date, o end_date tipo
# "presente"/"actual"/"current") ordena primero por ser lo más reciente.
_ONGOING_RE = re.compile(r"presente|actual|current|present", re.IGNORECASE)
_YEAR_RE = re.compile(r"(\d{4})")
_MONTH_NUM_RE = re.compile(r"(?:^|-)(\d{1,2})(?:-|$)")
_MONTH_NAMES = {
    "ene": 1, "enero": 1, "jan": 1, "january": 1,
    "feb": 2, "febrero": 2, "february": 2,
    "mar": 3, "marzo": 3, "march": 3,
    "abr": 4, "abril": 4, "apr": 4, "april": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6, "june": 6,
    "jul": 7, "julio": 7, "july": 7,
    "ago": 8, "agosto": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "september": 9,
    "oct": 10, "octubre": 10, "october": 10,
    "nov": 11, "noviembre": 11, "november": 11,
    "dic": 12, "diciembre": 12, "dec": 12, "december": 12,
}


def _date_sort_key(entry: dict, date_field: str) -> tuple[int, int, int]:
    """Clave de orden descendente (más reciente primero) para un dict con
    fechas de texto libre. (is_ongoing, year, month) -- ongoing gana
    siempre, después año, después mes si se puede extraer barato."""
    value = entry.get(date_field)
    if not value or _ONGOING_RE.search(str(value)):
        return (1, 9999, 12)

    text = str(value).lower()
    year_match = _YEAR_RE.search(text)
    year = int(year_match.group(1)) if year_match else 0

    month = 0
    for name, num in _MONTH_NAMES.items():
        if name in text:
            month = num
            break
    if month == 0:
        month_match = _MONTH_NUM_RE.search(text)
        if month_match:
            candidate_month = int(month_match.group(1))
            if 1 <= candidate_month <= 12:
                month = candidate_month

    return (0, year, month)


def _sort_by_recency(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda e: _date_sort_key(e, "end_date"),
        reverse=True,
    )


@router.get("/{slug}", response_model=PublicProfileResponse)
def get_public_profile(slug: str) -> PublicProfileResponse:
    # Cache de 60s: el endpoint más pegado bajo tráfico viral (ver RF-08).
    # Una 404 no queda cacheada -- cached() solo guarda si compute() no
    # lanza, así que un slug inválido sigue pegándole a la DB en cada hit
    # (aceptable, no es el caso que este cache busca resolver).
    return cached(f"public_profile:{slug}", lambda: _build_public_profile(slug))


@router.get("/{slug}/cv")
def download_public_cv(slug: str) -> Response:
    # Decisión de producto (2026-08-23): el CV en PDF pasa a ser
    # descargable desde el perfil público -- ver botón de descarga en
    # ProfileView.tsx. Antes de esto el PDF nunca se servía públicamente
    # (ver texto viejo de privacy.sections.pdf, ya actualizado). Mismo
    # gate que el resto del perfil público: get_public_candidate 404ea si
    # el candidato no es público, así que un CV de un perfil no público
    # tampoco queda expuesto acá.
    #
    # Se proxea el contenido en vez de redirigir a una URL firmada de R2
    # -- así el navegador nunca ve la key del bucket ni una URL firmada
    # copiable/compartible por fuera de esta página. El CV está acotado a
    # 150KB (r2.MAX_PDF_SIZE_BYTES), así que traerlo entero a memoria acá
    # es aceptable, no justifica streaming por chunks.
    with SessionLocal() as db:
        candidate = get_public_candidate(db, slug)
        document = db.scalar(
            select(CVDocument).where(
                CVDocument.candidate_id == candidate.id, CVDocument.is_current.is_(True)
            )
        )
        if document is None:
            raise HTTPException(status_code=404, detail="No CV available")
        profile = db.get(Profile, candidate.user_id)
        display_name = (profile.full_name if profile else None) or candidate.slug
        filename = _cv_download_filename(display_name)
        raw_pdf = r2.download_object(document.r2_key)
        # RF-08: alcanzar "impulso" (3 shares o una donación, nunca se
        # revoca -- ver referral.py) quita la marca de agua del PDF para
        # siempre. Es la primera feature real gateada por tier, no solo
        # informativa como el resto del sistema.
        tier = get_or_create_tier(db, candidate.id)
        db.commit()
        content = raw_pdf if tier.tier != "base" else pdf.add_watermark(raw_pdf)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def _cv_download_filename(display_name: str) -> str:
    # NFKD + encode ascii "ignore": sin esto, "José" quedaba como "jos"
    # (la é se descartaba entera en vez de transliterarse) -- acá sí
    # importa, es un nombre de archivo que la persona ve, no una URL.
    ascii_name = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii")
    slug_name = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower() or "candidato"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"wetolk-{slug_name}-{ts}.pdf"


def _build_public_profile(slug: str) -> PublicProfileResponse:
    with SessionLocal() as db:
        candidate = get_public_candidate(db, slug)
        profile = db.get(Profile, candidate.user_id)
        quick_questions = db.scalars(
            select(QuickQuestion.question)
            .where(QuickQuestion.candidate_id == candidate.id)
            .order_by(QuickQuestion.position)
        ).all()
        document = db.scalar(
            select(CVDocument).where(
                CVDocument.candidate_id == candidate.id, CVDocument.is_current.is_(True)
            )
        )
        extracted = (document.extracted if document else None) or {}
        experiences = _sort_by_recency(extracted.get("experiences") or [])
        education = _sort_by_recency(extracted.get("education") or [])
        projects = extracted.get("projects") or []
        # get_or_create_tier puede insertar una fila nueva -- SessionLocal()
        # a secas no auto-commitea como sí lo hace la dependencia get_db(),
        # así que sin este commit el insert se pierde en el rollback
        # implícito al cerrar la sesión.
        tier = get_or_create_tier(db, candidate.id)
        tier_value = tier.tier
        db.commit()
        return PublicProfileResponse(
            slug=candidate.slug,
            full_name=profile.full_name if profile else None,
            headline=candidate.headline,
            overview=candidate.overview,
            skills=candidate.skills,
            years_experience=candidate.years_experience,
            linkedin_url=candidate.linkedin_url,
            github_url=candidate.github_url,
            portfolio_url=candidate.portfolio_url,
            youtube_url=candidate.youtube_url,
            agent_language=candidate.agent_language,
            work_mode=candidate.work_mode,
            location_city=candidate.location_city,
            location_country=candidate.location_country,
            quick_questions=list(quick_questions),
            tier=tier_value,
            experiences=experiences,
            education=education,
            projects=projects,
        )


class ChatRequest(BaseModel):
    message: str = Field(max_length=500)
    conversation_id: str | None = None
    locale: str | None = None


@router.post("/{slug}/chat")
def chat(slug: str, body: ChatRequest, request: Request) -> StreamingResponse:
    client_ip = get_client_ip(request)
    ctx = prepare_turn(slug, client_ip, body.message, body.conversation_id, body.locale)

    def event_stream() -> Generator[str, None, None]:
        model = get_chat_model(temperature=0.2)
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


class ContactRequestIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ContactResponse(BaseModel):
    status: str


@router.post("/{slug}/contact", response_model=ContactResponse, status_code=201)
def contact_candidate(
    slug: str,
    body: ContactRequestIn,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactResponse:
    recruiter = _get_recruiter(db, user)
    candidate = get_public_candidate(db, slug)

    # Upsert manual en vez de confiar en la unique constraint (recruiter_id,
    # candidate_id): un mismo reclutador puede volver a escribirle al mismo
    # candidato -- eso actualiza el mensaje y reabre el request a "pending"
    # en vez de fallar con un IntegrityError.
    existing = db.scalar(
        select(ContactRequest).where(
            ContactRequest.recruiter_id == recruiter.id,
            ContactRequest.candidate_id == candidate.id,
        )
    )
    if existing is not None:
        existing.message = body.message
        existing.recruiter_email = user.email
        existing.status = "pending"
        existing.created_at = datetime.now(timezone.utc)
        db.commit()
    else:
        db.add(
            ContactRequest(
                recruiter_id=recruiter.id,
                candidate_id=candidate.id,
                message=body.message,
                recruiter_email=user.email,
                status="pending",
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Dos requests concurrentes del mismo reclutador al mismo
            # candidato (doble click, retry de red) pueden pisarse acá --
            # la que pierde la carrera cae en la unique constraint
            # (recruiter_id, candidate_id). Mismo criterio que
            # _get_candidate (cv.py): se descarta el insert propio y se
            # actualiza la fila que ya ganó, en vez de un 500 crudo.
            db.rollback()
            existing = db.scalar(
                select(ContactRequest).where(
                    ContactRequest.recruiter_id == recruiter.id,
                    ContactRequest.candidate_id == candidate.id,
                )
            )
            if existing is None:
                raise
            existing.message = body.message
            existing.recruiter_email = user.email
            existing.status = "pending"
            existing.created_at = datetime.now(timezone.utc)
            db.commit()

    push.send_push(
        db,
        candidate.user_id,
        {"title": "Nuevo mensaje de un reclutador", "body": body.message[:120], "url": "/dashboard/messages"},
    )

    return ContactResponse(status="sent")
