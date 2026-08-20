from fastapi import Request


def get_client_ip(request: Request) -> str:
    """IP real del visitante. Detrás de un proxy (Railway en prod),
    request.client.host es la IP del proxy, no la del visitante -- hay que
    leer X-Forwarded-For.

    Se toma el ÚLTIMO valor de la cadena, no el primero. Un proxy le
    AGREGA la IP del que se conectó a él al final del header (o lo crea
    de cero si no existía) -- ese último valor es el único que el propio
    proxy garantiza, nunca lo escribe el cliente. Los valores anteriores
    en la cadena los pudo haber puesto cualquiera antes de llegar acá.
    Usar el primer valor (como hacía la versión anterior de esta función)
    deja que cualquiera falsifique su IP mandando su propio header --
    rompiendo tanto el rate limit del chat como el dedupe de visitas
    referidas y el umbral anti-fraude de "alcance" (RF-08). Con un solo
    proxy conocido delante (Railway), el último hop es el confiable.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
