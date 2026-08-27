"""add candidates.cv_quality_ack, cv_responsibility_ack, cv_ack_at

Revision ID: 5fd162970924
Revises: 2fc06ca962aa
Create Date: 2026-08-27 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5fd162970924'
down_revision: Union[str, Sequence[str], None] = '2fc06ca962aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'candidates',
        sa.Column('cv_quality_ack', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='public',
    )
    op.add_column(
        'candidates',
        sa.Column('cv_responsibility_ack', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='public',
    )
    op.add_column(
        'candidates',
        sa.Column('cv_ack_at', sa.DateTime(timezone=True), nullable=True),
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'cv_ack_at', schema='public')
    op.drop_column('candidates', 'cv_responsibility_ack', schema='public')
    op.drop_column('candidates', 'cv_quality_ack', schema='public')
