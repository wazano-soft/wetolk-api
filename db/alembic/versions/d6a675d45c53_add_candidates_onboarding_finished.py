"""add candidates.onboarding_finished(_at)

Revision ID: d6a675d45c53
Revises: 01bc1947fd23
Create Date: 2026-08-27 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd6a675d45c53'
down_revision: Union[str, Sequence[str], None] = '01bc1947fd23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'candidates',
        sa.Column('onboarding_finished', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='public',
    )
    op.add_column(
        'candidates',
        sa.Column('onboarding_finished_at', sa.DateTime(timezone=True), nullable=True),
        schema='public',
    )
    # Backfill de quien ya venía con onboarding_step al tope antes de que
    # este flag existiera -- si no, quedaban marcados como "no terminado"
    # sin ninguna forma de distinguirlos.
    op.execute(
        "UPDATE public.candidates SET onboarding_finished = true, onboarding_finished_at = now() "
        "WHERE onboarding_step >= 4"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'onboarding_finished_at', schema='public')
    op.drop_column('candidates', 'onboarding_finished', schema='public')
