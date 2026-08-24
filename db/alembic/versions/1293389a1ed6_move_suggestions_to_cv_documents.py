"""move suggestions to cv_documents

Revision ID: 1293389a1ed6
Revises: 8ec0f1c21f2a
Create Date: 2026-08-23 00:00:00.000000

Las suggestions son dato de un CV puntual (ya viven dentro de
cv_documents.extracted como parte del JSON completo) -- se saca la columna
denormalizada de candidates y se agrega una propia en cv_documents, para
no perder la referencia a qué CV corresponden cuando haya más de uno.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1293389a1ed6'
down_revision: Union[str, Sequence[str], None] = '8ec0f1c21f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cv_documents',
        sa.Column(
            'suggestions',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
        schema='public',
    )
    # Backfill desde candidates.suggestions hacia el CVDocument vigente de
    # cada candidato -- si no se hace esto, cualquier suggestion ya
    # calculada se pierde para el usuario hasta que resuba el CV.
    op.execute(
        """
        UPDATE public.cv_documents AS d
        SET suggestions = c.suggestions
        FROM public.candidates AS c
        WHERE d.candidate_id = c.id
          AND d.is_current = true
          AND c.suggestions IS NOT NULL
        """
    )
    op.drop_column('candidates', 'suggestions', schema='public')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'candidates',
        sa.Column(
            'suggestions',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=True,
        ),
        schema='public',
    )
    op.execute(
        """
        UPDATE public.candidates AS c
        SET suggestions = d.suggestions
        FROM public.cv_documents AS d
        WHERE d.candidate_id = c.id
          AND d.is_current = true
          AND d.suggestions IS NOT NULL
        """
    )
    op.drop_column('cv_documents', 'suggestions', schema='public')
