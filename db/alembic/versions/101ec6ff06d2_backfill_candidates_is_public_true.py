"""backfill candidates.is_public=true for every candidate

Revision ID: 101ec6ff06d2
Revises: d49b1feda36a
Create Date: 2026-08-27 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '101ec6ff06d2'
down_revision: Union[str, Sequence[str], None] = 'd49b1feda36a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Decisión de producto: todo perfil de candidato es público -- el
    # control ya no existe en los formularios (ver ProfileUpdate en
    # api/profile.py, que dejó de aceptar is_public). Esto backfillea a
    # quien lo haya apagado antes de ese cambio.
    op.execute("UPDATE public.candidates SET is_public = true WHERE is_public = false")


def downgrade() -> None:
    """Downgrade schema."""
    # No hay forma de recuperar quién tenía is_public=false antes del
    # backfill -- downgrade es un no-op intencional.
    pass
