"""add procrastinate schema

Revision ID: 8ec0f1c21f2a
Revises: 6c0e1c9b7a2f
Create Date: 2026-08-22 00:20:00.000000

Aplica el esquema de tablas/funciones de Procrastinate (cola de background
tasks con reintentos, persistida en este mismo Postgres -- sin Redis ni
infra nueva). Se lee directo del paquete instalado (procrastinate==3.9.0,
pineado en requirements.txt) en vez de copiar el SQL a mano, para no
arrastrar errores de transcripción de un archivo de ~600 líneas.

Si en el futuro se sube la versión de procrastinate y esa versión trae
cambios de schema, va a hacer falta una migración nueva con el diff --
procrastinate no expone un export automático de "solo lo que cambió"
hacia Alembic, revisar su CHANGELOG en ese momento.
"""
import importlib.resources
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8ec0f1c21f2a'
down_revision: Union[str, Sequence[str], None] = '6c0e1c9b7a2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROCRASTINATE_FUNCTIONS = [
    "procrastinate_defer_jobs_v1",
    "procrastinate_defer_periodic_job_v2",
    "procrastinate_fetch_job_v2",
    "procrastinate_finish_job_v1",
    "procrastinate_cancel_job_v1",
    "procrastinate_retry_job_v1",
    "procrastinate_retry_job_v2",
    "procrastinate_notify_queue_job_inserted_v1",
    "procrastinate_notify_queue_abort_job_v1",
    "procrastinate_trigger_function_status_events_insert_v1",
    "procrastinate_trigger_function_status_events_update_v1",
    "procrastinate_trigger_function_scheduled_events_v1",
    "procrastinate_trigger_abort_requested_events_procedure_v1",
    "procrastinate_unlink_periodic_defers_v1",
    "procrastinate_register_worker_v1",
    "procrastinate_unregister_worker_v1",
    "procrastinate_update_heartbeat_v1",
    "procrastinate_prune_stalled_workers_v1",
]


def upgrade() -> None:
    """Upgrade schema."""
    schema_sql = importlib.resources.files("procrastinate.sql").joinpath("schema.sql").read_text()
    op.execute(schema_sql)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, "
        "procrastinate_jobs, procrastinate_workers CASCADE"
    )
    for fn in _PROCRASTINATE_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {fn} CASCADE")
    op.execute(
        "DROP TYPE IF EXISTS procrastinate_job_status, procrastinate_job_event_type, "
        "procrastinate_job_to_defer_v1 CASCADE"
    )
