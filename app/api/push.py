import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.db import get_db
from app.models import PushSubscription

router = APIRouter()


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.post("/subscribe", status_code=201)
def subscribe(
    body: SubscribeIn, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing is not None:
        existing.user_id = uuid.UUID(user.id)
        existing.p256dh = body.keys.p256dh
        existing.auth = body.keys.auth
        db.commit()
    else:
        db.add(
            PushSubscription(
                user_id=uuid.UUID(user.id),
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # Dos POST /subscribe casi simultáneos para el mismo endpoint
            # (ej. el botón inline y el modal de NotificationPrompt
            # montados a la vez) pueden pisarse acá -- mismo criterio que
            # el resto del código para esta carrera contra una unique
            # constraint.
            db.rollback()
            existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
            if existing is None:
                raise
            existing.user_id = uuid.UUID(user.id)
            existing.p256dh = body.keys.p256dh
            existing.auth = body.keys.auth
            db.commit()
    return {"status": "subscribed"}


@router.delete("/subscribe")
def unsubscribe(
    endpoint: str, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == endpoint, PushSubscription.user_id == uuid.UUID(user.id)
    ).delete()
    db.commit()
    return {"status": "unsubscribed"}
