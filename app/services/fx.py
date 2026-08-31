import logging
from decimal import ROUND_HALF_UP, Decimal

import httpx

from app.core.config import settings
from app.services.cache import cached

logger = logging.getLogger(__name__)

# Serie SF43718 = "Tipo de cambio Pesos por dólar E.U.A. FIX" del SIE de
# Banxico. Se publica una vez por día hábil (~12:00 CT); cachear 12h sobra
# y nos mantiene lejos del rate limit del API (200 req / 5 min por token).
# `datos/oportuno` devuelve el último dato disponible (fin de semana y
# feriados incluidos: da el último hábil).
_BANXICO_URL = (
    "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718/datos/oportuno"
)
_CACHE_KEY = "fx:usd_mxn"
_CACHE_TTL_SECONDS = 12 * 60 * 60


def _fetch_usd_mxn() -> Decimal:
    fallback = Decimal(str(settings.usd_mxn_fallback_rate))
    if not settings.banxico_token:
        logger.warning("BANXICO_TOKEN vacío -- usando tasa fallback USD/MXN=%s", fallback)
        return fallback
    try:
        res = httpx.get(
            _BANXICO_URL,
            headers={"Bmx-Token": settings.banxico_token},
            timeout=10,
        )
        res.raise_for_status()
        dato = res.json()["bmx"]["series"][0]["datos"][0]["dato"]
        return Decimal(str(dato))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.warning("Banxico FIX no disponible (%s) -- usando fallback %s", exc, fallback)
        return fallback


def usd_mxn_rate() -> Decimal:
    """Pesos por dólar según el FIX de Banxico, cacheado 12h."""
    return cached(_CACHE_KEY, _fetch_usd_mxn, _CACHE_TTL_SECONDS)


def usd_to_mxn_cents(amount_usd: float) -> int:
    """Convierte un monto en dólares a centavos de peso para el `unit_amount`
    de Stripe. Aplica `fx_buffer` sobre la tasa FIX porque entre esta llamada
    y el pago real la tasa se mueve, y si el donante paga desde afuera Stripe
    le suma su propio spread de Adaptive Pricing encima."""
    mxn = Decimal(str(amount_usd)) * usd_mxn_rate() * Decimal(str(settings.fx_buffer))
    return int((mxn * 100).to_integral_value(rounding=ROUND_HALF_UP))
