import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import AuthUser, get_current_user
from app.core.db import pool
from app.services import r2
from app.services.cv_extraction import extract_cv
from app.services.pdf import UnextractableTextError, extract_text

router = APIRouter()


def _get_candidate(user: AuthUser) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            "select id, storage_token from public.candidates where user_id = %s",
            (user.id,),
        ).fetchone()
        if row is not None:
            return {"id": row[0], "storage_token": row[1]}

        # Provisioning perezoso. El trigger de Postgres (RF-01) solo puede
        # correr cuando auth.users vive en la misma instancia que
        # public.candidates. Con Auth en Supabase y datos en un Postgres
        # distinto (local en dev, u otro proyecto Supabase), eso no siempre
        # se cumple — FastAPI se hace cargo acá la primera vez que hace
        # falta, sin pisar nada si el trigger ya lo creó.
        full_name = (user.email or "user").split("@", 1)[0]
        slug = f"{re.sub(r'[^a-zA-Z0-9]+', '-', full_name).lower()}-{uuid.uuid4().hex[:4]}"

        conn.execute(
            "insert into public.profiles (id, full_name) values (%s, %s) on conflict (id) do nothing",
            (user.id, full_name),
        )
        row = conn.execute(
            "insert into public.candidates (user_id, slug) values (%s, %s) returning id, storage_token",
            (user.id, slug),
        ).fetchone()
        conn.execute(
            "insert into public.candidate_tiers (candidate_id) values (%s)",
            (row[0],),
        )
        return {"id": row[0], "storage_token": row[1]}


class UploadUrlResponse(BaseModel):
    upload_url: str
    r2_key: str


@router.post("/upload-url", response_model=UploadUrlResponse)
def get_upload_url(user: AuthUser = Depends(get_current_user)) -> UploadUrlResponse:
    candidate = _get_candidate(user)
    key = r2.cv_key(str(candidate["storage_token"]))
    return UploadUrlResponse(upload_url=r2.create_upload_url(key), r2_key=key)


class ProcessRequest(BaseModel):
    r2_key: str


class ProcessResponse(BaseModel):
    document_id: str
    status: str


@router.post("/process", response_model=ProcessResponse)
def process_cv(
    body: ProcessRequest, user: AuthUser = Depends(get_current_user)
) -> ProcessResponse:
    candidate = _get_candidate(user)
    candidate_id = candidate["id"]

    pdf_bytes = r2.download_object(body.r2_key)
    if len(pdf_bytes) > r2.MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 5MB")

    # RF-02: reemplazar CV -> soft delete de la version anterior, se crea
    # una fila nueva en vez de pisar la existente.
    with pool.connection() as conn:
        conn.execute(
            "update public.cv_documents set is_current = false where candidate_id = %s",
            (candidate_id,),
        )
        row = conn.execute(
            """
            insert into public.cv_documents (candidate_id, r2_key, filename, size_bytes, status)
            values (%s, %s, %s, %s, 'parsing')
            returning id
            """,
            (candidate_id, body.r2_key, body.r2_key.rsplit("/", 1)[-1], len(pdf_bytes)),
        ).fetchone()
        document_id = row[0]
        conn.execute(
            "update public.candidates set status = 'processing' where id = %s",
            (candidate_id,),
        )

    try:
        text = extract_text(pdf_bytes)
    except UnextractableTextError:
        with pool.connection() as conn:
            conn.execute(
                "update public.cv_documents set status = 'failed', error_message = %s where id = %s",
                ("PDF sin texto extraíble (probable escaneo sin OCR)", document_id),
            )
            conn.execute(
                "update public.candidates set status = 'error' where id = %s",
                (candidate_id,),
            )
        raise HTTPException(
            status_code=422,
            detail="El PDF no tiene texto extraíble. Completá el formulario manual.",
        )

    extract = extract_cv(text)

    with pool.connection() as conn:
        conn.execute(
            "update public.cv_documents set status = 'parsed', extracted = %s where id = %s",
            (extract.model_dump_json(), document_id),
        )
        conn.execute(
            """
            update public.candidates
            set headline = %s, degree = %s, overview = %s, skills = %s,
                interests = %s, status = 'ready'
            where id = %s
            """,
            (
                extract.headline,
                extract.degree,
                extract.overview,
                extract.skills,
                extract.interests,
                candidate_id,
            ),
        )

    return ProcessResponse(document_id=str(document_id), status="ready")


class StatusResponse(BaseModel):
    status: str


@router.get("/status", response_model=StatusResponse)
def get_status(user: AuthUser = Depends(get_current_user)) -> StatusResponse:
    candidate = _get_candidate(user)
    with pool.connection() as conn:
        row = conn.execute(
            "select status from public.candidates where id = %s",
            (candidate["id"],),
        ).fetchone()
    return StatusResponse(status=row[0])
