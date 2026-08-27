import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import RecruiterWaitlistSignup

router = APIRouter()

# Sin el extra "email-validator" que pide EmailStr -- alcanza con esto para
# el único propósito acá (evitar basura obvia antes de guardar).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RecruiterWaitlistRequest(BaseModel):
    email: str
    name: str | None = None

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("invalid email")
        return value

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class RecruiterWaitlistResponse(BaseModel):
    already_registered: bool


@router.post("/recruiter", response_model=RecruiterWaitlistResponse)
def join_recruiter_waitlist(
    body: RecruiterWaitlistRequest, db: Session = Depends(get_db)
) -> RecruiterWaitlistResponse:
    # Sin sesión a propósito -- la funcionalidad de reclutador todavía no
    # está liberada (ver RECRUITER_COMING_SOON en el frontend), así que
    # nadie tiene cuenta todavía en este flujo.
    already = db.scalar(
        select(RecruiterWaitlistSignup).where(RecruiterWaitlistSignup.email == body.email)
    )

    # ON CONFLICT DO UPDATE en vez de DO NOTHING -- si ya estaba anotado
    # solo con el email y ahora manda el nombre, lo completa en vez de
    # ignorarlo; COALESCE evita pisar un nombre ya guardado con null.
    stmt = insert(RecruiterWaitlistSignup).values(email=body.email, name=body.name)
    stmt = stmt.on_conflict_do_update(
        index_elements=["email"],
        set_={"name": func.coalesce(stmt.excluded.name, RecruiterWaitlistSignup.name)},
    )
    db.execute(stmt)
    db.flush()
    return RecruiterWaitlistResponse(already_registered=already is not None)
