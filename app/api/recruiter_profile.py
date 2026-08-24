from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.search import _get_recruiter
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Profile

router = APIRouter()


class RecruiterProfileResponse(BaseModel):
    full_name: str | None
    company: str | None
    plan: str


class RecruiterProfileUpdate(BaseModel):
    # Ambos opcionales -- PATCH solo toca lo que venga en el body, mismo
    # patrón que ProfileUpdate en api/profile.py.
    full_name: str | None = None
    company: str | None = None


def _to_response(recruiter, profile: Profile | None) -> RecruiterProfileResponse:
    return RecruiterProfileResponse(
        full_name=profile.full_name if profile else None,
        company=recruiter.company,
        plan=recruiter.plan,
    )


@router.get("", response_model=RecruiterProfileResponse)
def get_recruiter_profile(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> RecruiterProfileResponse:
    recruiter = _get_recruiter(db, user)
    profile = db.get(Profile, user.id)
    return _to_response(recruiter, profile)


@router.patch("", response_model=RecruiterProfileResponse)
def update_recruiter_profile(
    body: RecruiterProfileUpdate,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecruiterProfileResponse:
    recruiter = _get_recruiter(db, user)
    profile = db.get(Profile, user.id)

    # model_fields_set (no "is not None"): un full_name explícito en null
    # tiene que poder borrar el nombre, no quedar ignorado en silencio --
    # mismo criterio que update_profile en api/profile.py.
    if "full_name" in body.model_fields_set:
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile.full_name = body.full_name
    if "company" in body.model_fields_set:
        recruiter.company = body.company

    db.commit()
    return _to_response(recruiter, profile)
