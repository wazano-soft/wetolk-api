"""make contact_requests.recruiter_id nullable (anonymous contact)

Revision ID: 784a571991f9
Revises: 5fd162970924
Create Date: 2026-08-27 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '784a571991f9'
down_revision: Union[str, Sequence[str], None] = '5fd162970924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('ALTER TABLE public.contact_requests ALTER COLUMN recruiter_id DROP NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    # Reponer NOT NULL requeriría decidir qué hacer con las filas anónimas
    # (recruiter_id NULL) que hayan quedado -- no se intenta acá.
    op.execute(
        'ALTER TABLE public.contact_requests ALTER COLUMN recruiter_id SET NOT NULL'
    )
