"""add candidate cv extraction columns

Revision ID: 158ac49d6fb3
Revises: ff92b2b050b1
Create Date: 2026-08-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '158ac49d6fb3'
down_revision: Union[str, Sequence[str], None] = 'ff92b2b050b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidates', sa.Column('youtube_url', sa.Text(), nullable=True), schema='public')
    op.add_column('candidates', sa.Column('detected_language', sa.Text(), nullable=True), schema='public')
    op.add_column(
        'candidates',
        sa.Column('is_risky_prompt', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='public',
    )
    op.add_column(
        'candidates',
        sa.Column(
            'suggestions',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
        schema='public',
    )
    op.create_check_constraint(
        'candidates_detected_language_check',
        'candidates',
        "detected_language in ('es','en','other')",
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('candidates_detected_language_check', 'candidates', schema='public', type_='check')
    op.drop_column('candidates', 'suggestions', schema='public')
    op.drop_column('candidates', 'is_risky_prompt', schema='public')
    op.drop_column('candidates', 'detected_language', schema='public')
    op.drop_column('candidates', 'youtube_url', schema='public')
