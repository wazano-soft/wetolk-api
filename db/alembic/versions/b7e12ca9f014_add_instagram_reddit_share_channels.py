"""add instagram/reddit to shares.channel check

Revision ID: b7e12ca9f014
Revises: a4f2e9c17b83
Create Date: 2026-08-27 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e12ca9f014'
down_revision: Union[str, Sequence[str], None] = 'a4f2e9c17b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("shares_channel_check", "shares", schema="public", type_="check")
    op.create_check_constraint(
        "shares_channel_check",
        "shares",
        "channel in ('linkedin','x','whatsapp','facebook','instagram','reddit','copy','other')",
        schema="public",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("shares_channel_check", "shares", schema="public", type_="check")
    op.create_check_constraint(
        "shares_channel_check",
        "shares",
        "channel in ('linkedin','x','whatsapp','facebook','copy','other')",
        schema="public",
    )
