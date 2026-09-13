"""The startup allowlist audit (spec §17.4, code_setting_ui_hardening).

This wave made a routine's allowlist a real ceiling in both orchestrator
modes. For a routine whose allowlist was written while it was decorative,
that is a silent behavior change: nothing fails at boot, and the refusal
arrives inside the next autonomous fire, which nobody is watching. The audit
exists so the operator hears about it first, at boot, by name.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.db import get_session_factory

pytestmark = pytest.mark.anyio


async def _routine(name: str, allowlist: dict[str, Any] | None, **kw: Any) -> UUID:
    from app.models import Routine

    async with get_session_factory()() as session:
        routine = Routine(
            id=uuid4(),
            name=name,
            prompt="do the thing",
            allowlist=allowlist,
            status=kw.pop("status", "active"),
            **kw,
        )
        session.add(routine)
        await session.commit()
        return UUID(str(routine.id))


async def _run_using(routine_id: UUID, steps: list[tuple[str, str]]) -> None:
    """A finished ambient run for `routine_id` whose steps used `steps`
    (step_type, entity_name)."""
    from app.models import Conversation, Run, RunStep

    async with get_session_factory()() as session:
        conv = Conversation(id=uuid4(), title="ambient")
        session.add(conv)
        await session.flush()
        run = Run(
            id=uuid4(),
            conversation_id=conv.id,
            chat_message="fire",
            status="completed",
            trigger={"routine_id": str(routine_id), "source": "schedule"},
            started_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        session.add(run)
        await session.flush()
        for step_type, entity_name in steps:
            session.add(
                RunStep(
                    id=uuid4(),
                    run_id=run.id,
                    step_type=step_type,
                    entity_name=entity_name,
                    status="completed",
                )
            )
        await session.commit()


class TestNarrowerThanHistory:
    async def test_a_routine_that_used_a_tool_outside_its_allowlist_is_named(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("digest-routine", {"tools": ["srv.allowed"]})
        await _run_using(rid, [("tool_call", "srv.allowed"), ("tool_call", "srv.forbidden")])
        findings = [f for f in await narrower_than_history() if f["routine_id"] == str(rid)]
        assert len(findings) == 1
        assert findings[0]["routine_name"] == "digest-routine"
        assert findings[0]["kind"] == "tools"
        # only the entry that would actually be refused
        assert findings[0]["entries"] == ["srv.forbidden"]

    async def test_a_routine_within_its_allowlist_is_silent(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("tidy-routine", {"tools": ["srv.a", "srv.b"]})
        await _run_using(rid, [("tool_call", "srv.a"), ("tool_call", "srv.b")])
        assert [f for f in await narrower_than_history() if f["routine_id"] == str(rid)] == []

    async def test_an_unmentioned_kind_is_unconstrained_and_never_warned_about(self) -> None:
        """The audit must mirror the runtime rule exactly: a kind the
        allowlist does not mention is not filtered, so warning about it
        would send the operator to widen something that already permits
        everything."""
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("skills-only", {"skills": ["summarize"]})
        await _run_using(rid, [("skill", "summarize"), ("tool_call", "srv.anything")])
        assert [f for f in await narrower_than_history() if f["routine_id"] == str(rid)] == []

    async def test_each_kind_is_judged_against_its_own_list(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("mixed", {"tools": ["srv.a"], "skills": ["summarize"]})
        await _run_using(
            rid,
            [
                ("tool_call", "srv.a"),
                ("skill", "summarize"),
                ("skill", "translate"),
                ("sub_agent", "researcher"),
            ],
        )
        findings = [f for f in await narrower_than_history() if f["routine_id"] == str(rid)]
        # sub_agents is unmentioned → unconstrained; tools is satisfied
        assert [(f["kind"], f["entries"]) for f in findings] == [("skills", ["translate"])]

    async def test_a_routine_with_no_allowlist_is_skipped(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("open-routine", None)
        await _run_using(rid, [("tool_call", "srv.whatever")])
        assert [f for f in await narrower_than_history() if f["routine_id"] == str(rid)] == []

    async def test_a_paused_routine_is_skipped(self) -> None:
        """It is not about to fire, so the operator does not need the noise."""
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("paused", {"tools": ["srv.a"]}, status="paused")
        await _run_using(rid, [("tool_call", "srv.forbidden")])
        assert [f for f in await narrower_than_history() if f["routine_id"] == str(rid)] == []

    async def test_a_routine_that_has_never_run_is_skipped(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        rid = await _routine("never-fired", {"tools": ["srv.a"]})
        assert [f for f in await narrower_than_history() if f["routine_id"] == str(rid)] == []

    async def test_another_routines_runs_are_not_attributed_here(self) -> None:
        from app.ambient.allowlist_audit import narrower_than_history

        mine = await _routine("mine", {"tools": ["srv.a"]})
        theirs = await _routine("theirs", {"tools": ["srv.a"]})
        await _run_using(mine, [("tool_call", "srv.a")])
        await _run_using(theirs, [("tool_call", "srv.forbidden")])
        findings = await narrower_than_history()
        assert [f["routine_name"] for f in findings if f["routine_id"] == str(mine)] == []
        assert [f["routine_name"] for f in findings if f["routine_id"] == str(theirs)] == ["theirs"]


class TestBootHook:
    async def test_the_boot_hook_logs_and_returns_a_count(self) -> None:
        from app.ambient.allowlist_audit import log_narrow_allowlists

        rid = await _routine("boot-routine", {"tools": ["srv.allowed"]})
        await _run_using(rid, [("tool_call", "srv.forbidden")])
        assert await log_narrow_allowlists() >= 1

    async def test_the_boot_hook_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An audit that fails must not fail the boot it is auditing."""
        import app.ambient.allowlist_audit as mod

        async def boom() -> list[dict[str, Any]]:
            raise RuntimeError("database is having a day")

        monkeypatch.setattr(mod, "narrower_than_history", boom)
        assert await mod.log_narrow_allowlists() == 0
