from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Candidate, CVDocument, Profile, Recruiter, Search
from app.services.agent_prompt import build_cv_context
from app.services.embeddings import get_embeddings
from app.services.search import extract_search_criteria, generate_match

router = APIRouter()


def _get_recruiter(db: Session, user: AuthUser) -> Recruiter:
    """Mismo patrón de provisioning perezoso que _get_candidate (cv.py),
    para el otro actor (RF-10, Fase 2)."""
    recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == user.id))
    if recruiter is not None:
        return recruiter

    # Una cuenta que ya es candidata no se puede volver reclutadora por
    # esta vía silenciosa -- sin este chequeo, cualquier candidato
    # autenticado podía llamar a /api/search y quedar provisionado como
    # reclutador sobre la marcha, con acceso a los perfiles de otros
    # candidatos sin haber pasado nunca por /reclutador (hallazgo de
    # code-review).
    existing_candidate = db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    if existing_candidate is not None:
        raise HTTPException(
            status_code=403, detail="This account is already registered as a candidate"
        )

    full_name = user.full_name or (user.email or "user").split("@", 1)[0]
    try:
        profile = db.get(Profile, user.id)
        if profile is None:
            db.add(Profile(id=user.id, full_name=full_name, role="recruiter"))
            db.flush()
        elif profile.role != "recruiter":
            # El trigger de Postgres (RF-01, ver comentario en cv.py)
            # siempre crea profiles con role='candidate' por defecto --
            # no distingue reclutadores. Llegar acá sin fila de Candidate
            # es la señal real de que esta cuenta es de un reclutador, así
            # que el default del trigger se corrige acá.
            profile.role = "recruiter"
        recruiter = Recruiter(user_id=user.id)
        db.add(recruiter)
        db.flush()
        return recruiter
    except IntegrityError:
        db.rollback()
        recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == user.id))
        if recruiter is None:
            raise
        return recruiter


class SearchRequest(BaseModel):
    query: str


class CandidateResult(BaseModel):
    slug: str
    full_name: str | None
    overview: str | None
    highlights: list[str]
    skills: list[str]
    years_experience: float | None
    work_mode: str | None
    location_city: str | None
    location_country: str | None
    score: int
    justification: str


class SearchResponse(BaseModel):
    results: list[CandidateResult]


TOP_N = 3


@router.post("", response_model=SearchResponse)
def search_candidates(
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    recruiter = _get_recruiter(db, user)

    criteria = extract_search_criteria(body.query)
    query_embedding = get_embeddings().embed_query(body.query)

    stmt = select(Candidate).where(
        Candidate.is_public.is_(True),
        Candidate.is_searchable.is_(True),
        Candidate.profile_embedding.is_not(None),
    )
    if criteria.work_mode:
        stmt = stmt.where(Candidate.work_mode == criteria.work_mode)
    if criteria.location:
        # El criterio extraído no distingue ciudad de país ("Argentina" vs
        # "Buenos Aires") -- buscar solo en location_city dejaba afuera
        # candidatos que matchean por país.
        stmt = stmt.where(
            or_(
                Candidate.location_city.ilike(f"%{criteria.location}%"),
                Candidate.location_country.ilike(f"%{criteria.location}%"),
            )
        )
    if criteria.years_min:
        stmt = stmt.where(Candidate.years_experience >= criteria.years_min)

    stmt = stmt.order_by(Candidate.profile_embedding.cosine_distance(query_embedding)).limit(TOP_N)
    candidates = db.scalars(stmt).all()

    results = []
    for candidate in candidates:
        owner_profile = db.get(Profile, candidate.user_id)
        cv_context = build_cv_context(_current_extracted(db, candidate.id))
        match = generate_match(body.query, cv_context)
        results.append(
            CandidateResult(
                slug=candidate.slug,
                full_name=owner_profile.full_name if owner_profile else None,
                overview=candidate.overview,
                highlights=match.highlights[:5],
                skills=candidate.skills,
                years_experience=candidate.years_experience,
                work_mode=candidate.work_mode,
                location_city=candidate.location_city,
                location_country=candidate.location_country,
                score=match.score,
                justification=match.justification,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)

    db.add(
        Search(
            recruiter_id=recruiter.id,
            raw_query=body.query,
            parsed=criteria.model_dump(mode="json"),
            results=[r.model_dump(mode="json") for r in results],
        )
    )
    db.commit()

    return SearchResponse(results=results)


def _current_extracted(db: Session, candidate_id: int) -> dict:
    document = db.scalar(
        select(CVDocument).where(
            CVDocument.candidate_id == candidate_id, CVDocument.is_current.is_(True)
        )
    )
    return document.extracted if document and document.extracted else {}
