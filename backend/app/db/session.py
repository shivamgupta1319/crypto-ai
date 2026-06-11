"""SQLAlchemy engine/session setup (SQLite, no server required)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# check_same_thread=False so the scheduler/background jobs can share the engine.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Bring the schema to head via Alembic migrations (no more raw create_all)."""
    from app import models  # noqa: F401  (side-effect: registers models on Base)
    from app.db.migrate import run_migrations

    run_migrations()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
