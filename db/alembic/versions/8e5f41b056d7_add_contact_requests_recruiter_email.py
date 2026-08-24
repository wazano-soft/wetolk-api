"""add contact_requests.recruiter_email

Revision ID: 8e5f41b056d7
Revises: 5da797309f6c
Create Date: 2026-08-23 00:00:00.000000

Snapshot denormalizado del email del reclutador al momento del contacto
(tomado del JWT, AuthUser.email) -- no hay columna de email alcanzable
por SQLAlchemy, auth.users de Supabase no está mapeado acá.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8e5f41b056d7'
down_revision: Union[str, Sequence[str], None] = '5da797309f6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'contact_requests',
        sa.Column('recruiter_email', sa.Text(), nullable=True),
        schema='public',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contact_requests', 'recruiter_email', schema='public')
