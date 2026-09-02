"""tools.ingest_state (PLAN M53 — re-ingest preserves operator intent)

Before M53 every MCP tools/list ingest set status='active' and cleared
deleted_at on every row the server still offered, resurrecting tools an
operator had disabled or deleted. `ingest_state` records whether the
SERVER last offered the tool ('present') or dropped it ('missing'), so a
reappearance reactivates only what the server's absence deactivated.

Revision ID: r7f8a9b0c1d2
Revises: q6e7f8a9b0c1
"""

import sqlalchemy as sa

from alembic import op

revision: str = "r7f8a9b0c1d2"
down_revision: str | None = "q6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("ingest_state", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("tools", "ingest_state")
