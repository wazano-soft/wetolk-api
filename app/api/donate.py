import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cv import _get_candidate
from app.core.auth import AuthUser, get_current_user
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.services.referral import advance_tier, get_or_create_tier
from app.services.stripe_service import construct_webhook_event, create_checkout_session

router = APIRouter()


class CheckoutSessionRequest(BaseModel):
    amount: float  # en la moneda mostrada al usuario (MXN), no en centavos


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
def create_donation_checkout(
    body: CheckoutSessionRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse:
    if body.amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be positive")

    candidate = _get_candidate(db, user)
    session = create_checkout_session(
        candidate_id=candidate.id,
        candidate_slug=candidate.slug,
        amount_cents=round(body.amount * 100),
        success_url=f"{settings.frontend_url}/dashboard/share?donated=1",
        cancel_url=f"{settings.frontend_url}/dashboard/share",
    )
    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")
    return CheckoutSessionResponse(checkout_url=session.url)


# Dedup en memoria de eventos ya procesados -- mismo criterio de MVP de
# instancia única que el resto del proyecto (cache.py, rate limiter en
# agent_turn.py). Stripe reintenta la entrega del webhook si no responde
# 2xx a tiempo; sin esto, un reintento sumaría el aporte dos veces a
# donated_total (no es un cobro doble -- Stripe ya cobró una sola vez --
# pero sí un conteo doble en el nivel de "Aporta o Comparte").
_processed_events: set[str] = set()


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict[str, bool]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = construct_webhook_event(payload, sig_header)
    except (stripe.error.SignatureVerificationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    if event.id in _processed_events:
        return {"received": True}
    _processed_events.add(event.id)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        candidate_id = int(session["metadata"]["candidate_id"])
        amount_total = session["amount_total"] or 0  # centavos

        with SessionLocal() as db:
            tier = get_or_create_tier(db, candidate_id)
            tier.donated_total = float(tier.donated_total) + amount_total / 100
            # RF-07: cualquier monto desbloquea Impulso de inmediato.
            advance_tier(tier, "impulso", "donation")
            db.commit()

    return {"received": True}
