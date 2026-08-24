"""regenerate short slugs for candidates

Revision ID: 5da797309f6c
Revises: 1293389a1ed6
Create Date: 2026-08-23 00:00:00.000000

Los slugs viejos exponían el nombre del candidato en la URL pública
(`nombre-apellido-xxxx`). Se reemplazan por un identificador opaco de 10
caracteres alfanuméricos -- mismo formato que ahora genera
`_generate_slug()` en app/api/cv.py, ver esa función para el detalle.
"""
import secrets
import string
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

# revision identifiers, used by Alembic.
revision: str = '5da797309f6c'
down_revision: Union[str, Sequence[str], None] = '1293389a1ed6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUG_ALPHABET = string.ascii_lowercase + string.digits


def _generate_slug() -> str:
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(10))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    candidate_ids = [
        row[0] for row in bind.execute(sa.text("SELECT id FROM public.candidates")).fetchall()
    ]
    for candidate_id in candidate_ids:
        # Colisión a 10 chars sobre un alfabeto de 36 es prácticamente
        # imposible (36^10 combinaciones), pero se reintenta igual con un
        # SAVEPOINT por fila en vez de asumir que nunca va a pasar.
        for _attempt in range(5):
            slug = _generate_slug()
            savepoint = bind.begin_nested()
            try:
                bind.execute(
                    sa.text("UPDATE public.candidates SET slug = :slug WHERE id = :id"),
                    {"slug": slug, "id": candidate_id},
                )
                savepoint.commit()
                break
            except IntegrityError:
                savepoint.rollback()
        else:
            raise RuntimeError(
                f"No se pudo generar un slug único para candidate_id={candidate_id} "
                "tras varios intentos"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Los slugs viejos (con el nombre del candidato) no quedan preservados
    # en ningún lado antes de este upgrade -- no hay forma de recuperarlos.
    # Aceptado: etapa temprana del producto, pocos usuarios, no hace falta
    # preservar links viejos.
    pass
