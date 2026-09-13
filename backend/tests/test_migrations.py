"""The Alembic revisions, actually executed (spec §13).

The rest of the suite builds its schema with `Base.metadata.create_all`, so
until this file existed the ~30 revisions under `alembic/versions/` were
exercised by nothing but text greps: a revision that raised on an empty
database, or a model change that nobody wrote a migration for, shipped green.

Three things are proved here, each against a scratch database this module
creates and drops itself — never the suite's, whose schema and rows other
tests depend on:

1. `alembic upgrade head` runs clean from an empty database;
2. the schema it produces matches `Base.metadata` (Alembic's own
   `compare_metadata`) — the check that catches a model change with no
   migration;
3. the newest revision round-trips: `downgrade -1`, then `upgrade head`.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command
from app.config import get_config
from app.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ── what the comparison ignores, and why ──────────────────────────────────
#
# Exactly one family of objects: the LangGraph Postgres checkpointer's own
# schema. `AsyncPostgresSaver.setup()` creates `checkpoints`,
# `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` and their
# indexes at runtime, the first time a run needs to pause; they are the
# saver's tables, not ours, and they are deliberately outside
# `Base.metadata`. `compare_metadata` therefore reports each of them as a
# `remove_table` / `remove_index` — a demand to DROP them.
#
# This matters more than it looks. On a database that has never served a run
# the saver has never called `setup()`, the tables do not exist, and the
# diff is empty either way — so a check without this filter passes here and
# fails the first time anyone points it at a database that has done any
# work. The three `*_thread_prefix_idx` indexes are ours (raw DDL in
# `x3l4m5n6o7p8`, guarded by `to_regclass`) but they sit ON the saver's
# tables, so they are excluded by the same rule.
#
# Filtering is by name prefix and nothing else: every object our metadata
# does own is still compared, and the assertion below is still exactly
# empty.
_SAVER_PREFIX = "checkpoint"


def _is_saver_table(name: str | None) -> bool:
    return bool(name) and str(name).startswith(_SAVER_PREFIX)


def _include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
    """Reflection-side filter: keeps the saver's tables out of the comparison
    entirely (and with them every index and constraint they carry)."""
    if type_ == "table":
        return not _is_saver_table(name)
    if type_ in {"index", "unique_constraint", "foreign_key_constraint"}:
        return not _is_saver_table(parent_names.get("table_name"))
    return True


def _include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Object-side filter, belt and braces with `_include_name`: an index on
    a saver table reaches this hook carrying its table, not just its name."""
    if type_ == "table":
        return not _is_saver_table(name)
    table = getattr(obj, "table", None)
    return not _is_saver_table(getattr(table, "name", None))


