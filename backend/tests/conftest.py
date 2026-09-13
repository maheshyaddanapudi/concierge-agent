"""Shared test fixtures: test database, app client, fake LLM scripting."""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/concierge_test",
)
os.environ["FAKE_LLM_ENABLED"] = "1"
# M52: the suite's in-process counterparties (MCP HTTP server, A2A stub) listen
# on loopback; name them as the operator would name an internal server —
# the SSRF tests clear this to exercise the bare `public` policy
os.environ.setdefault("EGRESS_ALLOW_HOSTS", "127.0.0.1,localhost")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import get_config  # noqa: E402
from app.db import get_engine, get_session_factory, reset_db_state  # noqa: E402
from app.llm import fake as fake_llm  # noqa: E402
from app.llm.registry import register_builtin_providers  # noqa: E402
from app.memory import scheduler as memory_scheduler  # noqa: E402
from app.models import Base  # noqa: E402

get_config.cache_clear()
register_builtin_providers()

# An unscripted structured-output call is a missing assertion, not a
# convenience: the fake's canned PlannerOutput / ConditionChoice /
# OverlapVerdict / AnswerUi each carry a run to `completed` on their own, so
# a test that only checks "the run completed" proves nothing. Off for the
# whole suite; a test that genuinely wants the canned answer opens the door
# itself with `fake_llm.allow_defaults()` (or the `fake_defaults` fixture).
fake_llm.set_allow_defaults(False)


@pytest.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    reset_db_state()
    engine = get_engine()
    async with engine.begin() as conn:
        # memory tables use pgvector (spec §16.1); the test image ships it
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


# The fire-and-forget §16.2 post-run pipeline debounces 1s in prod; under
# suite load a task spawned by test N can land DURING test N+1, racing its
# fake-LLM script queue and the truncate below (the test_memory_semantic
# order-flake shape). Tests shrink the debounce and drain at every boundary.
memory_scheduler._POST_RUN_DEBOUNCE_S = 0.01


async def _settle_background_work() -> None:
    """Every fire-and-forget task this process may have started, awaited
    before the truncate — otherwise one replays against the NEXT test's
    world, against a table that no longer holds its rows. The A2A and eval
    entries were added when a new per-agent ingest lock made a leftover
    card refresh land one test late and fail on a foreign key: the task was
    always crossing the boundary, the lock only made it visible."""
    from app import control as _control
    from app import retrieval as _retrieval
    from app.ambient import drain as _ambient_drain
    from app.api import evals as _evals_api
    from app.settings_store import drain_backfill

    await memory_scheduler.drain()
    await drain_backfill()
    pending: list[asyncio.Task[object]] = [
        *list(getattr(_ambient_drain, "_EXEC_TASKS", set())),
        *list(getattr(_evals_api, "_RUN_TASKS", {}).values()),
        # the lazy §16.1 embedding backfill and the control-plane LISTEN
        # helpers are fire-and-forget too, and write rows of their own
        *[t for t in getattr(_retrieval, "_EMBED_TASKS", set()) if isinstance(t, asyncio.Task)],
        *list(getattr(_control, "_tasks", set())),
    ]
    pending = [t for t in pending if not t.done()]
    if pending:
        # AWAIT them — never cancel. Cancelling a task mid-flight leaves the
        # run record half-written, and the next test then trips over a world
        # nobody put there. A task that will not settle inside the budget is
        # left alone and reported rather than killed.
        done, still_running = await asyncio.wait(pending, timeout=5.0)
        if still_running:
            print(f"warning: {len(still_running)} background task(s) outlived their test")


