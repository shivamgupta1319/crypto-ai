"""runtime settings table

Adds the key-value ``settings`` table used by the Settings page (N9) to override
config.py defaults at runtime.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The 0001 baseline runs create_all() over the *current* models, so on a fresh
    # DB this table already exists. This migration only materializes it for DBs
    # stamped at 0001 before the table was added — hence the existence guard.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("settings"):
        return
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value_json", sa.String(), nullable=False, server_default="null"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("settings")
