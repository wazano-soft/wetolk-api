from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _sqlalchemy_url(url: str) -> str:
    # settings.database_url viene en formato postgresql://... (estilo
    # psycopg2); forzamos el driver psycopg (v3), que es el único instalado.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_sqlalchemy_url(settings.database_url))
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
