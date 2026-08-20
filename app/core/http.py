from fastapi import Request


def get_client_ip(request: Request) -> str:
    """IP real del visitante. Detrás de un proxy (Railway en prod),
    request.client.host es la IP del proxy, no la del visitante -- hay que
    leer X-Forwarded-For (el primer valor es el cliente original). Sin
    esto, todos los visitantes detrás del mismo proxy hashean igual: el
    dedupe de visitas referidas y el rate limit del chat quedan rotos."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
