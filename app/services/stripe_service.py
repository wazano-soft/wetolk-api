import stripe

from app.core.config import settings

stripe.api_key = settings.stripe_secret_key

DONATION_CURRENCY = "mxn"


def create_checkout_session(
    candidate_id: int, candidate_slug: str, amount_cents: int, success_url: str, cancel_url: str
) -> stripe.checkout.Session:
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": DONATION_CURRENCY,
                    "product_data": {"name": f"Aporte a Wetölk — {candidate_slug}"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        metadata={"candidate_id": str(candidate_id)},
        success_url=success_url,
        cancel_url=cancel_url,
    )


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
