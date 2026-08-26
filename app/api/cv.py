import logging
import secrets
import string
from datetime import datetime

import procrastinate
from app.schemas.cv import CVExtract, Suggestion
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.db import SessionLocal, get_db
from app.core.tasks import task_app
from app.models import Candidate, CandidateTier, CVChunk, CVDocument, Profile, Recruiter
from app.services import r2
from app.services.cv_extraction import extract_cv
from app.services.embeddings import get_embeddings, get_token_count
from app.services.pdf import UnextractableTextError, extract_text

logger = logging.getLogger(__name__)

router = APIRouter()

def _create_cv_chunks(extract: CVExtract, candidate_id: int, document_id: int) -> list[dict]:
    """Divide el CV extraído en chunks por sección para embeddings granulares."""
    chunks = []

    # Chunk de headline + overview
    if extract.headline or extract.overview:
        content = f"{extract.headline or ''}\n{extract.overview or ''}".strip()
        if content:
            chunks.append({
                "section": "overview",
                "title": extract.headline,
                "content": content,
                "metadata": {"type": "profile_summary"}
            })

    # Chunks de experiencias
    for i, exp in enumerate(extract.experiences):
        content_parts = [f"{exp.role} at {exp.company}"]
        if exp.description:
            content_parts.append(exp.description)
        if exp.achievements:
            content_parts.extend(exp.achievements)

        content = "\n".join(content_parts)
        chunks.append({
            "section": "experience",
            "title": f"{exp.role} at {exp.company}",
            "content": content,
            "metadata": {
                "type": "experience",
                "company": exp.company,
                "role": exp.role,
                "index": i
            }
        })

    # Chunks de educación
    for i, edu in enumerate(extract.education):
        content = f"{edu.degree} at {edu.institution}"
        if edu.field:
            content += f" - {edu.field}"
        chunks.append({
            "section": "education",
            "title": edu.degree,
            "content": content,
            "metadata": {
                "type": "education",
                "institution": edu.institution,
                "degree": edu.degree,
                "index": i
            }
        })

    # Chunks de proyectos
    for i, proj in enumerate(extract.projects):
        content = f"{proj.name} ({proj.kind})"
        if proj.description:
            content += f"\n{proj.description}"
        chunks.append({
            "section": "project",
            "title": proj.name,
            "content": content,
            "metadata": {
                "type": "project",
                "name": proj.name,
                "kind": proj.kind,
                "index": i
            }
        })

    # Chunk de skills
    if extract.skills:
        content = "Skills: " + ", ".join(extract.skills)
        chunks.append({
            "section": "skills",
            "title": "Technical Skills",
            "content": content,
            "metadata": {"type": "skills", "count": len(extract.skills)}
        })

    return chunks


@task_app.task(
    name="process_cv_chunks",
    pass_context=True,
    # Rate limits / hiccups transitorios del proveedor de embeddings: 3
    # intentos con backoff exponencial (~10s, ~100s) antes de darse por
    # vencido y marcar chunks_status="failed".
    retry=procrastinate.RetryStrategy(max_attempts=3, exponential_wait=10),
)
def process_cv_chunks(
    context: procrastinate.JobContext, candidate_id: int, document_id: int, extract: dict
) -> None:
    """Job de Procrastinate: arma los chunks del CV, calcula sus embeddings y
    los persiste. Recibe los datos ya resueltos como JSON plano (no objetos
    ORM ni Pydantic) porque el job se guarda en procrastinate_jobs y puede
    ejecutarlo un worker en otro proceso -- nada de eso sobrevive serializar
    a JSON salvo primitivos."""
    extract_obj = CVExtract.model_validate(extract)
    db = SessionLocal()
    try:
        chunks = _create_cv_chunks(extract_obj, candidate_id, document_id)
        embeddings = get_embeddings()
        for chunk in chunks:
            db.add(CVChunk(
                candidate_id=candidate_id,
                document_id=document_id,
                section=chunk["section"],
                title=chunk["title"],
                content=chunk["content"],
                metadata_=chunk["metadata"],
                embedding=embeddings.embed_query(chunk["content"]),
                token_count=get_token_count(chunk["content"]),
            ))
        document = db.get(CVDocument, document_id)
        if document:
            document.chunks_status = "done"
        db.commit()
    except Exception:
        logger.exception("Fallo el chunking de CV para document_id=%s", document_id)
        db.rollback()
        # Solo marcamos chunks_status="failed" si este era el último
        # intento permitido -- si todavía quedan reintentos, dejamos
        # "pending" (Procrastinate va a reencolar el job solo) y
        # re-lanzamos para que el retry se dispare de verdad.
        retry_strategy = context.task.retry_strategy
        max_attempts = retry_strategy.max_attempts if retry_strategy else 0
        is_final_attempt = max_attempts is not None and context.job.attempts >= max_attempts
        if is_final_attempt:
            document = db.get(CVDocument, document_id)
            if document:
                document.chunks_status = "failed"
                db.commit()
        raise
    finally:
        db.close()


