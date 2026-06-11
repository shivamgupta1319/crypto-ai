"""initial baseline schema

Creates all current tables (candles, active_strategies, signals, paper_trades,
backtest_runs) from the app models. Subsequent schema changes get their own
revisions (hand-written or `alembic revision --autogenerate`).

Revision ID: 0001
Revises:
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.db.session import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
