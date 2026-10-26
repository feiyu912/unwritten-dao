"""initial world schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text
from world_server.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
