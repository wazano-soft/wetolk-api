"""add contact_messages and push_subscriptions

Revision ID: c51385d609b6
Revises: 8e5f41b056d7
Create Date: 2026-08-23 15:40:45.723567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c51385d609b6'
down_revision: Union[str, Sequence[str], None] = '8e5f41b056d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.Text(), nullable=False),
        sa.Column('auth', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['public.profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
        schema='public',
    )
    op.create_index(
        'push_subscriptions_user_id_idx', 'push_subscriptions', ['user_id'], unique=False, schema='public'
    )

    op.create_table(
        'contact_messages',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('contact_request_id', sa.UUID(), nullable=False),
        sa.Column('sender_role', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("sender_role in ('candidate','recruiter')", name='contact_messages_sender_role_check'),
        sa.ForeignKeyConstraint(['contact_request_id'], ['public.contact_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        'contact_messages_contact_request_id_idx',
        'contact_messages',
        ['contact_request_id'],
        unique=False,
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('contact_messages_contact_request_id_idx', table_name='contact_messages', schema='public')
    op.drop_table('contact_messages', schema='public')

    op.drop_index('push_subscriptions_user_id_idx', table_name='push_subscriptions', schema='public')
    op.drop_table('push_subscriptions', schema='public')
