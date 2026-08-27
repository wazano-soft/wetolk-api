from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import TOTAL_ONBOARDING_STEPS, Profile

router = APIRouter()


class ProfileResponse(BaseModel):
    slug: str
    full_name: str | None
    avatar_url: str | None
    headline: str | None
    degree: str | None
    overview: str | None
    skills: list[str]
    interests: list[str]
    work_mode: str | None
    location_city: str | None
    location_country: str | None
    willing_relocate: bool
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    linkedin_url: str | None
    github_url: str | None
    youtube_url: str | None
    portfolio_url: str | None
    agent_language: str
    is_public: bool
    is_searchable: bool
    status: str
    onboarding_step: int
    onboarding_finished: bool
    onboarding_finished_at: datetime | None


@router.get("", response_model=ProfileResponse)
def get_profile(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProfileResponse:
    candidate = _get_candidate(db, user)
    profile = db.get(Profile, user.id)
    return ProfileResponse(
        slug=candidate.slug,
        full_name=profile.full_name if profile else None,
        avatar_url=profile.avatar_url if profile else None,
        headline=candidate.headline,
        degree=candidate.degree,
        overview=candidate.overview,
        skills=candidate.skills,
        interests=candidate.interests,
        work_mode=candidate.work_mode,
        location_city=candidate.location_city,
        location_country=candidate.location_country,
        willing_relocate=bool(candidate.willing_relocate),
        salary_min=candidate.salary_min,
        salary_max=candidate.salary_max,
        salary_currency=candidate.salary_currency,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        youtube_url=candidate.youtube_url,
        portfolio_url=candidate.portfolio_url,
        agent_language=candidate.agent_language,
        is_public=candidate.is_public,
        is_searchable=candidate.is_searchable,
        status=candidate.status,
        onboarding_step=candidate.onboarding_step,
        onboarding_finished=candidate.onboarding_finished,
        onboarding_finished_at=candidate.onboarding_finished_at,
    )


class ProfileUpdate(BaseModel):
    # Todos opcionales -- PATCH solo toca lo que venga en el body.
    full_name: str | None = None
    headline: str | None = None
    degree: str | None = None
    overview: str | None = None
    skills: list[str] | None = None
    interests: list[str] | None = None
    work_mode: Literal["remote", "hybrid", "onsite"] | None = None
    location_city: str | None = None
    location_country: str | None = None
    willing_relocate: bool | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = Field(None, max_length=3)
    linkedin_url: str | None = None
    github_url: str | None = None
    youtube_url: str | None = None
    portfolio_url: str | None = None
    agent_language: Literal["es", "en"] | None = None
    is_searchable: bool | None = None
    onboarding_step: int | None = Field(None, ge=1, le=TOTAL_ONBOARDING_STEPS)

    @field_validator("location_city")
    @classmethod
    def _normalize_city(cls, value: str | None) -> str | None:
        # location_city es texto libre que el candidato tipea a mano (no lo
        # extrae el parser de CV) -- sin esto, "morelia" quedaba en
        # minúscula tal cual se guardó, en vez de "Morelia".
        if not value:
            return value
        particles = {"de", "del", "la", "las", "los", "y"}
        words = value.strip().split()
        capitalized = [
            w.lower() if w.lower() in particles else w[:1].upper() + w[1:].lower()
            for w in words
        ]
        if capitalized:
            capitalized[0] = capitalized[0][:1].upper() + capitalized[0][1:]
        return " ".join(capitalized)

    @model_validator(mode="after")
    def _validate_salary_range(self) -> "ProfileUpdate":
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("salary_min cannot be greater than salary_max")
        return self


# Columnas NOT NULL en candidates -- un null explícito en el body para
# cualquiera de estas rompía en el commit con un IntegrityError sin
# capturar (500 crudo). full_name no está acá porque profiles.full_name
# sí admite null: un candidato puede querer borrarlo.
_NOT_NULLABLE_FIELDS = {
    "skills", "interests", "agent_language", "is_searchable", "onboarding_step",
}


@router.patch("", response_model=ProfileResponse)
def update_profile(
    body: ProfileUpdate,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    candidate = _get_candidate(db, user)

    updates = body.model_dump(exclude_unset=True, exclude={"full_name"})
    for field in _NOT_NULLABLE_FIELDS & updates.keys():
        if updates[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    if "onboarding_step" in updates:
        # Monotónico -- una pestaña vieja del wizard (ej. quedó abierta en
        # el paso 2 mientras en otra ya se llegó al 4) no puede retroceder
        # el progreso guardado.
        updates["onboarding_step"] = max(updates["onboarding_step"], candidate.onboarding_step)
        # onboarding_finished(_at) no lo manda el cliente -- se deriva acá,
        # una sola vez, para que sea un marcador server-side confiable
        # (segmentación/campañas) independiente de si el wizard cambia de
        # cantidad de pasos más adelante.
        if updates["onboarding_step"] >= TOTAL_ONBOARDING_STEPS and not candidate.onboarding_finished:
            updates["onboarding_finished"] = True
            updates["onboarding_finished_at"] = datetime.now(timezone.utc)
    for field, value in updates.items():
        setattr(candidate, field, value)

    profile = db.get(Profile, user.id)
    # model_fields_set (no "is not None"): un full_name explícito en null
    # tiene que poder borrar el nombre, no quedar ignorado en silencio.
    if "full_name" in body.model_fields_set:
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile.full_name = body.full_name

    db.flush()
    return ProfileResponse(
        slug=candidate.slug,
        full_name=profile.full_name if profile else None,
        avatar_url=profile.avatar_url if profile else None,
        headline=candidate.headline,
        degree=candidate.degree,
        overview=candidate.overview,
        skills=candidate.skills,
        interests=candidate.interests,
        work_mode=candidate.work_mode,
        location_city=candidate.location_city,
        location_country=candidate.location_country,
        willing_relocate=bool(candidate.willing_relocate),
        salary_min=candidate.salary_min,
        salary_max=candidate.salary_max,
        salary_currency=candidate.salary_currency,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        youtube_url=candidate.youtube_url,
        portfolio_url=candidate.portfolio_url,
        agent_language=candidate.agent_language,
        is_public=candidate.is_public,
        is_searchable=candidate.is_searchable,
        status=candidate.status,
        onboarding_step=candidate.onboarding_step,
        onboarding_finished=candidate.onboarding_finished,
        onboarding_finished_at=candidate.onboarding_finished_at,
    )
