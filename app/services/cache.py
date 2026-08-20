import time
from collections.abc import Callable
from typing import TypeVar

# Cache en memoria, mismo espíritu que el rate limiter de agent_turn.py:
# una sola instancia de Railway en el MVP, sin Redis en el presupuesto de
# $5/mes (ver 03-documento-tecnico.md). GET /api/a/{slug} es el endpoint
# que más tráfico recibe bajo un pico viral -- este cache le baja la carga
# a la DB sin tocar la lógica del handler.
DEFAULT_TTL_SECONDS = 60

T = TypeVar("T")
_store: dict[str, tuple[float, object]] = {}


def cached(key: str, compute: Callable[[], T], ttl_seconds: float = DEFAULT_TTL_SECONDS) -> T:
    hit = _store.get(key)
    now = time.monotonic()
    if hit is not None and hit[0] > now:
        return hit[1]  # type: ignore[return-value]

    value = compute()
    _store[key] = (now + ttl_seconds, value)
    return value
