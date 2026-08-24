"""add feedback_reports table

Revision ID: df8028e1b377
Revises: 261d4812b656
Create Date: 2026-08-24 02:39:14.980416

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df8028e1b377'
down_revision: Union[str, Sequence[str], None] = '261d4812b656'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'feedback_reports',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('loom_url', sa.Text(), nullable=True),
        sa.Column('page_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('user_id is not null or email is not null', name='feedback_reports_identity_check'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('feedback_reports', schema='public')
