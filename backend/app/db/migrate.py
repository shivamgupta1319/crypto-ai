"""Run Alembic migrations programmatically at app startup.

Handles three cases cleanly:
- fresh DB (no tables)          → upgrade to head (creates everything).
- legacy DB (tables, no alembic)→ stamp the *baseline*, then upgrade to head so
                                  later revisions still create any tables the old
                                  create_all DB never had (idempotent guards).
- migrated DB                   → upgrade to head (apply any new revisions).
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import settings
from app.db.session import engine

logger = logging.getLogger("cryptoai.migrate")

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
MIGRATIONS_DIR = BACKEND_DIR / "migrations"
BASELINE_REVISION = "0001"  # the create_all baseline; later revisions add tables


def _config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def run_migrations() -> None:
    cfg = _config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "candles" in tables:
        # Legacy DB built by create_all — adopt the baseline (don't recreate the
        # original tables), then upgrade so later revisions add any tables the old
        # DB predates (settings, training_samples, agent_proposals). Those upgrades
        # are guarded by has_table() checks, so this is safe whatever the DB has.
        logger.info("legacy DB detected; stamping baseline then upgrading to head")
        command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
    else:
        command.upgrade(cfg, "head")

    # Safety net: reconcile any model tables that are physically missing despite
    # the recorded revision. This rescues DBs stamped to head by an earlier build
    # *before* a table's migration existed (create_all only creates missing tables,
    # never altering or dropping existing ones).
    import app.models  # noqa: F401  (register all tables on Base.metadata)
    from app.db.session import Base

    expected = set(Base.metadata.tables)
    present = set(inspect(engine).get_table_names())
    missing = expected - present
    if missing:
        logger.warning("reconciling missing tables not created by migrations: %s", sorted(missing))
        Base.metadata.create_all(bind=engine)
