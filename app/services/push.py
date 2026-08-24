import json
import logging
import uuid

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PushSubscription

logger = logging.getLogger(__name__)

# webpush() reenvía timeout=None (su propio default) directo a requests --
# el fallback de 10s de pywebpush solo aplica cuando el kwarg está
# ausente, no cuando vale None, así que sin esto un push endpoint colgado
# bloquea el thread del request que disparó la notificación indefinidamente.
_WEBPUSH_TIMEOUT = 10


def send_push(db: Session, user_id: uuid.UUID, payload: dict) -> None:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        logger.warning("Push notification skipped: VAPID keys not configured")
        return

    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
    stale_ids = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                timeout=_WEBPUSH_TIMEOUT,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                # Suscripción vencida/revocada del lado del navegador --
                # se poda para no seguir intentando.
                stale_ids.append(sub.id)
            else:
                # Otros status (ej. 500 transitorio del push service) no
                # tumban el request que disparó la notificación (posteo de
                # mensaje, etc), pero sí quedan logueados -- antes se
                # tragaban en silencio total, sin ninguna traza.
                logger.warning("Push delivery failed for subscription %s: %s", sub.id, exc)
        except Exception:
            logger.warning("Push delivery failed for subscription %s", sub.id, exc_info=True)
    if stale_ids:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale_ids)).delete(synchronize_session=False)
        db.commit()
