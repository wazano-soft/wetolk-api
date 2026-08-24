import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.api.search import _get_recruiter
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import Candidate, ContactMessage, ContactRequest, Profile, Recruiter
from app.services import push

router = APIRouter()


def _resolve_actor(db: Session, user: AuthUser, contact_request: ContactRequest) -> Literal["candidate", "recruiter"]:
    candidate = db.scalar(select(Candidate).where(Candidate.user_id == uuid.UUID(user.id)))
    if candidate is not None and candidate.id == contact_request.candidate_id:
        return "candidate"
    recruiter = db.scalar(select(Recruiter).where(Recruiter.user_id == uuid.UUID(user.id)))
    if recruiter is not None and recruiter.id == contact_request.recruiter_id:
        return "recruiter"
    raise HTTPException(status_code=404, detail="Contact request not found")


class ContactRequestOut(BaseModel):
    id: str
    recruiter_company: str | None
    recruiter_name: str | None
    recruiter_email: str | None
    message: str
    status: str
    created_at: datetime


class ContactRequestsResponse(BaseModel):
    requests: list[ContactRequestOut]


@router.get("", response_model=ContactRequestsResponse)
def list_contact_requests(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ContactRequestsResponse:
    candidate = _get_candidate(db, user)
    contact_requests = db.scalars(
        select(ContactRequest)
        .where(ContactRequest.candidate_id == candidate.id)
        .order_by(ContactRequest.created_at.desc())
    ).all()

    # N+1 aceptable a esta escala -- pocos contact requests por candidato,
    # no justifica armar el join contra recruiters + profiles acá.
    out = []
    for cr in contact_requests:
        recruiter = db.get(Recruiter, cr.recruiter_id)
        recruiter_profile = db.get(Profile, recruiter.user_id) if recruiter else None
        out.append(
            ContactRequestOut(
                id=str(cr.id),
                recruiter_company=recruiter.company if recruiter else None,
                recruiter_name=recruiter_profile.full_name if recruiter_profile else None,
                recruiter_email=cr.recruiter_email,
                message=cr.message,
                status=cr.status,
                created_at=cr.created_at,
            )
        )

    return ContactRequestsResponse(requests=out)


class UpdateContactRequestStatus(BaseModel):
    status: Literal["accepted", "declined"]


@router.patch("/{request_id}", response_model=ContactRequestOut)
def update_contact_request_status(
    request_id: uuid.UUID,
    body: UpdateContactRequestStatus,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactRequestOut:
    candidate = _get_candidate(db, user)
    cr = db.get(ContactRequest, request_id)
    if cr is None or cr.candidate_id != candidate.id:
        raise HTTPException(status_code=404, detail="Contact request not found")

    cr.status = body.status
    cr.responded_at = datetime.now(timezone.utc)
    db.commit()

    recruiter = db.get(Recruiter, cr.recruiter_id)
    recruiter_profile = db.get(Profile, recruiter.user_id) if recruiter else None
    return ContactRequestOut(
        id=str(cr.id),
        recruiter_company=recruiter.company if recruiter else None,
        recruiter_name=recruiter_profile.full_name if recruiter_profile else None,
        recruiter_email=cr.recruiter_email,
        message=cr.message,
        status=cr.status,
        created_at=cr.created_at,
    )


class SentContactRequestOut(BaseModel):
    id: str
    candidate_slug: str
    candidate_name: str | None
    candidate_headline: str | None
    message: str
    status: str
    created_at: datetime
    responded_at: datetime | None


class SentContactRequestsResponse(BaseModel):
    requests: list[SentContactRequestOut]


@router.get("/sent", response_model=SentContactRequestsResponse)
def list_sent_contact_requests(
    user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> SentContactRequestsResponse:
    recruiter = _get_recruiter(db, user)
    contact_requests = db.scalars(
        select(ContactRequest)
        .where(ContactRequest.recruiter_id == recruiter.id)
        .order_by(ContactRequest.created_at.desc())
    ).all()

    # Mismo N+1 aceptable que en list_contact_requests -- pocas filas por
    # reclutador.
    out = []
    for cr in contact_requests:
        candidate = db.get(Candidate, cr.candidate_id)
        candidate_profile = db.get(Profile, candidate.user_id) if candidate else None
        out.append(
            SentContactRequestOut(
                id=str(cr.id),
                candidate_slug=candidate.slug if candidate else "",
                candidate_name=candidate_profile.full_name if candidate_profile else None,
                candidate_headline=candidate.headline if candidate else None,
                message=cr.message,
                status=cr.status,
                created_at=cr.created_at,
                responded_at=cr.responded_at,
            )
        )

    return SentContactRequestsResponse(requests=out)


class ThreadMessageOut(BaseModel):
    id: str
    sender_role: Literal["candidate", "recruiter"]
    body: str
    created_at: datetime


class ContactThreadResponse(BaseModel):
    contact_request_id: str
    status: str
    messages: list[ThreadMessageOut]


@router.get("/{request_id}/messages", response_model=ContactThreadResponse)
def get_contact_thread(
    request_id: uuid.UUID, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> ContactThreadResponse:
    cr = db.get(ContactRequest, request_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Contact request not found")
    _resolve_actor(db, user, cr)  # 404s if neither side owns it

    # El mensaje inicial de ContactRequest.message es sintéticamente el
    # primer mensaje del hilo (siempre lo mandó el reclutador -- hoy solo
    # los reclutadores pueden iniciar contacto), seguido de los
    # ContactMessage reales en orden.
    thread_messages = db.scalars(
        select(ContactMessage)
        .where(ContactMessage.contact_request_id == cr.id)
        .order_by(ContactMessage.created_at)
    ).all()
    messages = [
        ThreadMessageOut(id=f"initial-{cr.id}", sender_role="recruiter", body=cr.message, created_at=cr.created_at)
    ] + [
        ThreadMessageOut(id=str(m.id), sender_role=m.sender_role, body=m.body, created_at=m.created_at)
        for m in thread_messages
    ]
    return ContactThreadResponse(contact_request_id=str(cr.id), status=cr.status, messages=messages)


class ThreadMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post("/{request_id}/messages", response_model=ThreadMessageOut, status_code=201)
def post_contact_message(
    request_id: uuid.UUID,
    body: ThreadMessageIn,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThreadMessageOut:
    cr = db.get(ContactRequest, request_id)
    if cr is None:
        raise HTTPException(status_code=404, detail="Contact request not found")
    actor = _resolve_actor(db, user, cr)

    msg = ContactMessage(contact_request_id=cr.id, sender_role=actor, body=body.body)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Notifica al OTRO lado de la conversación.
    recipient_user_id = None
    if actor == "recruiter":
        candidate = db.get(Candidate, cr.candidate_id)
        recipient_user_id = candidate.user_id if candidate else None
        title = "Nuevo mensaje de un reclutador"
        url = "/dashboard/messages"
    else:
        recruiter = db.get(Recruiter, cr.recruiter_id)
        recipient_user_id = recruiter.user_id if recruiter else None
        title = "Nuevo mensaje de un candidato"
        url = "/recruiter/messages"
    if recipient_user_id is not None:
        push.send_push(db, recipient_user_id, {"title": title, "body": body.body[:120], "url": url})

    return ThreadMessageOut(id=str(msg.id), sender_role=msg.sender_role, body=msg.body, created_at=msg.created_at)
