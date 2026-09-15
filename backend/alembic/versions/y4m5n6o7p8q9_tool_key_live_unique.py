"""tool_key is unique among live rows only

A soft-deleted tool used to keep its `tool_key` reserved forever, because
`ix_tools_tool_key` was unconditional. Deleting an MCP server and registering
it again under the same name therefore found `{server}.{tool}` taken by a
tombstone that no API or page will show, fell through to the collision
suffix, and wrote `sitefiles.echo-88501d` — a key the operator never chose
and cannot get back. Spec §4 gives that suffix one job, keeping two SERVERS
that expose the same tool name apart, and §14 step 2 promises plain
`{server}.{tool}` keys.

The index becomes partial on `deleted_at IS NULL`. Live rows are still
unique; tombstones stop reserving anything.

Backfill: rows whose key was suffixed by the old behaviour are NOT rewritten.
`tool_key` is editable and operator-facing, a skill's `{tool:…}` mentions are
matched against it, and a migration cannot know whether a given suffix was
this bug or a genuine cross-server collision that is still live. Renaming one
is a safe operator action in the UI; guessing on their behalf is not.

Revision ID: y4m5n6o7p8q9
Revises: x3l4m5n6o7p8
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "y4m5n6o7p8q9"
down_revision: str | None = "x3l4m5n6o7p8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_tools_tool_key", table_name="tools")
    op.create_index(
        "ix_tools_tool_key",
        "tools",
        ["tool_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Going back to an unconditional unique index can fail, and that is
    # honest: once keys have been reused, two rows legitimately share one
    # `tool_key` with only one of them live. The operator resolves the
    # duplicate — dropping tombstones or renaming — before downgrading.
    op.drop_index("ix_tools_tool_key", table_name="tools")
    op.create_index("ix_tools_tool_key", "tools", ["tool_key"], unique=True)
