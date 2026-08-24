"""add cv_documents chunks_status

Revision ID: 6c0e1c9b7a2f
Revises: 158ac49d6fb3
Create Date: 2026-08-22 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6c0e1c9b7a2f'
down_revision: Union[str, Sequence[str], None] = '158ac49d6fb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cv_documents',
        sa.Column('chunks_status', sa.Text(), server_default='pending', nullable=False),
        schema='public',
    )
    op.create_check_constraint(
        'cv_documents_chunks_status_check',
        'cv_documents',
        "chunks_status in ('pending','done','failed')",
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('cv_documents_chunks_status_check', 'cv_documents', schema='public', type_='check')
    op.drop_column('cv_documents', 'chunks_status', schema='public')