async def _create_saver_schema(url: str) -> None:
    """Run the checkpointer's own `setup()` against the scratch database, so
    the comparison below is made against a schema shaped like a database
    that has actually served a run — which is where the filter earns its
    keep."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        url.replace("+psycopg", ""),
        open=False,
        min_size=1,
        max_size=4,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        await AsyncPostgresSaver(pool).setup()
    finally:
        await pool.close()


# Nothing ELSE is filtered, deliberately. The one artefact that would have
# needed an exemption when this file was written —
# `sub_agents.embedding_hash` and `tools.embedding_hash` declaring
# `String(64)` against the `sa.Text()` that
# `f31a9c04e7d1_add_registry_embeddings` actually created — was fixed at the
# source instead (both models now declare `Text`). If a future difference is
# genuinely a rendering artefact, exempt THAT ONE by table and column with a
# comment naming it; never widen the assertion below.


def _describe(diff: Any) -> str:
    if isinstance(diff, list):
        return " ".join(_describe(d) for d in diff)
    if not isinstance(diff, tuple) or not diff:
        return repr(diff)
    kind = diff[0]
    if kind in {"add_table", "remove_table"}:
        return f"{kind}: {diff[1].name}"
    if kind in {"add_column", "remove_column"}:
        return f"{kind}: {diff[2]}.{diff[3].name}"
    if kind in {"add_index", "remove_index", "add_constraint", "remove_constraint"}:
        obj = diff[1]
        table = getattr(obj, "table", None)
        # `bool(Table)` raises, so compare against None explicitly
        owner = table.name if table is not None else "?"
        cols = ", ".join(c.name for c in getattr(obj, "columns", []))
        return f"{kind}: {owner}.{obj.name} ({cols})"
    if kind.startswith("modify_"):
        return f"{kind}: {diff[2]}.{diff[3]} {diff[5]!r} -> {diff[6]!r}"
    return repr(diff)


# ── scratch database ──────────────────────────────────────────────────────


def _admin_url() -> str:
    """The configured database URL, pointed at the `postgres` maintenance
    database and at the sync driver (CREATE DATABASE cannot run in the
    asyncpg engine's transaction)."""
    url = sa.make_url(get_config().database_url.replace("+asyncpg", "+psycopg"))
    # render_as_string, not str(): URL.__str__ masks the password
    return url.set(database="postgres").render_as_string(hide_password=False)


@contextmanager
def _scratch_database() -> Iterator[str]:
    """A database of this module's own, dropped however the test ends."""
    name = f"concierge_mig_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
        url = sa.make_url(_admin_url()).set(database=name).render_as_string(hide_password=False)
        try:
            yield url
        finally:
            with admin.connect() as conn:
                # WITH (FORCE): a connection left open by a failing test must
                # not turn a cleanup into a hang
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@contextmanager
def _alembic(url: str) -> Iterator[Config]:
    """`alembic/env.py` reads `get_config().database_url`, so point the whole
    config at the scratch database for the length of the command and put the
    process back exactly as it was."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url.replace("+psycopg", "+asyncpg")
    get_config.cache_clear()
    try:
        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        yield cfg
    finally:
        if previous is None:  # pragma: no cover - the suite always sets it
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_config.cache_clear()


def _head_revision() -> str:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(BACKEND_ROOT / "alembic"))
    return script.get_current_head() or ""


def _stamped(url: str) -> str | None:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


@pytest.fixture
def migrated() -> Iterator[str]:
    """An empty database taken to head. The upgrade itself is the first
    assertion: a revision that raises fails every test in this file."""
    with _scratch_database() as url:
        with _alembic(url) as cfg:
            command.upgrade(cfg, "head")
        yield url


def test_upgrade_head_from_empty(migrated: str) -> None:
    """(a) every revision runs, in order, on a database with nothing in it."""
    head = _head_revision()
    assert head, "alembic has no head revision"
    assert _stamped(migrated) == head

    engine = sa.create_engine(migrated)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
    # a spot check that the revisions built the real schema and not just the
    # version table: the oldest table, one from the middle, one from the end
    assert {"runs", "memories", "eval_runs", "a2a_tasks"} <= tables
    assert "alembic_version" in tables


async def test_migrated_schema_matches_models(migrated: str) -> None:
    """(b) the migrated schema IS `Base.metadata`.

    This is the check that catches a model change nobody wrote a migration
    for. It compares types but not server defaults: `compare_server_default`
    diffs every column whose default lives in Python rather than in the DDL,
    which is most of them, and says nothing about drift.

    The comparison is made AFTER the LangGraph checkpointer has created its
    own schema, because that is the shape of every database that has served
    a run — see `_include_name` above for what that means and why.
    """
    await _create_saver_schema(migrated)
    engine = sa.create_engine(migrated)
    try:
        with engine.connect() as conn:
            # the saver's tables really are there — otherwise this test is
            # quietly proving the filter on an empty room
            assert _is_saver_table(
                next((t for t in sa.inspect(engine).get_table_names() if _is_saver_table(t)), None)
            ), "the checkpointer's schema was not created; the exclusion below proves nothing"
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "compare_server_default": False,
                    "include_name": _include_name,
                    "include_object": _include_object,
                },
            )
            diffs = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()

    assert not diffs, "migrated schema differs from Base.metadata:\n" + "\n".join(
        f"  - {_describe(d)}" for d in diffs
    )


def test_newest_revision_round_trips(migrated: str) -> None:
    """(c) the newest revision's `downgrade` undoes its `upgrade` — the step
    an operator takes when a deploy goes wrong, and the one nothing else
    exercises."""
    head = _head_revision()
    with _alembic(migrated) as cfg:
        command.downgrade(cfg, "-1")
        after_downgrade = _stamped(migrated)
        assert after_downgrade != head, "downgrade -1 left the database at head"
        command.upgrade(cfg, "head")
    assert _stamped(migrated) == head
