"""hardening wave: every mutable input to a run is fingerprinted and pinned

- tools.description_hash / description_source — a tool's description is
  what the planner routes by; a re-ingest that rewords it is now versioned
  and logged, and an operator's edit ('operator') survives re-ingests
- skills / sub_agents.definition_hash / definition_version — the version of
  a definition, bumped only when definition fields change (a status toggle
  is not a new definition); overlap_audited_hash is the last definition the
  registry overlap audit judged
- remote_agents.card_hash / card_version — an A2A card that changes
  under a refresh is versioned and logged
- mcp_servers.config_hash — a connection config edit is a new binary
  behind the same rows; logged and reconnected at once
- run_steps.entity_name / model_params — the name and the model params a
  step ran with, on the row (not only in the log labels)
- runs.cost_usd / cost_priced / price_snapshot — the cost stamped at
  finish with the prices used, so a later price change never rewrites
  history
- deliveries.policy_id — which policy row set a delivery's tier
- skills.origin — who authored a definition ('human' | 'mined'): the §16.5
  activation guard keys off it, not off an editable description prefix
- every existing tool description is fingerprinted at upgrade time, so the
  first post-upgrade ingest judges a change rather than adopting it

Revision ID: v1j2k3l4m5n6
Revises: u0i1j2k3l4m5
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "v1j2k3l4m5n6"
down_revision: str | None = "u0i1j2k3l4m5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("description_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "tools",
        sa.Column(
            "description_source", sa.String(length=16), nullable=False, server_default="server"
        ),
    )
    # the fingerprint of every description as it is at upgrade time (the
    # same sha256 over the stripped UTF-8 text `apply_description` uses),
    # so the first post-upgrade ingest judges a change instead of adopting
    # whatever the server says now as a first sighting
    op.execute(
        "UPDATE tools SET description_hash = encode(sha256(convert_to(btrim(description), "
        "'UTF8')), 'hex') WHERE description IS NOT NULL"
    )
    for table in ("skills", "sub_agents"):
        op.add_column(table, sa.Column("definition_hash", sa.String(length=64), nullable=True))
        op.add_column(
            table,
            sa.Column("definition_version", sa.Integer(), nullable=False, server_default="1"),
        )
        op.add_column(table, sa.Column("overlap_audited_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "skills",
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="human"),
    )
    op.add_column("remote_agents", sa.Column("card_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "remote_agents",
        sa.Column("card_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("mcp_servers", sa.Column("config_hash", sa.String(length=64), nullable=True))
    op.add_column("run_steps", sa.Column("entity_name", sa.String(length=255), nullable=True))
    op.add_column(
        "run_steps",
        sa.Column("model_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("runs", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("cost_priced", sa.Boolean(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("price_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("deliveries", sa.Column("policy_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "policy_id")
    op.drop_column("runs", "price_snapshot")
    op.drop_column("runs", "cost_priced")
    op.drop_column("runs", "cost_usd")
    op.drop_column("run_steps", "model_params")
    op.drop_column("run_steps", "entity_name")
    op.drop_column("mcp_servers", "config_hash")
    op.drop_column("remote_agents", "card_version")
    op.drop_column("remote_agents", "card_hash")
    op.drop_column("skills", "origin")
    for table in ("sub_agents", "skills"):
        op.drop_column(table, "overlap_audited_hash")
        op.drop_column(table, "definition_version")
        op.drop_column(table, "definition_hash")
    op.drop_column("tools", "description_source")
    op.drop_column("tools", "description_hash")
