from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def sqlalchemy_url(url: str) -> str:
    # settings.database_url viene en formato postgresql://... (estilo
    # psycopg2); forzamos el driver psycopg (v3), que es el único instalado.
    # Reutilizada por db/alembic/env.py -- una sola implementación del
    # rewrite de driver para la app y las migraciones.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(
    sqlalchemy_url(settings.database_url),
    # El pooler de Supabase en modo Transaction (puerto 6543) reasigna la
    # conexión física de Postgres entre statements de una misma sesión --
    # los prepared statements de psycopg quedan atados a esa conexión y
    # colisionan (DuplicatePreparedStatement) apenas se reusa el pool.
    connect_args={"prepare_threshold": None},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
