"""Alembic environment — uses the app's metadata + DB URL from app.config."""
from __future__ import annotations

from alembic import context

# Importing models registers all tables on Base.metadata (needed for autogenerate).
import app.models  # noqa: F401,E402
from app.config import settings
from app.db.session import Base, engine

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-friendly ALTERs
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-friendly ALTERs
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
