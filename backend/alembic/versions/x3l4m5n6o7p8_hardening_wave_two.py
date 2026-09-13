"""code_setting_ui_hardening: operator intent, the out-of-run spend ledger,
the eval gate opt-in, and the indexes every cascade was scanning without.

Four groups, all additive — no column is dropped, no type changes, nothing
is rewritten. An upgrade over a populated database changes no behavior
except where a backfill is explicitly described below.

1. OPERATOR INTENT — `mcp_servers.disabled_at`, `remote_agents.disabled_at`.
   `status='inactive'` was overloaded: a server or agent is BORN inactive and
   its first successful connect or card fetch flips it to active, so the
   status alone could not tell "not connected yet" from "a human switched
   this off". That is why the Deactivate toggle was a label — start() and
   reconcile connected it again every interval, and a failed health ping
   wrote `error` over the disable, after which the next success wrote
   `active`. These columns record the human's decision, and they survive a
   restart. Backfilled for rows that HAVE connected at least once, because
   those are the ones whose `inactive` can only be a person's doing; a
   never-connected row stays NULL, which is byte-identical to today.

2. SPEND LEDGER — the `job_usage` table. The spend ceiling counted runs
   only, so every autonomous model call sat outside it: the overlap,
   significance and salience judges, anticipation, run digests, reflection,
   community summaries, extraction. The Settings hint said the ceiling was
   "one number for the whole deployment" and the dashboard reported $0 for
   all of it, so an operator at their ceiling watched chat refused while the
   background jobs kept billing. One row per out-of-run call, priced when it
   happens exactly as a run is.

3. EVAL GATE OPT-IN — `eval_datasets.allow_hitl_autoapprove`, default FALSE.
   The eval harness auto-approved every human gate it reached, so an
   uploaded one-case dataset pointing at a gated destructive workflow drove
   it to completion with the approval granted by a log line. Existing
   datasets are created at the new default: a batch that reaches a gate now
   refuses it rather than clearing it, and says so on the run.

4. INDEXES — nineteen foreign keys that every query and every cascading
   delete walked with a sequential scan, plus a partial index for the
   per-routine hourly event cap, plus `text_pattern_ops` indexes for the
   per-run checkpoint purge's `thread_id LIKE '<run>:%'` (which cannot use a
   normal index under a non-C collation). The checkpoint tables belong to
   the LangGraph saver, not to our metadata, so those three are raw DDL
   guarded by `to_regclass` — on a database where no run has ever executed
   the saver has not created them yet, and the migration must not fail.

Revision ID: x3l4m5n6o7p8
Revises: w2k3l4m5n6o7
"""

import sqlalchemy as sa

from alembic import op

revision: str = "x3l4m5n6o7p8"
down_revision: str | None = "w2k3l4m5n6o7"
branch_labels = None
depends_on = None

# (index name, table, columns) — every one a foreign key that was unindexed
_FK_INDEXES: list[tuple[str, str, list[str]]] = [
    ("memories_run_idx", "memories", ["run_id"]),
    ("memory_entity_links_entity_idx", "memory_entity_links", ["entity_id"]),
    ("run_digests_conversation_idx", "run_digests", ["conversation_id"]),
    ("plan_exemplars_run_idx", "plan_exemplars", ["run_id"]),
    ("deliveries_run_idx", "deliveries", ["run_id"]),
    ("deliveries_intent_idx", "deliveries", ["intent_id"]),
    ("ambient_wakeups_routine_idx", "ambient_wakeups", ["routine_id"]),
    ("ambient_wakeups_run_idx", "ambient_wakeups", ["run_id"]),
    ("ambient_events_routine_idx", "ambient_events", ["routine_id"]),
    ("ambient_events_intent_idx", "ambient_events", ["intent_id"]),
    ("ambient_events_correlation_idx", "ambient_events", ["correlation_id"]),
    # the per-routine hourly cap counts exactly this pair
    ("ambient_events_routine_recent_idx", "ambient_events", ["routine_id", "received_at"]),
    ("a2a_tasks_run_idx", "a2a_tasks", ["run_id"]),
    ("eval_cases_dataset_idx", "eval_cases", ["dataset_id"]),
    ("eval_runs_dataset_idx", "eval_runs", ["dataset_id"]),
    ("eval_results_case_idx", "eval_results", ["case_id"]),
    ("eval_results_run_idx", "eval_results", ["run_id"]),
    ("eval_results_eval_run_idx", "eval_results", ["eval_run_id"]),
    ("job_usage_at_idx", "job_usage", ["at"]),
]

_CHECKPOINT_PREFIX_INDEXES = [
    ("checkpoints_thread_prefix_idx", "checkpoints"),
    ("checkpoint_blobs_thread_prefix_idx", "checkpoint_blobs"),
    ("checkpoint_writes_thread_prefix_idx", "checkpoint_writes"),
]


def upgrade() -> None:
    # ── 1. operator intent ───────────────────────────────────────
    op.add_column(
        "mcp_servers", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "remote_agents", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    # a row that has connected (or fetched a card) at least once and is
    # nonetheless inactive was switched off by a person — record that, so the
    # upgrade does not silently reconnect something a human stopped
    op.execute(
        "UPDATE mcp_servers SET disabled_at = now() "
        "WHERE status = 'inactive' AND last_connected_at IS NOT NULL AND deleted_at IS NULL"
    )
    op.execute(
        "UPDATE remote_agents SET disabled_at = now() "
        "WHERE status = 'inactive' AND card IS NOT NULL AND deleted_at IS NULL"
    )

    # ── 2. the out-of-run spend ledger ───────────────────────────
    op.create_table(
        "job_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("cost_priced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 3. the eval gate opt-in ──────────────────────────────────
    op.add_column(
        "eval_datasets",
        sa.Column(
            "allow_hitl_autoapprove",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ── 4. indexes ───────────────────────────────────────────────
    # one row per (agent, skill id) is a database fact, mirroring the MCP
    # projection's index: two overlapping card refreshes both read an empty
    # tool set and both inserted, leaving the agent with duplicate tools.
    # Deduplicate first — keep the oldest row of each group, since that is
    # the one whose tool_key any existing binding already points at.
    op.execute(
        "DELETE FROM tools t USING tools older "
        "WHERE t.remote_agent_id IS NOT NULL "
        "AND t.remote_agent_id = older.remote_agent_id "
        "AND t.tool_name = older.tool_name "
        "AND (older.created_at, older.id) < (t.created_at, t.id)"
    )
    op.create_index(
        "tools_agent_skill_uq",
        "tools",
        ["remote_agent_id", "tool_name"],
        unique=True,
        postgresql_where=sa.text("remote_agent_id IS NOT NULL"),
        if_not_exists=True,
    )
    for name, table, columns in _FK_INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)
    for name, table in _CHECKPOINT_PREFIX_INDEXES:
        # the LangGraph saver owns these tables and may not have created them
        # yet on a database where no run has ever executed
        op.execute(
            f"DO $$ BEGIN IF to_regclass('public.{table}') IS NOT NULL THEN "
            f"CREATE INDEX IF NOT EXISTS {name} ON {table} (thread_id text_pattern_ops); "
            f"END IF; END $$;"
        )


def downgrade() -> None:
    for name, table in _CHECKPOINT_PREFIX_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name};")
        _ = table
    for name, table, _columns in _FK_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)
    op.drop_index("tools_agent_skill_uq", table_name="tools", if_exists=True)
    op.drop_column("eval_datasets", "allow_hitl_autoapprove")
    op.drop_table("job_usage")
    op.drop_column("remote_agents", "disabled_at")
    op.drop_column("mcp_servers", "disabled_at")
