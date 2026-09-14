"""The run-plane tenancy guards (spec §18.8, docs-hardening wave).

A documentation pass measured which run-plane surfaces actually asked the
auth port and found five that did not. `GET /runs/{id}` and
`DELETE /runs/{id}` had always called `owns_row`; cancel, retry, the HITL
decision, the HITL queue, the ambient ledger and — worst — the run-history
purge had not. The purge was unscoped AND unguarded: `_ADMIN_WRITE` covers
the registry and settings but not `/runs`, so with auth ON, destroying every
user's entire run history was a plain member action.

The §18.8 note that ownership checks on cancel/hitl/purge were left to a
later auth workstream covered acting on someone else's run. It never covered
erasing everyone's.

Every test here runs with auth ON, because with auth dark the provider's
filter is None by design and all of this is single-user behaviour that must
stay byte-identical — the last class in this file holds that line.
"""

from typing import Any
from uuid import uuid4

import pytest

from app.auth import bootstrap_admin
from app.config import get_config
from app.db import get_session_factory
from app.models import Conversation, Run, User

pytestmark = pytest.mark.anyio


@pytest.fixture
def auth_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


async def _login(client: Any, username: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["token"])


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _two_members(client: Any) -> tuple[User, str, User, str]:
    """alice and bob, both plain members, with their bearer tokens."""
    from sqlalchemy import select

    _, admin_pw = await bootstrap_admin()
    admin_token = await _login(client, "admin", admin_pw)
    tokens, users = [], []
    for name in ("alice", "bob"):
        resp = await client.post(
            "/api/v1/auth/users",
            json={"username": name, "password": "member-pass-1", "role": "member"},
            headers=_h(admin_token),
        )
        assert resp.status_code == 201, resp.text
        tokens.append(await _login(client, name, "member-pass-1"))
    async with get_session_factory()() as session:
        for name in ("alice", "bob"):
            users.append(
                (await session.execute(select(User).where(User.username == name))).scalar_one()
            )
    return users[0], tokens[0], users[1], tokens[1]


async def _run_for(user: User | None, status: str = "paused_hitl") -> Run:
    async with get_session_factory()() as session:
        uid = user.id if user is not None else None
        conv = Conversation(id=uuid4(), title="conv", user_id=uid)
        session.add(conv)
        await session.flush()
        run = Run(
            id=uuid4(),
            conversation_id=conv.id,
            chat_message="a private question",
            status=status,
            user_id=uid,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


class TestOneMemberCannotReachAnothersRun:
    async def test_purge_does_not_delete_another_members_runs(
        self, client: Any, auth_on: Any
    ) -> None:
        """The sharpest one: DELETE /runs used to wipe the whole table."""
        from sqlalchemy import func, select

        alice, _alice_t, _bob, bob_t = await _two_members(client)
        alice_run = await _run_for(alice, status="completed")
        bob_run = await _run_for(_bob, status="completed")

        resp = await client.delete("/api/v1/runs", headers=_h(bob_t))
        assert resp.status_code == 204, resp.text

        async with get_session_factory()() as session:
            surviving = set((await session.execute(select(Run.id))).scalars())
            total = (await session.execute(select(func.count()).select_from(Run))).scalar_one()
        assert alice_run.id in surviving, "bob's purge destroyed alice's run history"
        assert bob_run.id not in surviving, "bob's own runs should be gone"
        assert total >= 1

    async def test_hitl_decision_refuses_another_members_gate(
        self, client: Any, auth_on: Any
    ) -> None:
        """A gate is the human control point — the OWNER's human."""
        alice, _at, _bob, bob_t = await _two_members(client)
        run = await _run_for(alice, status="paused_hitl")
        resp = await client.post(
            f"/api/v1/runs/{run.id}/hitl", json={"decision": "approve"}, headers=_h(bob_t)
        )
        assert resp.status_code == 404, resp.text

    async def test_cancel_refuses_another_members_run(self, client: Any, auth_on: Any) -> None:
        alice, _at, _bob, bob_t = await _two_members(client)
        run = await _run_for(alice, status="running")
        resp = await client.post(f"/api/v1/runs/{run.id}/cancel", headers=_h(bob_t))
        assert resp.status_code == 404, resp.text

    async def test_retry_refuses_another_members_run(self, client: Any, auth_on: Any) -> None:
        """Retry also SPENDS tokens on the victim's behalf."""
        alice, _at, _bob, bob_t = await _two_members(client)
        run = await _run_for(alice, status="failed")
        resp = await client.post(f"/api/v1/runs/{run.id}/retry", headers=_h(bob_t))
        assert resp.status_code == 404, resp.text

    async def test_hitl_queue_lists_only_my_own_gates(self, client: Any, auth_on: Any) -> None:
        """The queue is rendered with working buttons beside each row."""
        alice, _at, bob, bob_t = await _two_members(client)
        alice_run = await _run_for(alice, status="paused_hitl")
        bob_run = await _run_for(bob, status="paused_hitl")
        resp = await client.get("/api/v1/hitl/pending", headers=_h(bob_t))
        assert resp.status_code == 200, resp.text
        ids = {row["run_id"] for row in resp.json()}
        assert str(bob_run.id) in ids
        assert str(alice_run.id) not in ids, "bob can see alice's pending gate"

    async def test_the_owner_is_still_allowed(self, client: Any, auth_on: Any) -> None:
        """The guard must refuse the stranger, not the owner."""
        alice, alice_t, _bob, _bt = await _two_members(client)
        run = await _run_for(alice, status="running")
        resp = await client.post(f"/api/v1/runs/{run.id}/cancel", headers=_h(alice_t))
        assert resp.status_code in (200, 202), resp.text


class TestDarkStackIsUnchanged:
    """Auth off is the shipped default and must stay byte-identical: the
    provider's tenancy filter is None, so every scoped query is every row."""

    async def test_purge_still_deletes_everything_when_auth_is_dark(self, client: Any) -> None:
        from sqlalchemy import func, select

        await _run_for(None, status="completed")
        await _run_for(None, status="completed")
        resp = await client.delete("/api/v1/runs")
        assert resp.status_code == 204, resp.text
        async with get_session_factory()() as session:
            total = (await session.execute(select(func.count()).select_from(Run))).scalar_one()
        assert total == 0

    async def test_hitl_queue_lists_everything_when_auth_is_dark(self, client: Any) -> None:
        run = await _run_for(None, status="paused_hitl")
        resp = await client.get("/api/v1/hitl/pending")
        assert resp.status_code == 200, resp.text
        assert str(run.id) in {row["run_id"] for row in resp.json()}
