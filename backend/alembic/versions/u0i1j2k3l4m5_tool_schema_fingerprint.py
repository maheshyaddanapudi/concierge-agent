"""tool schema fingerprint and the entity version on run steps

A tool's `input_schema` used to be overwritten silently on every MCP
re-ingest: a server renaming a parameter left no trace, no version and no
signal. `schema_hash` is the content hash of the schema as last written,
`schema_version` counts its changes (1 at first sighting), and
`schema_changed_at` marks a change the operator has not acknowledged yet.
`run_steps.entity_version` / `entity_hash` pin the version a step ran
against into the run record, so a trace reads against the registry as it
was. Existing rows keep NULL hashes: the next ingest records the hash as a
first sighting rather than flagging every tool as changed.

Revision ID: u0i1j2k3l4m5
Revises: t9h0i1j2k3l4
"""

import sqlalchemy as sa

from alembic import op

revision: str = "u0i1j2k3l4m5"
down_revision: str | None = "t9h0i1j2k3l4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("schema_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "tools",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tools", sa.Column("schema_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("run_steps", sa.Column("entity_version", sa.Integer(), nullable=True))
    op.add_column("run_steps", sa.Column("entity_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("run_steps", "entity_hash")
    op.drop_column("run_steps", "entity_version")
    op.drop_column("tools", "schema_changed_at")
    op.drop_column("tools", "schema_version")
    op.drop_column("tools", "schema_hash")
