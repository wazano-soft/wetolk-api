"""fix mutable search_path and lock down handle_new_user RPC

Revision ID: d49b1feda36a
Revises: 47c0ac659137
Create Date: 2026-08-27 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd49b1feda36a'
down_revision: Union[str, Sequence[str], None] = '47c0ac659137'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Se resuelve por oid en vez de hardcodear firmas porque las procrastinate_*
# son de una librería vendorizada (cola de jobs) y match_cv_chunks toma
# vector -- ambas pueden variar de firma entre versiones/entornos.
_SET_SEARCH_PATH = """
DO $$
DECLARE
    fn regprocedure;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND (p.proname LIKE 'procrastinate_%' OR p.proname = 'match_cv_chunks')
    LOOP
        EXECUTE format('ALTER FUNCTION %s SET search_path = public, pg_temp', fn);
    END LOOP;
END $$;
"""

_RESET_SEARCH_PATH = """
DO $$
DECLARE
    fn regprocedure;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND (p.proname LIKE 'procrastinate_%' OR p.proname = 'match_cv_chunks')
    LOOP
        EXECUTE format('ALTER FUNCTION %s RESET search_path', fn);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_SET_SEARCH_PATH)

    # handle_new_user es SECURITY DEFINER para poder insertar en
    # public.profiles durante el trigger de auth.users -- pero eso también
    # la hace invocable directo vía /rest/v1/rpc/handle_new_user por
    # cualquier anon/authenticated, sin pasar por un signup real. La
    # ejecución del trigger en sí no depende de este GRANT.
    # anon/authenticated los provisiona Supabase -- no existen en un
    # Postgres local plano, de ahí el chequeo.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM authenticated;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
                GRANT EXECUTE ON FUNCTION public.handle_new_user() TO anon;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
                GRANT EXECUTE ON FUNCTION public.handle_new_user() TO authenticated;
            END IF;
        END $$;
        """
    )
    op.execute(_RESET_SEARCH_PATH)