_SLUG_ALPHABET = string.ascii_lowercase + string.digits


def _generate_slug() -> str:
    """Identificador público corto y opaco -- sin prefijo de nombre (no
    filtra el nombre del candidato en la URL) y con suficiente espacio
    (36^10) para que una colisión sea prácticamente imposible."""
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(10))


def _get_candidate(db: Session, user: AuthUser) -> Candidate:
    candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    if candidate is not None:
        return candidate

    # Mismo criterio que _get_recruiter (search.py, hallazgo de code-review
    # análogo): una cuenta ya registrada como reclutadora no se puede volver
    # candidata por esta vía silenciosa -- sin este chequeo, cualquier
    # reclutador que entrara a /dashboard quedaba provisionado como
    # candidato de la nada, con un Candidate, slug y perfil público reales.
    existing_recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == user.id))
    if existing_recruiter is not None:
        raise HTTPException(
            status_code=403, detail="This account is already registered as a recruiter"
        )

    # Provisioning perezoso. El trigger de Postgres (RF-01) solo puede
    # correr cuando auth.users vive en la misma instancia que
    # public.candidates. Con Auth en Supabase y datos en un Postgres
    # distinto (local en dev, u otro proyecto Supabase), eso no siempre
    # se cumple — FastAPI se hace cargo acá la primera vez que hace
    # falta, sin pisar nada si el trigger ya lo creó.
    full_name = user.full_name or (user.email or "user").split("@", 1)[0]
    slug = _generate_slug()

    try:
        if db.get(Profile, user.id) is None:
            db.add(Profile(id=user.id, full_name=full_name))
            db.flush()  # profiles antes que candidates: sin relationship()
            # declarada entre las dos, SQLAlchemy no infiere el orden de
            # inserción solo del ForeignKey crudo -- lo forzamos a mano.

        candidate = Candidate(user_id=user.id, slug=slug)
        db.add(candidate)
        db.flush()  # necesitamos candidate.id antes del insert de abajo

        db.add(CandidateTier(candidate_id=candidate.id))
        db.flush()
        return candidate
    except IntegrityError:
        # Dos requests concurrentes de un usuario nuevo (ej. status +
        # upload-url al cargar la página) pueden pisarse acá: las dos ven
        # candidate is None y las dos intentan provisionar. La que pierde
        # la carrera cae acá -- descarta su intento y usa el que ganó.
        db.rollback()
        candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
        if candidate is None:
            raise
        return candidate


class UploadUrlResponse(BaseModel):
    upload_url: str
    r2_key: str


