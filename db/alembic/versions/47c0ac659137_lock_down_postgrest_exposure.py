"""enable RLS on tables exposed to PostgREST, fix security definer view

Revision ID: 47c0ac659137
Revises: b7e12ca9f014
Create Date: 2026-08-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '47c0ac659137'
down_revision: Union[str, Sequence[str], None] = 'b7e12ca9f014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Ninguna de estas tablas se consulta vía la API REST de Supabase (todo el
# acceso real pasa por FastAPI con DATABASE_URL, que conecta como el owner y
# no queda sujeto a RLS) -- Supabase Security Advisor las marcaba como
# alcanzables por cualquiera con la anon key, sin ninguna policy que lo
# impida. RLS sin policies = deny-all para los roles anon/authenticated de
# PostgREST, sin tocar el acceso del backend.
TABLES = [
    "candidate_embeddings",
    "procrastinate_workers",
    "procrastinate_jobs",
    "procrastinate_periodic_defers",
    "procrastinate_events",
    "push_subscriptions",
    "contact_messages",
    "feedback_reports",
    "alembic_version",
]


def upgrade() -> None:
    """Upgrade schema."""
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')

    # security_invoker en views es PG15+ (Supabase corre 15+, pero dev local
    # puede estar en 14) -- sin esto la ALTER VIEW rompe en local.
    bind = op.get_bind()
    server_version = bind.execute(
        text("SHOW server_version_num")
    ).scalar()
    if int(server_version) >= 150000:
        # La view ya filtraba a is_public=true y solo columnas no sensibles,
        # pero al no declarar security_invoker corría con permisos del owner
        # (bypassing RLS de candidates) en vez de los del rol que consulta.
        op.execute("ALTER VIEW public.public_profiles SET (security_invoker = true)")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    server_version = bind.execute(
        text("SHOW server_version_num")
    ).scalar()
    if int(server_version) >= 150000:
        op.execute("ALTER VIEW public.public_profiles SET (security_invoker = false)")
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
