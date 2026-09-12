"""Multi-replica ambient coordination (spec §18.9): the tick elects a leader
through a Postgres session advisory lock on a dedicated classid — exactly one
loop runs the evaluators, every loop LISTENs and drains, and a lapsed lease
(dead session) fails over to another loop within one tick."""

import asyncio
from typing import Any

from app.ambient import drain as drain_mod
from app.ambient.coordinate import (
    AMBIENT_LEADER_CLASSID,
    AMBIENT_LEADER_OBJID,
    LeaderLease,
)
from app.ambient.drain import run_ambient_loop
from app.db import get_session_factory
from app.settings_store import update_settings


async def _ambient(enabled: bool) -> None:
    async with get_session_factory()() as session:
        await update_settings(session, {"ambient_enabled": enabled})


# ── the lease itself ─────────────────────────────────────────────


class TestLeaderLease:
    async def test_dedicated_classid(self) -> None:
        # the pair is part of the on-wire contract between replicas — a
        # collision with the consolidation-job locks would deadlock ticks
        assert (AMBIENT_LEADER_CLASSID, AMBIENT_LEADER_OBJID) == (427017, 1)

    async def test_second_lease_blocked_until_release(self) -> None:
        a, b = LeaderLease(), LeaderLease()
        try:
            assert await a.ensure() is True
            assert a.held
            assert await b.ensure() is False  # held by a's session
            assert not b.held
            await a.release()
            assert await b.ensure() is True  # freed lock is acquirable
        finally:
            await a.release()
            await b.release()

    async def test_renew_keeps_leadership(self) -> None:
        a = LeaderLease()
        try:
            assert await a.ensure() is True
            assert await a.ensure() is True  # renewal path, same session
        finally:
            await a.release()

    async def test_dead_session_lapses_and_fails_over(self) -> None:
        a, b = LeaderLease(), LeaderLease()
        try:
            assert await a.ensure() is True
            # simulate a crashed replica: the conn dies WITHOUT unlocking —
            # Postgres releases session advisory locks with the session
            assert a._conn is not None
            await a._conn.close()
            assert await b.ensure() is True  # the lease lapsed
            assert await a.ensure() is False  # a lost it and cannot reacquire
            assert not a.held
        finally:
            await a.release()
            await b.release()


class TestDarkTick:
    async def test_dark_tick_releases_a_held_lease_without_raising(self) -> None:
        """One tick body, ambient dark, lease held: it must release and
        return — never raise out of the tick. The regression this pins
        was an UnboundLocalError on `obs` in exactly this branch."""
        from app import obs

        class FakeLease:
            held = True
            released = 0

            async def release(self) -> None:
                self.released += 1
                self.held = False

        class FakeCache:
            async def setting(self, key: str) -> Any:
                assert key == "ambient_enabled"
                return False

        lease = FakeLease()
        errors_before = obs.LOOP_ERRORS.labels(loop="ambient")._value.get()
        obs.AMBIENT_LEADER.set(1.0)
        await drain_mod._tick(asyncio.Event(), asyncio.Event(), lease, lambda: FakeCache())
        assert lease.released == 1 and not lease.held
        assert obs.AMBIENT_LEADER._value.get() == 0.0
        assert obs.LOOP_ERRORS.labels(loop="ambient")._value.get() == errors_before

    async def test_loop_survives_a_tick_that_raises(self, monkeypatch: Any) -> None:
        """Belt and braces: even a tick whose own error handling fails
        must not end the loop — it is counted, logged and the loop goes on."""
        from app import obs

        calls: list[int] = []

        async def broken_tick(*_a: Any, **_k: Any) -> None:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("handler itself failed")

        monkeypatch.setattr(drain_mod, "_tick", broken_tick)
        errors_before = obs.LOOP_ERRORS.labels(loop="ambient")._value.get()
        stop = asyncio.Event()
        task = asyncio.create_task(run_ambient_loop(stop, tick_s=0.05))
        try:
            await asyncio.sleep(0.4)
            assert not task.done(), "the loop died on a raising tick"
            assert len(calls) >= 3, "the loop stopped ticking after the raise"
            assert obs.LOOP_ERRORS.labels(loop="ambient")._value.get() == errors_before + 1
        finally:
            stop.set()
            if not task.done():
                await task


# ── two concurrent loops in one process ──────────────────────────


def _install_probes(monkeypatch: Any, evaluator_calls: list[int], drain_calls: list[int]) -> None:
    """Replace the first evaluator and the drain with task-identifying probes:
    id(current_task) tells which loop invoked them."""

    async def probe_evaluator() -> None:
        task = asyncio.current_task()
        assert task is not None
        evaluator_calls.append(id(task))

    async def probe_drain() -> int:
        task = asyncio.current_task()
        assert task is not None
        drain_calls.append(id(task))
        return 0

    monkeypatch.setattr("app.ambient.triggers.evaluate_schedules", probe_evaluator)
    monkeypatch.setattr(drain_mod, "drain_once", probe_drain)


