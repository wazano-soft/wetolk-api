import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_optional_user
from app.core.db import get_db
from app.models import FeedbackReport

router = APIRouter()


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    email: str | None = None
    loom_url: str | None = None
    page_url: str | None = None


class FeedbackResponse(BaseModel):
    id: str


@router.post("", response_model=FeedbackResponse)
def create_feedback(
    body: FeedbackRequest,
    user: AuthUser | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    # Beta abierta: sin sesión, el email es la única forma de responderle a
    # quien reporta -- por eso es obligatorio en ese caso (mismo criterio
    # que el CheckConstraint feedback_reports_identity_check en la DB).
    if user is None and not body.email:
        raise HTTPException(status_code=422, detail="email is required when not logged in")

    report = FeedbackReport(
        user_id=uuid.UUID(user.id) if user else None,
        email=body.email,
        message=body.message,
        loom_url=body.loom_url,
        page_url=body.page_url,
    )
    db.add(report)
    db.flush()
    return FeedbackResponse(id=str(report.id))