def _reset_module_caches() -> None:
    """Module-level caches that leaked between tests, making a pass or a
    failure depend on file order.

    Everything here is process-global state that outlives the rows the
    truncate removes: a cache keyed by an id that the next test reuses, a
    watermark that suppresses the next test's first tick, a registered
    adapter or transport stub a failed test never unregistered. Nothing is
    cancelled — see `_settle_background_work`."""
    from app import cost as _cost
    from app import obs as _obs
    from app import replica as _replica
    from app import retention as _retention
    from app import sanitize as _sanitize
    from app.a2a import poller as _a2a_poller
    from app.a2a.auth import clear_token_cache
    from app.ambient import channels as _channels
    from app.ambient import decide as _decide
    from app.ambient import learn as _learn
    from app.ambient import patterns as _patterns
    from app.ambient import sources as _sources
    from app.egress import set_resolver
    from app.factory.worker import clear_worker_cache
    from app.llm import metrics as _llm_metrics
    from app.memory import lifecycle as _lifecycle
    from app.orchestrator import admission as _admission
    from app.orchestrator import runner as _runner
    from app.retrieval import _INFLIGHT, _QUERY_VECS

    clear_token_cache()
    _QUERY_VECS.clear()
    _INFLIGHT.clear()
    _patterns._recent_fires.clear()
    _runner._CANCEL_REASON.clear()
    _runner._SHUTDOWN_REASON = None

    # admission counters: a run that never reached its release (the test
    # asserted the 503 and stopped) left its id in `_running` forever, and
    # the semaphore is sized from settings the next test changes
    _admission.reset()

    # compiled sub-agent graphs, keyed by (sub_agent_id, updated_at, …) —
    # the seed hands the next test the SAME ids, so a stale graph answers
    # for a definition that no longer exists
    clear_worker_cache()

    # delivery channels: adapters registered by a test, and the httpx
    # factory stub that would otherwise send the next test's webhook into a
    # dead MockTransport
    _channels._ADAPTERS.clear()
    _channels.register_native_channels()
    _channels.set_http_client_factory(None)
    _channels._subscribers.clear()
    _sources.set_http_client_factory(None)
    _sources.set_mcp_invoker(None)
    _decide.register_judge_usage_hook(None)

    # one metrics handler per (provider, model), holding a start timestamp
    # per in-flight call: a call whose error path never fired leaves an
    # entry that is attributed to the next test's latency
    _llm_metrics._HANDLERS.clear()

    # monotonic watermarks — a tick that ran in test N suppresses the first
    # tick of test N+1, which is the shape a "the poller did nothing" flake
    # takes
    _a2a_poller.reset_poll_watermark()
    _learn._last_run = None
    _retention._LAST_RUN = None
    _lifecycle._LAST_RUN.clear()

    _obs._RUN_TIMERS.clear()
    _cost._cache = None
    _sanitize._secret_cache = None
    _replica.set_replica_id(None)
    set_resolver(None)


@pytest.fixture(autouse=True)
async def _clean_tables(_database: None) -> AsyncIterator[None]:
    yield
    # no background task may cross a test boundary — settle them BEFORE the
    # truncate so none replays against the next test's world
    await _settle_background_work()
    _reset_module_caches()
    engine = get_engine()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture(autouse=True)
def _clean_fake_script() -> Iterator[None]:
    fake_llm.clear_script()
    fake_llm.set_allow_defaults(False)
    yield
    unscripted = fake_llm.unscripted_calls()
    fake_llm.clear_script()
    # a test that opened the door (or died inside `allow_defaults()`) must
    # not leave it open for the next one
    fake_llm.set_allow_defaults(False)
    if unscripted:
        # the raise at the call site is not enough on its own: the overlap
        # judge and several ambient surfaces catch broadly and degrade, so an
        # unscripted call can be swallowed and the test still pass. Failing
        # here catches it either way.
        pytest.fail(
            "unscripted structured-output call(s) during this test: "
            f"{', '.join(unscripted)}. Script what the surface should answer, "
            "or use the `fake_defaults` fixture if the canned answer is the point."
        )


@pytest.fixture
def fake_defaults() -> Iterator[None]:
    """Opt back in to the fake provider's canned structured answers, for a
    test whose subject is genuinely elsewhere."""
    with fake_llm.allow_defaults():
        yield


@pytest.fixture(autouse=True)
def _reset_registry_cache() -> Iterator[None]:
    """Fresh cache singleton per test — mode + memory state never leak."""
    from app.registry_cache import reset_cache

    reset_cache()
    yield
    reset_cache()


@pytest.fixture(autouse=True)
def _reset_sse_shutdown_flag() -> Iterator[None]:
    """sse-starlette monkey-patches uvicorn.Server.handle_exit, so ANY
    in-process uvicorn shutdown (the MCP http-transport tests run one) sets
    AppStatus.should_exit process-wide and permanently — after which every
    later EventSourceResponse drains instantly and SSE tests in OTHER files
    return empty streams. Reset the leaked global after every test."""
    yield
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def seeded_client(client: AsyncClient) -> AsyncClient:
    resp = await client.post("/api/v1/seed/reload")
    assert resp.status_code == 200, resp.text
    return client
