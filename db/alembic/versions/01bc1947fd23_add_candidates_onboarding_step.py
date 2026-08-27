"""add candidates.onboarding_step

Revision ID: 01bc1947fd23
Revises: 101ec6ff06d2
Create Date: 2026-08-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '01bc1947fd23'
down_revision: Union[str, Sequence[str], None] = '101ec6ff06d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'candidates',
        sa.Column('onboarding_step', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        schema='public',
    )
    # server_default=1 aplica a filas NUEVAS -- sin este backfill, todo
    # candidato que ya existía (con perfil real, armado con el wizard
    # viejo de 3 pasos o a mano en /dashboard) queda marcado como si nunca
    # hubiera empezado el onboarding. La siguiente migración backfillea
    # onboarding_finished mirando onboarding_step >= 4, así que si esto no
    # se corrige acá esa migración no matchea a nadie y el guard de
    # dashboard/layout.tsx manda a TODA la base existente de vuelta al
    # wizard, bloqueada en el paso 1 pidiendo resubir un CV que ya tienen.
    op.execute("UPDATE public.candidates SET onboarding_step = 4")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'onboarding_step', schema='public')
