"""add recruiter_waitlist_signups

Revision ID: 2fc06ca962aa
Revises: 2757dcc6a3d3
Create Date: 2026-08-27 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2fc06ca962aa'
down_revision: Union[str, Sequence[str], None] = '2757dcc6a3d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'recruiter_waitlist_signups',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='recruiter_waitlist_signups_pkey'),
        sa.UniqueConstraint('email', name='recruiter_waitlist_signups_email_key'),
        schema='public',
    )
    # Mismo criterio que las demás tablas nuevas de este batch (ver
    # 47c0ac659137) -- nadie la consulta vía la API REST de Supabase, RLS
    # sin policies la deja en deny-all para anon/authenticated.
    op.execute('ALTER TABLE public.recruiter_waitlist_signups ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('recruiter_waitlist_signups', schema='public')
