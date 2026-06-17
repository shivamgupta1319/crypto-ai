"""portfolio equity snapshots

Adds ``portfolio_snapshots`` — a per-cycle point-in-time record of the paper
account (realized balance + unrealized P&L = equity) so the equity time-series
is persisted and auditable rather than re-derived from closed trades only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001's create_all covers this on a fresh DB; guard so we only build it for
    # DBs stamped at an earlier revision.
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("portfolio_snapshots"):
        op.create_table(
            "portfolio_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("realized_balance", sa.Float(), nullable=False),
            sa.Column("unrealized_pnl", sa.Float(), nullable=True),
            sa.Column("equity", sa.Float(), nullable=False),
            sa.Column("open_positions", sa.Integer(), nullable=True),
            sa.Column("kill_switch", sa.Integer(), nullable=True),
        )
        op.create_index("ix_snapshot_time", "portfolio_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_snapshot_time", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
