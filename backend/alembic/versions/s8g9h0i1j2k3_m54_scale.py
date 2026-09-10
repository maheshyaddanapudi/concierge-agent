"""M54 — horizontal scale (spec §18.9, PLAN M54).

- `runs.owner_replica` / `runs.cancel_requested_at`: run ownership and
  cancellation as a persisted intent (arch-C3).
- `replicas`: one heartbeat row per live process — liveness, the
  cluster-wide subscriber count (scale-B1), dead-owner reaping.
- `job_clock`: `last_run_at` per periodic job — an interval becomes a
  cluster property instead of a per-process monotonic dict.
- `rate_buckets`: the §18.8 token bucket shared by every replica (scale-H3).
- `tools`: one row per (server, tool name) as a database fact, so N replicas
  ingesting the same server upsert instead of racing (scale-H6).
- `memory_embeddings`: the untyped `embedding` column — which pgvector could
  not index — becomes one typed column per supported dimension, each with
  a real HNSW cosine index (scale-B5, §16.1). Existing vectors whose
  dimension has a column are copied across; the rest are re-embedded by the
  M46 backfill under the active key.

Revision ID: s8g9h0i1j2k3
Revises: r7f8a9b0c1d2
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC, Vector

from alembic import op

revision: str = "s8g9h0i1j2k3"
down_revision: str | None = "r7f8a9b0c1d2"
branch_labels = None
depends_on = None

EMBEDDING_DIMS = (64, 256, 384, 512, 768, 1024, 1536, 3072)
HALFVEC_ABOVE = 2000


def _vtype(dims: int) -> sa.types.TypeEngine[object]:
    return HALFVEC(dims) if dims > HALFVEC_ABOVE else Vector(dims)


def upgrade() -> None:
    # ── run ownership + cancel intent ────────────────────────────
    op.add_column("runs", sa.Column("owner_replica", sa.String(length=128), nullable=True))
    op.add_column(
        "runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
    )

    # ── cluster tables ───────────────────────────────────────────
    op.create_table(
        "replicas",
        sa.Column("replica_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("subscribers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runs_in_flight", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "job_clock",
        sa.Column("job", sa.String(length=64), primary_key=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rate_buckets",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("tokens", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )

    # ── idempotent MCP ingest ────────────────────────────────────
    op.create_index(
        "tools_server_tool_uq",
        "tools",
        ["mcp_server_id", "tool_name"],
        unique=True,
        postgresql_where=sa.text("mcp_server_id IS NOT NULL"),
    )

    # ── typed per-dimension embeddings ───────────────────────────
    for dims in EMBEDDING_DIMS:
        op.add_column("memory_embeddings", sa.Column(f"emb_{dims}", _vtype(dims), nullable=True))
    for dims in EMBEDDING_DIMS:
        target = "halfvec" if dims > HALFVEC_ABOVE else "vector"
        op.execute(
            f"UPDATE memory_embeddings SET emb_{dims} = embedding::{target}({dims}) "  # noqa: S608 — dims are code constants
            f"WHERE vector_dims(embedding) = {dims}"
        )
    op.drop_column("memory_embeddings", "embedding")
    for dims in EMBEDDING_DIMS:
        ops = "halfvec_cosine_ops" if dims > HALFVEC_ABOVE else "vector_cosine_ops"
        op.execute(
            f"CREATE INDEX memory_embeddings_emb_{dims}_hnsw ON memory_embeddings "
            f"USING hnsw (emb_{dims} {ops})"
        )


def downgrade() -> None:
    for dims in EMBEDDING_DIMS:
        op.execute(f"DROP INDEX IF EXISTS memory_embeddings_emb_{dims}_hnsw")
    op.add_column("memory_embeddings", sa.Column("embedding", Vector(None), nullable=True))
    for dims in EMBEDDING_DIMS:
        if dims <= HALFVEC_ABOVE:
            op.execute(
                f"UPDATE memory_embeddings SET embedding = emb_{dims} "  # noqa: S608 — dims are code constants
                f"WHERE emb_{dims} IS NOT NULL"
            )
    for dims in EMBEDDING_DIMS:
        op.drop_column("memory_embeddings", f"emb_{dims}")
    op.drop_index("tools_server_tool_uq", table_name="tools")
    op.drop_table("rate_buckets")
    op.drop_table("job_clock")
    op.drop_table("replicas")
    op.drop_column("runs", "cancel_requested_at")
    op.drop_column("runs", "owner_replica")