@router.post("/upload-url", response_model=UploadUrlResponse)
def get_upload_url(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> UploadUrlResponse:
    candidate = _get_candidate(db, user)
    key = r2.cv_key(str(candidate.storage_token))
    return UploadUrlResponse(upload_url=r2.create_upload_url(key), r2_key=key)


class ProcessRequest(BaseModel):
    r2_key: str


class ProcessResponse(BaseModel):
    document_id: str
    status: str


@router.post("/process", response_model=ProcessResponse)
def process_cv(
    body: ProcessRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProcessResponse:
    candidate = _get_candidate(db, user)

    # Chequeo por HEAD antes de bajar el body entero -- si alguien subió un
    # archivo grande a través de la URL firmada (que no acota tamaño, ver
    # nota en r2.create_upload_url), no queremos cargarlo completo en
    # memoria solo para rechazarlo después.
    if r2.get_object_size(body.r2_key) > r2.MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 150KB")

    pdf_bytes = r2.download_object(body.r2_key)

    # RF-02: reemplazar CV -> soft delete de la version anterior, se crea
    # una fila nueva en vez de pisar la existente.
    db.query(CVDocument).filter(CVDocument.candidate_id == candidate.id).update(
        {"is_current": False}
    )
    document = CVDocument(
        candidate_id=candidate.id,
        r2_key=body.r2_key,
        filename=body.r2_key.rsplit("/", 1)[-1],
        size_bytes=len(pdf_bytes),
        status="parsing",
        chunks_status="pending",
    )
    db.add(document)
    candidate.status = "processing"
    db.flush()

    try:
        text = extract_text(pdf_bytes)
    except UnextractableTextError:
        document.status = "failed"
        document.error_message = "PDF sin texto extraíble (probable escaneo sin OCR)"
        candidate.status = "error"
        # get_db hace rollback de toda la sesión ante cualquier excepción
        # (app/core/db.py) -- sin este commit acá, el HTTPException de abajo
        # dispara ese rollback y se pierde el estado de fallo que acabamos
        # de setear. GET /api/cv/status quedaría mostrando el status viejo,
        # sin rastro del error.
        db.commit()
        raise HTTPException(
            status_code=422,
            detail="El PDF no tiene texto extraíble. Completá el formulario manual.",
        )

    extract = extract_cv(text)
    if extract.is_risky_prompt:
        # No filtramos esto silenciosamente ni exponemos el motivo exacto
        # en el mensaje -- decirle al usuario "detectamos un intento de
        # prompt injection" solo le da pistas a quien lo esté probando
        # a propósito. El texto igual queda guardado en document.extracted
        # para poder revisarlo manualmente si hace falta.
        document.status = "failed"
        document.extracted = extract.model_dump(mode="json")
        document.error_message = "CV rechazado: el contenido no pudo procesarse."
        candidate.status = "error"
        db.commit()
        raise HTTPException(
            status_code=422,
            detail="No pudimos procesar este CV. Verificá el archivo e intentá de nuevo.",
        )
    if extract.full_name:
        profile = db.get(Profile, candidate.user_id)
        if profile:
            profile.full_name = extract.full_name

    document.status = "parsed"
    document.extracted = extract.model_dump(mode="json")

    candidate.headline = extract.headline
    candidate.degree = extract.degree
    candidate.overview = extract.overview
    candidate.skills = extract.skills
    candidate.interests = extract.interests
    candidate.linkedin_url = extract.linkedin_url
    candidate.github_url = extract.github_url
    candidate.portfolio_url = extract.portfolio_url
    candidate.youtube_url = extract.youtube_url
    candidate.detected_language = extract.detected_language
    candidate.is_risky_prompt = extract.is_risky_prompt
    document.suggestions = [s.model_dump() for s in extract.suggestions]
    candidate.status = "ready"
    # extract.quick_questions NO se persiste acá -- son sugerencias para
    # el wizard justo después del análisis (GET /questions/suggest ya
    # cubre ese caso con su propia llamada). Lo que el usuario confirma
    # se guarda en la tabla quick_questions vía PUT /questions.

    # RF-10: embedding a nivel de perfil (no por chunk, ese ya existe para
    # el chat individual) para que la búsqueda de reclutador pueda rankear
    # por similitud coseno. Resumen sintético de lo más relevante para
    # matchear una vacante, no el CV completo.
    summary_parts = [extract.headline, extract.degree, extract.overview, *extract.skills]
    summary = " ".join(p for p in summary_parts if p)
    if summary:
        embedding = get_embeddings().embed_query(summary)
        token_count = get_token_count(summary)

        from app.models import CandidateEmbedding
        candidate_embedding = CandidateEmbedding(
            candidate_id=candidate.id,
            embedding=embedding,
            summary=summary,
            token_count=token_count,
            metadata_={
                "headline": extract.headline,
                "degree": extract.degree,
                "skills": extract.skills,
            }
        )
        db.add(candidate_embedding)

    # Commit explícito acá (no dejárselo al teardown de get_db): el job de
    # Procrastinate se inserta por una conexión aparte a Postgres y un
    # worker lo puede levantar de inmediato -- necesita ver esta
    # transacción ya confirmada, no alcanza con flush().
    db.commit()
    process_cv_chunks.defer(
        candidate_id=candidate.id, document_id=document.id, extract=extract.model_dump(mode="json")
    )

    return ProcessResponse(document_id=str(document.token), status="ready")


class StatusResponse(BaseModel):
    status: str


@router.get("/status", response_model=StatusResponse)
def get_status(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> StatusResponse:
    candidate = _get_candidate(db, user)
    return StatusResponse(status=candidate.status)


class CVDocumentOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: str
    chunks_status: str
    error_message: str | None
    created_at: datetime
    suggestions: list[Suggestion]


class CVDocumentsResponse(BaseModel):
    documents: list[CVDocumentOut]


@router.get("/documents", response_model=CVDocumentsResponse)
def list_cv_documents(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> CVDocumentsResponse:
    candidate = _get_candidate(db, user)
    # RF-02: por ahora un solo CV vigente por candidato -- is_current=True
    # nunca matchea más de una fila (subir uno nuevo pisa el flag del
    # anterior en process_cv()). Devolvemos lista igual, no un objeto
    # único, para no tener que romper el contrato el día que se permita
    # más de uno.
    docs = db.scalars(
        select(CVDocument)
        .where(CVDocument.candidate_id == candidate.id, CVDocument.is_current.is_(True))
        .order_by(CVDocument.created_at.desc())
    ).all()
    return CVDocumentsResponse(
        documents=[
            CVDocumentOut(
                id=str(d.token),
                filename=d.filename,
                size_bytes=d.size_bytes,
                status=d.status,
                chunks_status=d.chunks_status,
                error_message=d.error_message,
                created_at=d.created_at,
                suggestions=d.suggestions or [],
            )
            for d in docs
        ]
    )
