from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Profile

router = APIRouter()


class ProfileResponse(BaseModel):
    slug: str
    full_name: str | None
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
    portfolio_url: str | None
    agent_language: str
    is_public: bool
    is_searchable: bool
    status: str


@router.get("", response_model=ProfileResponse)
def get_profile(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProfileResponse:
    candidate = _get_candidate(db, user)
    profile = db.get(Profile, user.id)
    return ProfileResponse(
        slug=candidate.slug,
        full_name=profile.full_name if profile else None,
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
        portfolio_url=candidate.portfolio_url,
        agent_language=candidate.agent_language,
        is_public=candidate.is_public,
        is_searchable=candidate.is_searchable,
        status=candidate.status,
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
    portfolio_url: str | None = None
    agent_language: Literal["es", "en"] | None = None
    is_public: bool | None = None
    is_searchable: bool | None = None


@router.patch("", response_model=ProfileResponse)
def update_profile(
    body: ProfileUpdate,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    candidate = _get_candidate(db, user)

    updates = body.model_dump(exclude_unset=True, exclude={"full_name"})
    for field, value in updates.items():
        setattr(candidate, field, value)

    if body.full_name is not None:
        profile = db.get(Profile, user.id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile.full_name = body.full_name

    db.flush()
    return get_profile(user=user, db=db)
