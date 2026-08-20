from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import CVDocument, Profile, QuickQuestion
from app.services import r2
from app.services.referral import get_or_create_tier
from app.services.supabase_admin import delete_auth_user

router = APIRouter()


class CVDocumentExport(BaseModel):
    filename: str
    size_bytes: int
    is_current: bool
    created_at: datetime
    extracted: dict[str, Any] | None


class AccountExport(BaseModel):
    slug: str
    full_name: str | None
    headline: str | None
    degree: str | None
    overview: str | None
    skills: list[str]
    interests: list[str]
    years_experience: float | None
    work_mode: str | None
    location_city: str | None
    location_country: str | None
    willing_relocate: bool
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    agent_language: str
    is_public: bool
    is_searchable: bool
    quick_questions: list[str]
    cv_documents: list[CVDocumentExport]
    tier: str
    share_count: int
    referral_count: int
    donated_total: float


# Exportación de datos (RNF-03). Se excluyen deliberadamente los
# transcripts de conversación: son registros de uso generados por
# visitantes hablando con el agente, no "los datos del candidato" en el
# sentido de portabilidad -- decisión de alcance explícita, no un olvido.
@router.get("/export", response_model=AccountExport)
def export_account(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> AccountExport:
    candidate = _get_candidate(db, user)
    profile = db.get(Profile, user.id)
    quick_questions = db.scalars(
        select(QuickQuestion.question)
        .where(QuickQuestion.candidate_id == candidate.id)
        .order_by(QuickQuestion.position)
    ).all()
    documents = db.scalars(
        select(CVDocument).where(CVDocument.candidate_id == candidate.id)
    ).all()
    tier = get_or_create_tier(db, candidate.id)

    return AccountExport(
        slug=candidate.slug,
        full_name=profile.full_name if profile else None,
        headline=candidate.headline,
        degree=candidate.degree,
        overview=candidate.overview,
        skills=candidate.skills,
        interests=candidate.interests,
        years_experience=candidate.years_experience,
        work_mode=candidate.work_mode,
        location_city=candidate.location_city,
        location_country=candidate.location_country,
        willing_relocate=bool(candidate.willing_relocate),
        salary_min=candidate.salary_min,
        salary_max=candidate.salary_max,
        salary_currency=candidate.salary_currency,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        portfolio_url=candidate.portfolio_url,
        agent_language=candidate.agent_language,
        is_public=candidate.is_public,
        is_searchable=candidate.is_searchable,
        quick_questions=list(quick_questions),
        cv_documents=[
            CVDocumentExport(
                filename=d.filename,
                size_bytes=d.size_bytes,
                is_current=d.is_current,
                created_at=d.created_at,
                extracted=d.extracted,
            )
            for d in documents
        ],
        tier=tier.tier,
        share_count=tier.share_count,
        referral_count=tier.referral_count,
        donated_total=float(tier.donated_total),
    )


class DeleteAccountResponse(BaseModel):
    deleted: bool
    r2_objects_deleted: int


# Borrado de cuenta (RNF-03): PDF en R2 + todas las filas + vectores. El
# orden importa -- primero R2 (irreversible pero no crítico si falla a
# medias, se puede reintentar por prefijo), después la fila de Profile
# (cascadea a Candidate y todo lo que cuelga de ahí vía ondelete=CASCADE,
# confirmado en models.py), y al final el usuario de auth -- si algo de
# esto falla antes, todavía queda una cuenta funcional en vez de un
# usuario de auth huérfano sin datos.
@router.delete("", response_model=DeleteAccountResponse)
def delete_account(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> DeleteAccountResponse:
    candidate = _get_candidate(db, user)
    storage_token = candidate.storage_token

    r2_deleted = r2.delete_prefix(f"candidates/{storage_token}/")

    profile = db.get(Profile, user.id)
    if profile is not None:
        db.delete(profile)
    db.commit()

    delete_auth_user(user.id)

    return DeleteAccountResponse(deleted=True, r2_objects_deleted=r2_deleted)
