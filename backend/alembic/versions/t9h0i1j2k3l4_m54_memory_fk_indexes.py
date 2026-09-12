"""M54 (spec §18.9): index the self-referencing foreign keys on memories.

`supersedes` and `superseded_by` reference `memories.id`; without an index
on each, deleting a memory makes Postgres scan the whole table for rows
that point at it — the §14q-95 drill's cleanup of a million rows stalled
for minutes on exactly that. Erase (§16.1) and any bulk delete pay the
same cost; two btree indexes make the referential check a lookup.

Revision ID: t9h0i1j2k3l4
Revises: s8g9h0i1j2k3
"""

from __future__ import annotations

from alembic import op

revision: str = "t9h0i1j2k3l4"
down_revision: str | None = "s8g9h0i1j2k3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("memories_supersedes_idx", "memories", ["supersedes"], if_not_exists=True)
    op.create_index("memories_superseded_by_idx", "memories", ["superseded_by"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("memories_superseded_by_idx", table_name="memories")
    op.drop_index("memories_supersedes_idx", table_name="memories")
