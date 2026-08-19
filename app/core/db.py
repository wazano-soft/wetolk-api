from psycopg_pool import ConnectionPool

from app.core.config import settings

# Un solo pool para todo el proceso. FastAPI conecta directo a Postgres
# (local en dev, Supabase en prod, mismo DATABASE_URL de siempre) — no pasa
# por PostgREST, así que las políticas RLS no aplican acá: este backend usa
# permisos de servicio y es responsable de sus propios checks de pertenencia.
pool = ConnectionPool(conninfo=settings.database_url, open=False)
