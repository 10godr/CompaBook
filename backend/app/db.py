from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    # Todas las fechas son timestamptz en UTC (diseno-tecnico.md §3).
    type_annotation_map = {datetime: DateTime(timezone=True)}


class DatabaseNotConfigured(RuntimeError):
    pass


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if not url:
        raise DatabaseNotConfigured("DATABASE_URL no está definida")
    # El pooler de Supabase en modo transacción no admite prepared statements, y cada
    # invocación serverless abre y cierra su conexión, así que no hay pool propio.
    return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})


def get_db() -> Iterator[Session]:
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
