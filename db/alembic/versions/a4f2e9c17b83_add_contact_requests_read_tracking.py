"""add contact_requests read tracking

Revision ID: a4f2e9c17b83
Revises: d940b7124ee0
Create Date: 2026-08-26 10:00:00.000000

Un timestamp por lado en vez de read_at por ContactMessage -- cubre tanto
"conversación nueva sin abrir" como "hay mensajes nuevos" con la misma
columna (todo lo posterior a *_last_read_at cuenta como no leído), y solo
hace falta actualizar una fila al abrir la conversación en vez de N.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4f2e9c17b83'
down_revision: Union[str, Sequence[str], None] = 'd940b7124ee0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'contact_requests',
        sa.Column('candidate_last_read_at', sa.DateTime(timezone=True), nullable=True),
        schema='public',
    )
    op.add_column(
        'contact_requests',
        sa.Column('recruiter_last_read_at', sa.DateTime(timezone=True), nullable=True),
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contact_requests', 'recruiter_last_read_at', schema='public')
    op.drop_column('contact_requests', 'candidate_last_read_at', schema='public')
