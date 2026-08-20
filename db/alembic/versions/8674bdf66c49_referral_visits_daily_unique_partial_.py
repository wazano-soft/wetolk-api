"""referral_visits_daily_unique: make it a partial index (is_valid only)

Bug found in code review: the plain unique index on
(candidate_id, visitor_hash, visit_date) deduped ALL visits, not just
valid ones. An early invalid visit (bounce < 10s) occupied the key for
the day, so a genuinely valid visit from the same visitor later that
day hit the same IntegrityError the app treats as "already counted" --
silently losing that referral credit. Scoping the index to
WHERE is_valid fixes it: invalid visits no longer collide with anything.

Revision ID: 8674bdf66c49
Revises: 91023de81a19
Create Date: 2026-08-19 18:35:17.492058

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8674bdf66c49'
down_revision: Union[str, Sequence[str], None] = '91023de81a19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("drop index public.referral_visits_daily_unique")
    op.execute(
        "create unique index referral_visits_daily_unique "
        "on public.referral_visits (candidate_id, visitor_hash, visit_date) "
        "where is_valid"
    )


def downgrade() -> None:
    op.execute("drop index public.referral_visits_daily_unique")
    op.execute(
        "create unique index referral_visits_daily_unique "
        "on public.referral_visits (candidate_id, visitor_hash, visit_date)"
    )
