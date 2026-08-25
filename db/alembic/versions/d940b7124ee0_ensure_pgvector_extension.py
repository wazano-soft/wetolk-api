"""ensure pgvector extension

Revision ID: d940b7124ee0
Revises: df8028e1b377
Create Date: 2026-08-24 21:39:45.507825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd940b7124ee0'
down_revision: Union[str, Sequence[str], None] = 'df8028e1b377'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    pass
