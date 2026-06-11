"""adaptive intelligence tables

Adds ``training_samples`` (meta-labeling feature store) and ``agent_proposals``
(the agent's human-approval queue) for N10.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001's create_all covers these on a fresh DB; guard so we only build them
    # for DBs stamped at an earlier revision.
    insp = sa.inspect(op.get_bind())

    if not insp.has_table("training_samples"):
        op.create_table(
            "training_samples",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("timeframe", sa.String(length=8), nullable=False),
            sa.Column("strategy", sa.String(length=40), nullable=False),
            sa.Column("direction", sa.Integer(), nullable=False),
            sa.Column("regime", sa.String(length=20), nullable=True),
            sa.Column("features_json", sa.String(), nullable=True),
            sa.Column("label", sa.Integer(), nullable=False),
            sa.Column("realized_r", sa.Float(), nullable=True),
            sa.Column("bars_held", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=10), nullable=True),
            sa.Column("bar_time", sa.Integer(), nullable=False),
            sa.UniqueConstraint("symbol", "timeframe", "strategy", "bar_time", "source",
                                name="uq_training_sample"),
        )

    if not insp.has_table("agent_proposals"):
        op.create_table(
            "agent_proposals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("rationale", sa.String(), nullable=True),
            sa.Column("payload_json", sa.String(), nullable=True),
            sa.Column("prev_json", sa.String(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=12), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("agent_proposals")
    op.drop_table("training_samples")
