"""The out-of-run spend ledger (`job_usage`, code_setting_ui_hardening).

The spend ceiling counted RUNS only. Every model call the system makes on
its own initiative — the overlap, significance and salience judges,
anticipation, run digests, reflection, community summaries, extraction —
sat outside it. So the Settings hint said the ceiling was "one number for
the whole deployment", the dashboard reported $0 for all of that work, and
an operator sitting at their ceiling watched chat get refused while the
background jobs kept billing.

These tests hold the three claims that fix makes: the tokens are recorded,
they count toward the same one ceiling a run answers to, and a job past
that ceiling declines instead of spending.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db import get_session_factory
from app.settings_store import update_settings

pytestmark = pytest.mark.anyio


async def _set(**kv: Any) -> None:
    async with get_session_factory()() as session:
        await update_settings(session, kv)


async def _clear_ledger() -> None:
    from app.models import JobUsage

    async with get_session_factory()() as session:
        await session.execute(delete(JobUsage))
        await session.commit()


async def _rows() -> list[Any]:
    from app.models import JobUsage

    async with get_session_factory()() as session:
        return list((await session.execute(select(JobUsage))).scalars())


async def _spend(*, fresh: bool = True) -> dict[str, Any]:
    from app.cost import invalidate_spend_cache, spend_today
    from app.orchestrator.graph_mode import load_settings_snapshot

    invalidate_spend_cache()
    return await spend_today(await load_settings_snapshot(), fresh=fresh)


class TestJobUsageIsRecorded:
    async def test_an_out_of_run_call_lands_in_the_ledger(self) -> None:
        from app.cost import record_job_usage

        await _clear_ledger()
        await _set(model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}})
        await record_job_usage(
            "overlap_judge", "fake:judge", {"input_tokens": 1000, "output_tokens": 500}
        )
        rows = await _rows()
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "overlap_judge"
        assert row.model == "fake:judge"
        assert row.input_tokens == 1000 and row.output_tokens == 500
        assert row.cost_priced is True
        # 1000/1e6*1000 + 500/1e6*1000 = 1.0 + 0.5
        assert row.cost_usd == pytest.approx(1.5)

    async def test_a_call_with_no_tokens_writes_nothing(self) -> None:
        """A provider that reported no usage is not a zero-cost row — it is
        no row at all, or the ledger fills with noise that prices nothing."""
        from app.cost import record_job_usage

        await _clear_ledger()
        await record_job_usage("reflection", "fake:judge", {})
        await record_job_usage("reflection", "fake:judge", None)
        await record_job_usage("reflection", "fake:judge", {"input_tokens": 0, "output_tokens": 0})
        assert await _rows() == []

    async def test_an_unknown_model_is_recorded_unpriced_never_guessed(self) -> None:
        from app.cost import record_job_usage

        await _clear_ledger()
        await _set(model_prices={})
        await record_job_usage(
            "memory_extract", "nobody:knows-this", {"input_tokens": 700, "output_tokens": 300}
        )
        rows = await _rows()
        assert len(rows) == 1
        assert rows[0].cost_priced is False
        assert not rows[0].cost_usd  # None or 0 — never an invented number
        # and the day's report surfaces the tokens rather than hiding them
        spend = await _spend()
        assert spend["unpriced_tokens"] >= 1000

    async def test_a_ledger_write_never_raises_into_the_job(self) -> None:
        """Best-effort by design: measuring the work must not break it."""
        from app.cost import record_job_usage

        await _clear_ledger()
        # a settings blob that is not a dict where a price map is expected
        await record_job_usage(
            "salience_judge",
            "fake:judge",
            {"input_tokens": 10, "output_tokens": 10},
            {"model_prices": "not-a-mapping"},
        )  # must not raise


class TestJobUsageCountsTowardTheOneCeiling:
    async def test_job_spend_shows_up_in_the_day_total_and_by_kind(self) -> None:
        from app.cost import record_job_usage

        await _clear_ledger()
        await _set(
            model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}},
            spend_ceiling_enabled=False,
        )
        before = await _spend()
        await record_job_usage(
            "community_summary", "fake:judge", {"input_tokens": 2000, "output_tokens": 0}
        )
        after = await _spend()
        assert after["usd_today"] == pytest.approx(before["usd_today"] + 2.0)
        # reported under its own kind so an operator can see WHICH job spent
        assert after["by_kind"]["job:community_summary"] == pytest.approx(2.0)

    async def test_job_spend_alone_can_reach_the_ceiling(self) -> None:
        """The point of the fix: before it, background work could bill past
        the ceiling forever because the ceiling never saw it."""
        from app.cost import record_job_usage

        await _clear_ledger()
        await _set(
            model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}},
            spend_ceiling_enabled=True,
            spend_ceiling_usd_per_day=1.0,
        )
        assert (await _spend())["ceiling"]["reached"] is False
        await record_job_usage(
            "anticipation", "fake:judge", {"input_tokens": 5000, "output_tokens": 0}
        )  # $5 against a $1 ceiling
        spend = await _spend()
        assert spend["ceiling"]["reached"] is True
        assert spend["ceiling"]["remaining"] == 0.0

    async def test_yesterdays_job_spend_does_not_count_against_today(self) -> None:
        from app.models import JobUsage

        await _clear_ledger()
        await _set(
            model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}},
            spend_ceiling_enabled=True,
            spend_ceiling_usd_per_day=1.0,
        )
        async with get_session_factory()() as session:
            session.add(
                JobUsage(
                    id=uuid4(),
                    kind="run_digest",
                    model="fake:judge",
                    input_tokens=9000,
                    output_tokens=0,
                    cost_usd=9.0,
                    cost_priced=True,
                    at=datetime.now(UTC) - timedelta(days=1, hours=2),
                )
            )
            await session.commit()
        spend = await _spend()
        assert spend["usd_today"] == 0.0
        assert spend["ceiling"]["reached"] is False


class TestJobsDeclineAtTheCeiling:
    async def test_enforce_job_ceiling_is_true_while_the_gate_is_off(self) -> None:
        from app.cost import enforce_job_ceiling

        await _clear_ledger()
        await _set(spend_ceiling_enabled=False, spend_ceiling_usd_per_day=0.01)
        assert await enforce_job_ceiling("overlap_judge") is True

    async def test_a_job_past_the_ceiling_declines(self) -> None:
        from app.cost import enforce_job_ceiling, record_job_usage

        await _clear_ledger()
        await _set(
            model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}},
            spend_ceiling_enabled=True,
            spend_ceiling_usd_per_day=1.0,
        )
        assert await enforce_job_ceiling("overlap_judge") is True
        await record_job_usage(
            "overlap_judge", "fake:judge", {"input_tokens": 5000, "output_tokens": 0}
        )
        from app.cost import invalidate_spend_cache

        invalidate_spend_cache()
        # declining is not an error — nobody is waiting on it, and it tries
        # again next tick
        assert await enforce_job_ceiling("overlap_judge") is False

    async def test_the_overlap_audit_declines_rather_than_spending(self) -> None:
        """The §4 re-audit is a real caller of the gate: past the ceiling it
        judges nothing instead of judging the whole registry."""
        from app.cost import invalidate_spend_cache, record_job_usage
        from app.overlap import audit_registry_overlap

        await _clear_ledger()
        await _set(
            registry_overlap_audit_enabled=True,
            model_prices={"fake:judge": {"input_per_m": 1000.0, "output_per_m": 1000.0}},
            spend_ceiling_enabled=True,
            spend_ceiling_usd_per_day=1.0,
        )
        await record_job_usage(
            "overlap_judge", "fake:judge", {"input_tokens": 5000, "output_tokens": 0}
        )
        invalidate_spend_cache()
        assert await audit_registry_overlap() == 0


class TestJobSpendContextManager:
    async def test_job_spend_ledgers_the_tokens_the_call_reported(self) -> None:
        """`job_spend` is the wrapper every out-of-run call site uses: it
        hands the model a callback and writes whatever usage came back."""
        from langchain_core.messages import AIMessage

        from app.cost import job_spend
        from app.llm import fake as fake_llm
        from app.llm import get_model

        await _clear_ledger()
        await _set(model_prices={"fake:scripted": {"input_per_m": 1000.0, "output_per_m": 1000.0}})
        fake_llm.push_message(
            AIMessage(
                content="judged",
                usage_metadata={
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "total_tokens": 400,
                },
            )
        )
        model = get_model("fake:scripted")
        async with job_spend("significance_judge", "fake:scripted") as cb:
            await model.ainvoke("anything", config={"callbacks": cb})
        rows = await _rows()
        assert len(rows) == 1
        assert rows[0].kind == "significance_judge"
        assert rows[0].input_tokens == 300 and rows[0].output_tokens == 100
        assert rows[0].cost_usd == pytest.approx(0.4)

    async def test_a_failing_call_inside_job_spend_still_propagates(self) -> None:
        """The wrapper measures; it does not swallow the job's own errors."""
        from app.cost import job_spend

        await _clear_ledger()
        with pytest.raises(ValueError, match="boom"):
            async with job_spend("eval_judge", "fake:scripted"):
                raise ValueError("boom")
