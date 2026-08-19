import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Candidate, CandidateTier, CVDocument, Profile
from app.services import r2
from app.services.cv_extraction import extract_cv
from app.services.pdf import UnextractableTextError, extract_text

router = APIRouter()


def _get_candidate(db: Session, user: AuthUser) -> Candidate:
    candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    if candidate is not None:
        return candidate

    # Provisioning perezoso. El trigger de Postgres (RF-01) solo puede
    # correr cuando auth.users vive en la misma instancia que
    # public.candidates. Con Auth en Supabase y datos en un Postgres
    # distinto (local en dev, u otro proyecto Supabase), eso no siempre
    # se cumple — FastAPI se hace cargo acá la primera vez que hace
    # falta, sin pisar nada si el trigger ya lo creó.
    full_name = (user.email or "user").split("@", 1)[0]
    slug = f"{re.sub(r'[^a-zA-Z0-9]+', '-', full_name).lower()}-{uuid.uuid4().hex[:4]}"

    if db.get(Profile, user.id) is None:
        db.add(Profile(id=user.id, full_name=full_name))
        db.flush()  # profiles antes que candidates: sin relationship()
        # declarada entre las dos, SQLAlchemy no infiere el orden de
        # inserción solo del ForeignKey crudo -- lo forzamos a mano.

    candidate = Candidate(user_id=user.id, slug=slug)
    db.add(candidate)
    db.flush()  # necesitamos candidate.id antes del insert de abajo

    db.add(CandidateTier(candidate_id=candidate.id))
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

    pdf_bytes = r2.download_object(body.r2_key)
    if len(pdf_bytes) > r2.MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 5MB")

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
        raise HTTPException(
            status_code=422,
            detail="El PDF no tiene texto extraíble. Completá el formulario manual.",
        )

    extract = extract_cv(text)

    document.status = "parsed"
    document.extracted = extract.model_dump(mode="json")

    candidate.headline = extract.headline
    candidate.degree = extract.degree
    candidate.overview = extract.overview
    candidate.skills = extract.skills
    candidate.interests = extract.interests
    candidate.status = "ready"

    return ProcessResponse(document_id=str(document.id), status="ready")


class StatusResponse(BaseModel):
    status: str


@router.get("/status", response_model=StatusResponse)
def get_status(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> StatusResponse:
    candidate = _get_candidate(db, user)
    return StatusResponse(status=candidate.status)
