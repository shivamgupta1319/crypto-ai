"""Run Alembic migrations programmatically at app startup.

Handles three cases cleanly:
- fresh DB (no tables)          → upgrade to head (creates everything).
- legacy DB (tables, no alembic)→ stamp head (adopt baseline, don't recreate).
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


def _config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def run_migrations() -> None:
    cfg = _config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "candles" in tables:
        # Legacy DB built by create_all — adopt the baseline without recreating.
        logger.info("legacy DB detected; stamping baseline revision")
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")
