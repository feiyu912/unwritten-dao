"""Migration 0002: agent decision audit table.

0001 used ``Base.metadata.create_all`` and already includes the table on a
fresh database; ``checkfirst=True`` keeps this migration safe in both orders.
"""

from __future__ import annotations

from alembic import op
from world_server.models import AgentDecisionRow

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    AgentDecisionRow.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    AgentDecisionRow.__table__.drop(bind=op.get_bind(), checkfirst=True)
