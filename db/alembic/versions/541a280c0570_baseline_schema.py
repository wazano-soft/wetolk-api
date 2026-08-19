"""baseline schema

Migración de arranque: ejecuta el schema inicial completo desde
db/0001_init.sql (tablas, índices HNSW, RLS, vista pública, trigger
de RF-01, función match_cv_chunks) — todo lo que autogenerate de
Alembic no puede derivar de los modelos ORM en app/models.py.

Los tres entornos (local, dev-Supabase, prod-Supabase) ya tenían este
schema aplicado antes de adoptar Alembic; se estampan en esta revisión
con `alembic stamp` en vez de volver a correrla. De acá en adelante,
todo cambio de schema es una migración nueva generada con
`alembic revision --autogenerate`.

Revision ID: 541a280c0570
Revises:
Create Date: 2026-08-19 14:01:45.230855

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '541a280c0570'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQL_FILE = Path(__file__).resolve().parents[2] / "0001_init.sql"


def upgrade() -> None:
    op.execute(_SQL_FILE.read_text())


def downgrade() -> None:
    raise NotImplementedError(
        "No hay downgrade para el baseline -- restaurar desde un backup si hace falta."
    )
