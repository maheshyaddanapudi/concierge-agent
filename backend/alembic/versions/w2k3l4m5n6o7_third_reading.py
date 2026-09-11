"""third reading: two backfills the hardening-wave migration left out

- skills.origin — a proposal mined BEFORE definitions carried an origin was
  tagged only by the proposal prefix in its description; the §16.5
  activation guard keys off `origin`, so those rows were activatable
  unjudged after the upgrade. Stamped 'mined' by the prefix they carry.
- tools.description_hash — the upgrade-time fingerprint trimmed spaces only
  (Postgres `btrim` default) where `apply_description` strips every
  whitespace character, so a description ending in a newline was flagged as
  drifted on the first post-upgrade ingest. Re-stamped for server-sourced
  rows with the same trim the code uses.

Revision ID: w2k3l4m5n6o7
Revises: v1j2k3l4m5n6
"""

from alembic import op

revision: str = "w2k3l4m5n6o7"
down_revision: str | None = "v1j2k3l4m5n6"
branch_labels = None
depends_on = None

PROPOSAL_PREFIX = "[proposed from fallback mining] "


def upgrade() -> None:
    # (`[` is not a LIKE metacharacter in PostgreSQL — only `%` and `_` are)
    op.execute(
        "UPDATE skills SET origin = 'mined' WHERE origin = 'human' "
        f"AND description LIKE '{PROPOSAL_PREFIX}%'"
    )
    op.execute(
        "UPDATE tools SET description_hash = encode(sha256(convert_to("
        "btrim(description, E' \\t\\n\\r\\x0b\\x0c'), 'UTF8')), 'hex') "
        "WHERE description IS NOT NULL AND description_source = 'server'"
    )


def downgrade() -> None:
    # data-only: the stamps are what the hardening-wave migration meant to
    # write; nothing to undo
    pass
