"""widen quick_questions question max length

Revision ID: 261d4812b656
Revises: c51385d609b6
Create Date: 2026-08-23 22:25:31.295354

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '261d4812b656'
down_revision: Union[str, Sequence[str], None] = 'c51385d609b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "quick_questions_question_check", "quick_questions", schema="public", type_="check"
    )
    op.create_check_constraint(
        "quick_questions_question_check",
        "quick_questions",
        "char_length(question) <= 150",
        schema="public",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "quick_questions_question_check", "quick_questions", schema="public", type_="check"
    )
    op.create_check_constraint(
        "quick_questions_question_check",
        "quick_questions",
        "char_length(question) <= 80",
        schema="public",
    )
