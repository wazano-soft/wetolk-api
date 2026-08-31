import stripe

from app.core.config import settings

stripe.api_key = settings.stripe_secret_key

# La cuenta de Stripe es de México: liquida en MXN y solo cobra en MXN a
# tarjetas locales. Los presets se piensan en USD y se convierten a
# centavos de peso antes de llegar acá (ver services/fx.py). Con Adaptive
# Pricing activado en el Dashboard, Stripe le muestra al donante extranjero
# su moneda local partiendo de este MXN.
DONATION_CURRENCY = "mxn"


def create_checkout_session(
    amount_cents: int,
    success_url: str,
    cancel_url: str,
    candidate_id: int | None = None,
    candidate_slug: str | None = None,
) -> stripe.checkout.Session:
    # candidate_id=None es un aporte general al home, sin candidato
    # asociado -- el webhook lo distingue por la ausencia de metadata y no
    # le suma nivel/tier a nadie (RF-07 solo aplica a aportes dirigidos a
    # un agente puntual).
    product_name = f"Aporte a Wetölk — {candidate_slug}" if candidate_slug else "Aporte a Wetölk"
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": DONATION_CURRENCY,
                    "product_data": {"name": product_name},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        metadata={"candidate_id": str(candidate_id)} if candidate_id is not None else {},
        success_url=success_url,
        cancel_url=cancel_url,
    )


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
