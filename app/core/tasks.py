import procrastinate

from app.core.config import settings

# Conector async por defecto -- soporta tanto `.defer()` síncrono (usado
# desde los endpoints, que son `def` no `async def`) como el worker async
# embebido en el lifespan de FastAPI (ver app/main.py). No hace falta Redis:
# la cola vive en el mismo Postgres, con reintentos persistidos en
# procrastinate_jobs (schema aplicado en db/alembic/versions/
# 8ec0f1c21f2a_add_procrastinate_schema.py).
task_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=settings.database_url)
)
