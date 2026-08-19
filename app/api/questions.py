from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import CVDocument, QuickQuestion
from app.services.agent_prompt import build_cv_context
from app.services.question_suggestions import suggest_questions

router = APIRouter()


class QuestionsResponse(BaseModel):
    questions: list[str]


@router.get("", response_model=QuestionsResponse)
def get_questions(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> QuestionsResponse:
    candidate = _get_candidate(db, user)
    rows = db.scalars(
        select(QuickQuestion)
        .where(QuickQuestion.candidate_id == candidate.id)
        .order_by(QuickQuestion.position)
    )
    return QuestionsResponse(questions=[r.question for r in rows])


class ReplaceQuestionsRequest(BaseModel):
    # RF-05: máximo 5, mínimo 0. PUT reemplaza el set completo -- no hay
    # endpoints por item porque no hace falta direccionar una pregunta
    # puntual desde afuera, siempre se guardan/leen las 5 juntas.
    questions: list[str] = Field(max_length=5)


@router.put("", response_model=QuestionsResponse)
def replace_questions(
    body: ReplaceQuestionsRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuestionsResponse:
    for q in body.questions:
        if len(q) > 80:
            raise HTTPException(status_code=422, detail="Cada pregunta puede tener hasta 80 caracteres")

    candidate = _get_candidate(db, user)
    db.query(QuickQuestion).filter(QuickQuestion.candidate_id == candidate.id).delete()
    for i, question in enumerate(body.questions, start=1):
        db.add(QuickQuestion(candidate_id=candidate.id, question=question, position=i))

    return QuestionsResponse(questions=body.questions)


class SuggestQuestionsResponse(BaseModel):
    suggestions: list[str]


@router.post("/suggest", response_model=SuggestQuestionsResponse)
def suggest(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> SuggestQuestionsResponse:
    candidate = _get_candidate(db, user)
    document = db.scalar(
        select(CVDocument).where(
            CVDocument.candidate_id == candidate.id, CVDocument.is_current.is_(True)
        )
    )
    if document is None or not document.extracted:
        raise HTTPException(status_code=409, detail="El perfil todavía no está listo")

    cv_context = build_cv_context(document.extracted)
    return SuggestQuestionsResponse(suggestions=suggest_questions(cv_context))