class TestTwoLoops:
    async def test_exactly_one_loop_ticks_and_both_drain(self, monkeypatch: Any) -> None:
        await _ambient(True)
        evaluator_calls: list[int] = []
        drain_calls: list[int] = []
        _install_probes(monkeypatch, evaluator_calls, drain_calls)
        stop1, stop2 = asyncio.Event(), asyncio.Event()
        t1 = asyncio.create_task(run_ambient_loop(stop1, tick_s=0.2))
        t2 = asyncio.create_task(run_ambient_loop(stop2, tick_s=0.2))
        try:
            await asyncio.sleep(1.2)
            assert evaluator_calls, "no tick ran at all"
            assert set(evaluator_calls) in ({id(t1)}, {id(t2)}), (
                "evaluators must run on exactly ONE loop"
            )
            assert set(drain_calls) == {id(t1), id(t2)}, (
                "every replica drains (SKIP-LOCKED-safe), leader or not"
            )
        finally:
            stop1.set()
            stop2.set()
            await asyncio.gather(t1, t2)

    async def test_takeover_when_leader_stops(self, monkeypatch: Any) -> None:
        await _ambient(True)
        evaluator_calls: list[int] = []
        drain_calls: list[int] = []
        _install_probes(monkeypatch, evaluator_calls, drain_calls)
        stop1, stop2 = asyncio.Event(), asyncio.Event()
        t1 = asyncio.create_task(run_ambient_loop(stop1, tick_s=0.2))
        t2 = asyncio.create_task(run_ambient_loop(stop2, tick_s=0.2))
        try:
            await asyncio.sleep(0.8)
            assert evaluator_calls
            leader_id = evaluator_calls[-1]
            leader_task, leader_stop, follower_task = (
                (t1, stop1, t2) if leader_id == id(t1) else (t2, stop2, t1)
            )
            # a clean stop releases the lease; a crash would lapse it — either
            # way the follower takes over within one tick
            leader_stop.set()
            await leader_task
            evaluator_calls.clear()
            await asyncio.sleep(0.8)
            assert evaluator_calls, "the follower never took over"
            assert set(evaluator_calls) == {id(follower_task)}
        finally:
            stop1.set()
            stop2.set()
            for task in (t1, t2):
                if not task.done():
                    await task

    async def test_off_then_on_leads_again(self, monkeypatch: Any) -> None:
        """The Settings switch flips ambient_enabled off and back on. The
        tick that sees it dark surrenders the lease; the next tick that
        sees it lit must lead again. Before the fix the dark tick raised
        inside `_tick` (a local `obs` import shadowed the module), the
        handler raised on the same name, and the loop task died: no lease,
        gauge 0, nothing logged, until a restart."""
        from app import obs

        await _ambient(True)
        evaluator_calls: list[int] = []
        drain_calls: list[int] = []
        _install_probes(monkeypatch, evaluator_calls, drain_calls)
        stop = asyncio.Event()
        task = asyncio.create_task(run_ambient_loop(stop, tick_s=0.1))
        try:
            await asyncio.sleep(0.5)
            assert evaluator_calls, "the loop never led while lit"
            await _ambient(False)
            await asyncio.sleep(0.5)
            assert not task.done(), "the loop task died on the dark tick"
            assert obs.AMBIENT_LEADER._value.get() == 0.0
            probe = LeaderLease()
            try:
                assert await probe.ensure() is True, "the dark loop must surrender the lease"
            finally:
                await probe.release()
            evaluator_calls.clear()
            await _ambient(True)
            await asyncio.sleep(0.8)
            assert not task.done(), "the loop task died after the dark→lit transition"
            assert evaluator_calls, "the loop never led again after ambient came back"
            assert obs.AMBIENT_LEADER._value.get() == 1.0
        finally:
            stop.set()
            if not task.done():
                await task

    async def test_dark_loop_holds_no_lease(self, monkeypatch: Any) -> None:
        await _ambient(False)
        evaluator_calls: list[int] = []
        drain_calls: list[int] = []
        _install_probes(monkeypatch, evaluator_calls, drain_calls)
        stop = asyncio.Event()
        task = asyncio.create_task(run_ambient_loop(stop, tick_s=0.1))
        probe = LeaderLease()
        try:
            await asyncio.sleep(0.4)
            assert evaluator_calls == [] and drain_calls == []  # dark = no-op
            assert await probe.ensure() is True, "a dark loop must not hold the lease"
        finally:
            await probe.release()
            stop.set()
            await task
