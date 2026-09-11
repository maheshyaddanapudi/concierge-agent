"""Tool schema drift (spec §3.2) and the registry pinned into the run.

A server that renames a parameter used to overwrite the tool's input
schema silently; now every write fingerprints and versions it, a change is
logged, counted and flagged (or quarantined) until acknowledged, and every
tool call records the version it ran against — so a trace reads against
the registry as it was. Plus the overlap judge's own model role.
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import obs
from app.db import get_session_factory
from app.llm import fake as fake_llm
from app.mcp.manager import McpManager, set_manager
from app.models import McpServer, Tool
from app.native.provider import native_tool, native_tools
from app.settings_store import update_settings
from app.toolschema import (
    QUARANTINED,
    acknowledge_schema,
    apply_schema,
    schema_fingerprint,
)
from tests.factory_helpers import create_skill, create_sub_agent, create_tool

API = "/api/v1"
STUB = str(Path(__file__).resolve().parent / "stub_mcp_server.py")

if "drift_echo" not in native_tools():

    @native_tool("drift_echo", "echo a message back")
    async def _drift_echo(message: str) -> str:
        return f"drift-echo:{message}"


@pytest.fixture(autouse=True)
async def _settings() -> None:
    async with get_session_factory()() as session:
        await update_settings(
            session,
            {
                "default_model": "fake:scripted",
                "formatter_enabled": False,
                "orchestrator_mode": "graph",
                "mcp_schema_change_policy": "warn",
                "overlap_judge_model": None,
                "overlap_judge_model_params": None,
            },
        )


@pytest.fixture
async def manager() -> AsyncIterator[McpManager]:
    m = McpManager()
    set_manager(m)
    yield m
    set_manager(None)
    await m.stop()


async def make_stub_server() -> UUID:
    async with get_session_factory()() as session:
        server = McpServer(
            name=f"drift-{uuid4().hex[:4]}",
            description="stub server",
            transport="stdio",
            command=sys.executable,
            args=[STUB],
            source="dynamic",
            status="inactive",
        )
        session.add(server)
        await session.commit()
        return server.id


async def tools_of(server_id: UUID) -> dict[str, Tool]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(select(Tool).where(Tool.mcp_server_id == server_id))
        ).scalars()
        return {t.tool_name: t for t in rows}


async def wait_for(predicate: Any, timeout_s: float = 10.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.2)
    raise AssertionError("condition not met within timeout")


async def wait_run(
    client: AsyncClient, run_id: str, statuses: set[str], timeout_s: float = 20.0
) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout_s
    run: dict[str, Any] = {}
    while asyncio.get_event_loop().time() < deadline:
        run = (await client.get(f"{API}/runs/{run_id}")).json()
        if run["status"] in statuses:
            return dict(run)
        await asyncio.sleep(0.1)
    raise AssertionError(f"run did not reach {statuses}; last: {run.get('status')}")


def steps_of_type(run: dict[str, Any], step_type: str) -> list[dict[str, Any]]:
    return [s for s in run["steps"] if s["step_type"] == step_type]


def plan_direct_tool(tool_id: str) -> None:
    fake_llm.push_ai(
        "",
        tool_calls=[
            {
                "name": "PlannerOutput",
                "args": {
                    "entries": [
                        {
                            "id": "s1",
                            "capability": {"type": "direct_tool", "id": tool_id},
                            "task": "echo hello",
                            "depends_on": [],
                        }
                    ],
                    "direct_answer": None,
                    "no_confident_match": False,
                },
                "id": f"p{uuid4().hex[:6]}",
            }
        ],
    )


# ── the fingerprint and the write rule ───────────────────────────


class TestFingerprint:
    def test_key_order_and_whitespace_do_not_count(self) -> None:
        a = {"type": "object", "properties": {"text": {"type": "string"}, "n": {"type": "int"}}}
        b = {"properties": {"n": {"type": "int"}, "text": {"type": "string"}}, "type": "object"}
        assert schema_fingerprint(a) == schema_fingerprint(b)
        assert len(schema_fingerprint(a) or "") == 64

    def test_a_renamed_parameter_counts(self) -> None:
        a = {"type": "object", "properties": {"text": {"type": "string"}}}
        b = {"type": "object", "properties": {"message": {"type": "string"}}}
        assert schema_fingerprint(a) != schema_fingerprint(b)
        assert schema_fingerprint(None) is None


def _row(**kw: Any) -> Tool:
    defaults: dict[str, Any] = {
        "name": "t",
        "kind": "mcp",
        "tool_name": "t",
        "tool_key": f"srv.t-{uuid4().hex[:4]}",
        "source": "dynamic",
        "status": "active",
        "ingest_state": "present",
        "schema_version": 1,
    }
    defaults.update(kw)
    return Tool(**defaults)


class TestApplySchema:
    V1 = {"type": "object", "properties": {"text": {"type": "string"}}}
    V2 = {"type": "object", "properties": {"message": {"type": "string"}}}

    def test_first_sighting_records_without_flagging(self) -> None:
        row = _row()
        assert apply_schema(row, self.V1) is False
        assert row.schema_hash == schema_fingerprint(self.V1)
        assert row.schema_version == 1
        assert row.schema_changed_at is None

    def test_same_schema_is_not_a_change(self) -> None:
        row = _row(input_schema=self.V1, schema_hash=schema_fingerprint(self.V1))
        assert apply_schema(row, dict(self.V1)) is False
        assert row.schema_version == 1 and row.schema_changed_at is None

    def test_warn_bumps_flags_counts_and_keeps_the_tool_in_service(self) -> None:
        row = _row(input_schema=self.V1, schema_hash=schema_fingerprint(self.V1))
        before = obs.TOOL_SCHEMA_CHANGES.labels(kind="mcp", policy="warn")._value.get()
        assert apply_schema(row, self.V2, policy="warn") is True
        assert row.schema_version == 2
        assert row.schema_hash == schema_fingerprint(self.V2)
        assert row.schema_changed_at is not None
        assert row.status == "active" and row.ingest_state == "present"
        assert obs.TOOL_SCHEMA_CHANGES.labels(kind="mcp", policy="warn")._value.get() == before + 1

    def test_quarantine_takes_it_out_of_service_until_acknowledged(self) -> None:
        row = _row(input_schema=self.V1, schema_hash=schema_fingerprint(self.V1))
        assert apply_schema(row, self.V2, policy="quarantine") is True
        assert row.status == "inactive" and row.ingest_state == QUARANTINED
        acknowledge_schema(row)
        assert row.schema_changed_at is None
        assert row.status == "active" and row.ingest_state == "present"
        assert row.schema_version == 2, "acknowledging keeps the version — it is the record"

    def test_quarantine_never_reactivates_an_operator_disabled_tool(self) -> None:
        row = _row(status="inactive", input_schema=self.V1, schema_hash=schema_fingerprint(self.V1))
        apply_schema(row, self.V2, policy="quarantine")
        assert row.ingest_state == "present", "only an ACTIVE tool is quarantined"
        acknowledge_schema(row)
        assert row.status == "inactive"


# ── a live MCP server renaming a parameter ───────────────────────


class TestIngestDrift:
    async def _connect_and_mutate(self, manager: McpManager) -> UUID:
        server_id = await make_stub_server()
        await manager.connect_server(server_id)
        echo = (await tools_of(server_id))["echo"]
        assert echo.schema_version == 1 and echo.schema_hash is not None
        assert "text" in (echo.input_schema or {})["properties"]
        tools = await manager.get_langchain_tools(server_id, ["mutate_schema"])
        await tools[0].ainvoke({})

        async def renamed() -> bool:
            row = (await tools_of(server_id)).get("echo")
            return bool(row and "message" in (row.input_schema or {}).get("properties", {}))

        await wait_for(renamed)
        return server_id

    async def test_warn_versions_and_flags_the_tool(
        self, manager: McpManager, client: AsyncClient
    ) -> None:
        server_id = await self._connect_and_mutate(manager)
        echo = (await tools_of(server_id))["echo"]
        assert echo.schema_version == 2
        assert echo.schema_changed_at is not None
        assert echo.status == "active"  # warn keeps it in service
        assert echo.schema_hash == schema_fingerprint(echo.input_schema)
        # the API says so, and a re-ingest without a further change is quiet
        out = (await client.get(f"{API}/tools/{echo.id}")).json()
        assert out["schema_version"] == 2 and out["schema_changed_at"] is not None
        await manager.refresh_tools(server_id)
        assert (await tools_of(server_id))["echo"].schema_version == 2
        # acknowledged: the flag clears, the version stays
        resp = await client.post(f"{API}/tools/{echo.id}/acknowledge-schema")
        assert resp.status_code == 200, resp.text
        assert resp.json()["schema_changed_at"] is None
        assert resp.json()["schema_version"] == 2

    async def test_quarantine_holds_it_out_of_service_until_acknowledged(
        self, manager: McpManager, client: AsyncClient
    ) -> None:
        async with get_session_factory()() as session:
            await update_settings(session, {"mcp_schema_change_policy": "quarantine"})
        server_id = await self._connect_and_mutate(manager)
        echo = (await tools_of(server_id))["echo"]
        assert echo.schema_version == 2
        assert echo.status == "inactive" and echo.ingest_state == QUARANTINED
        # a further re-ingest does not put it back — only the operator does
        await manager.refresh_tools(server_id)
        echo = (await tools_of(server_id))["echo"]
        assert echo.status == "inactive" and echo.ingest_state == QUARANTINED
        resp = await client.post(f"{API}/tools/{echo.id}/acknowledge-schema")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "active" and body["ingest_state"] == "present"
        assert body["schema_changed_at"] is None and body["schema_version"] == 2

    async def test_acknowledge_is_idempotent_and_404s_on_unknown(self, client: AsyncClient) -> None:
        tool = await create_tool(tool_name="drift_echo", tool_key=f"quiet-{uuid4().hex[:4]}")
        resp = await client.post(f"{API}/tools/{tool.id}/acknowledge-schema")
        assert resp.status_code == 200 and resp.json()["schema_version"] == 1
        assert (await client.post(f"{API}/tools/{uuid4()}/acknowledge-schema")).status_code == 404


# ── the settings ─────────────────────────────────────────────────


class TestSettings:
    async def test_policy_is_validated(self, client: AsyncClient) -> None:
        resp = await client.patch(f"{API}/settings", json={"mcp_schema_change_policy": "ignore"})
        assert resp.status_code == 422
        resp = await client.patch(
            f"{API}/settings", json={"mcp_schema_change_policy": "quarantine"}
        )
        assert resp.status_code == 200
        assert (await client.get(f"{API}/settings")).json()["mcp_schema_change_policy"] == (
            "quarantine"
        )

    async def test_overlap_judge_model_is_its_own_role(self, client: AsyncClient) -> None:
        from app.overlap import _judge_model

        # null → the default model, like every other role
        ref, params = await _judge_model()
        assert ref == "fake:scripted" and params is None
        resp = await client.patch(
            f"{API}/settings",
            json={
                "overlap_judge_model": "fake:scripted",
                "overlap_judge_model_params": {"effort": "low"},
            },
        )
        assert resp.status_code == 200, resp.text
        ref, params = await _judge_model()
        assert ref == "fake:scripted"
        assert params is not None and params.effort == "low"
        # params without a model are refused, as for the other roles
        resp = await client.patch(
            f"{API}/settings",
            json={"overlap_judge_model": None, "overlap_judge_model_params": {"effort": "low"}},
        )
        assert resp.status_code == 422


# ── the version pinned into the run ──────────────────────────────


class TestRunPinning:
    async def test_direct_tool_step_and_snapshot_carry_the_schema_version(
        self, client: AsyncClient
    ) -> None:
        from app.factory.worker import sanitize_tool_name

        tool = await create_tool(
            tool_name="drift_echo", tool_key=f"decho-{uuid4().hex[:4]}", direct_exposure=True
        )
        plan_direct_tool(str(tool.id))
        fake_llm.push_ai(
            "",
            tool_calls=[
                {"name": sanitize_tool_name(tool.tool_key), "args": {"message": "hi"}, "id": "t1"}
            ],
        )
        fake_llm.push_ai("done")
        run_id = (await client.post(f"{API}/chat", json={"message": "echo"})).json()["run_id"]
        run = await wait_run(client, run_id, {"completed", "failed"})
        assert run["status"] == "completed", run["error"]
        step = steps_of_type(run, "tool_call")[0]
        assert step["entity_version"] == 1
        assert step["entity_hash"] == tool.schema_hash
        # the frozen snapshot keeps the schema, not only the id
        entry = run["snapshot"]["s1"]
        assert entry["payload"]["schema_hash"] == tool.schema_hash
        assert entry["payload"]["input_schema"] == tool.input_schema
        assert entry["payload"]["schema_version"] == 1

    async def test_skill_loop_tool_call_carries_the_version(self, client: AsyncClient) -> None:
        from app.factory.worker import sanitize_tool_name

        tool = await create_tool(
            tool_name="drift_echo",
            tool_key=f"secho-{uuid4().hex[:4]}",
            schema_version=3,
        )
        skill = await create_skill(name=f"drift-skill-{uuid4().hex[:4]}", tools=[tool])
        agent = await create_sub_agent(
            {
                "nodes": [{"id": "work", "type": "skill", "skill_id": str(skill.id)}],
                "edges": [{"from": "START", "to": "work"}, {"from": "work", "to": "END"}],
            },
            direct_exposure=True,
        )
        fake_llm.push_ai(
            "",
            tool_calls=[
                {"name": sanitize_tool_name(tool.tool_key), "args": {"message": "hi"}, "id": "t2"}
            ],
        )
        fake_llm.push_ai("skill done")
        resp = await client.post(f"{API}/sub-agents/{agent.id}/invoke", json={"message": "go"})
        assert resp.status_code == 201, resp.text
        run = await wait_run(client, resp.json()["run_id"], {"completed", "failed"})
        assert run["status"] == "completed", run["error"]
        step = steps_of_type(run, "tool_call")[0]
        assert step["entity_version"] == 3 and step["entity_hash"] == tool.schema_hash
        # a direct run now freezes the agent it ran, like a routed dispatch
        entry = run["snapshot"]["direct"]
        assert entry["rung"] == "custom_sub_agent"
        assert entry["payload"]["snapshot"]["sub_agent"]["id"] == str(agent.id)
        bound = entry["payload"]["snapshot"]["skills"][str(skill.id)]["tools"][0]
        assert bound["schema_hash"] == tool.schema_hash and bound["schema_version"] == 3

    async def test_agentic_run_freezes_the_catalog_it_could_see(self, client: AsyncClient) -> None:
        from app.factory.worker import sanitize_tool_name

        async with get_session_factory()() as session:
            await update_settings(session, {"orchestrator_mode": "agentic"})
        tool = await create_tool(
            tool_name="drift_echo", tool_key=f"aecho-{uuid4().hex[:4]}", direct_exposure=True
        )
        hidden = await create_tool(tool_name="drift_echo", tool_key=f"hidden-{uuid4().hex[:4]}")
        fake_llm.push_ai(
            "",
            tool_calls=[
                {"name": sanitize_tool_name(tool.tool_key), "args": {"message": "hi"}, "id": "t3"}
            ],
        )
        fake_llm.push_ai("agentic done")
        run_id = (await client.post(f"{API}/chat", json={"message": "echo"})).json()["run_id"]
        run = await wait_run(client, run_id, {"completed", "failed"})
        assert run["status"] == "completed", run["error"]
        catalog = run["snapshot"]["catalog"]
        listed = {t["id"]: t for t in catalog["tools"]}
        assert str(tool.id) in listed and str(hidden.id) not in listed
        assert listed[str(tool.id)]["schema_hash"] == tool.schema_hash
        assert listed[str(tool.id)]["schema_version"] == 1
        assert "skills" in catalog and "sub_agents" in catalog
        step = steps_of_type(run, "tool_call")[0]
        assert step["entity_version"] == 1 and step["entity_hash"] == tool.schema_hash
