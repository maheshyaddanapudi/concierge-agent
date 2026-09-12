"""Hot-path indexes (PLAN M50 — arch-C2 / code-H1)

The M49 baseline measured /runs and /conversations scaling with the table
(10× rows → ~7× latency) over 23 migrations that never indexed the run
tables' foreign keys or the columns every list orders and filters by.

Revision ID: q6e7f8a9b0c1
Revises: p5d6e7f8a9b0
"""

from alembic import op

revision: str = "q6e7f8a9b0c1"
down_revision: str | None = "p5d6e7f8a9b0"
branch_labels = None
depends_on = None

INDEXES = (
    ("runs_conversation_idx", "runs", "conversation_id"),
    ("runs_status_idx", "runs", "status"),
    ("runs_started_at_idx", "runs", "started_at"),
    ("run_steps_run_idx", "run_steps", "run_id"),
    ("tools_mcp_server_idx", "tools", "mcp_server_id"),
)


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.create_index(name, table, [column], if_not_exists=True)


def downgrade() -> None:
    for name, table, _column in INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
