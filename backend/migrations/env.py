from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db import Base

target_metadata = Base.metadata


def get_url() -> str:
    # Alembic usa la conexión directa (5432), no el pooler de la app.
    settings = get_settings()
    url = settings.database_url_direct or settings.database_url
    if not url:
        raise RuntimeError("Define DATABASE_URL_DIRECT en backend/.env")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
