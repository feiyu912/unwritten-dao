"""decision-model sample payload

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent_decision")}
    if "sample" not in columns:
        op.add_column("agent_decision", sa.Column("sample", JSONB, nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("agent_decision")}
    if "sample" in columns:
        op.drop_column("agent_decision", "sample")
