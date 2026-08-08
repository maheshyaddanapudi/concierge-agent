"""M8: per-skill loop limits (§3.3), form gates (§3.5), charts (§7.1/§5b)."""

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db import get_session_factory
from app.factory.dag import validate_workflow
from app.llm import fake as fake_llm
from app.native.provider import native_tools
from app.orchestrator.answer_ui import AnswerUi, extract_charts, to_a2ui_messages
from app.settings_store import update_settings
from tests.factory_helpers import create_skill, create_sub_agent
from tests.test_orchestrator import plan_call, send_chat, steps_of_type, wait_run

API = "/api/v1"


@pytest.fixture(autouse=True)
async def _m8_settings() -> None:
    async with get_session_factory()() as session:
        await update_settings(
            session,
            {
                "default_model": "fake:scripted",
                "formatter_enabled": False,
                "orchestrator_mode": "graph",
            },
        )


class TestSkillLoopLimit:
    def test_skilldoc_parses_max_tool_iterations(self) -> None:
        from app.skilldoc import parse_skill_document

        doc = parse_skill_document("---\nname: deep\nmax_tool_iterations: 20\n---\nBody here.")
        assert doc.max_tool_iterations == 20

    def test_skilldoc_rejects_bad_limit(self) -> None:
        from app.skilldoc import SkillDocError, parse_skill_document

        with pytest.raises(SkillDocError):
            parse_skill_document("---\nname: deep\nmax_tool_iterations: zero\n---\nBody.")

    async def test_research_skill_seeded_with_20(self, seeded_client: AsyncClient) -> None:
        skills = (await seeded_client.get(f"{API}/skills")).json()
        research = next(s for s in skills if s["name"] == "web-research")
        assert research["max_tool_iterations"] == 20

    async def test_skill_override_beats_settings_default(self) -> None:
        from app.factory.worker import _max_tool_iterations

        async with get_session_factory()() as session:
            await update_settings(session, {"max_tool_iterations": 5})
        assert await _max_tool_iterations({"max_tool_iterations": 20}) == 20
        assert await _max_tool_iterations({"max_tool_iterations": None}) == 5
        assert await _max_tool_iterations(None) == 5

    async def test_api_create_and_patch_limit(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{API}/skills",
            json={"name": f"deep-{uuid4().hex[:4]}", "max_tool_iterations": 12},
        )
        assert resp.status_code == 201, resp.text
        skill = resp.json()
        assert skill["max_tool_iterations"] == 12
        resp = await client.patch(f"{API}/skills/{skill['id']}", json={"max_tool_iterations": 3})
        assert resp.status_code == 200
        assert resp.json()["max_tool_iterations"] == 3


class TestFormGates:
    def _questions(self) -> list[dict[str, Any]]:
        return [
            {"id": "scope", "prompt": "Which scope?", "kind": "choice", "options": ["all", "top"]},
            {"id": "title", "prompt": "Title for the file?", "kind": "text"},
        ]

    def test_workflow_validation_accepts_questions(self) -> None:
        workflow = {
            "nodes": [
                {"id": "g", "type": "hitl", "prompt": "Configure?", "questions": self._questions()}
            ],
            "edges": [{"from": "START", "to": "g"}, {"from": "g", "to": "END"}],
        }
        assert validate_workflow(workflow, set()) == []

    def test_workflow_validation_rejects_bad_questions(self) -> None:
        bad = {
            "nodes": [
                {
                    "id": "g",
                    "type": "hitl",
                    "prompt": "?",
                    "questions": [
                        {"id": "a", "kind": "choice", "options": ["only-one"]},
                        {"id": "a", "kind": "text"},
                        {"kind": "approve"},
                    ],
                }
            ],
            "edges": [{"from": "START", "to": "g"}, {"from": "g", "to": "END"}],
        }
        errors = validate_workflow(bad, set())
        assert any("choice needs >=2 options" in e for e in errors)
        assert any("ids must be unique" in e for e in errors)
        assert any("non-empty 'id'" in e for e in errors)

    async def test_form_gate_pause_answers_resume(self, client: AsyncClient) -> None:
        """Gate pauses with questions in the SSE payload; answers ride the
        resume into the hitl step output and downstream node state."""
        skill = await create_skill(name=f"writer-{uuid4().hex[:4]}")
        workflow = {
            "nodes": [
                {
                    "id": "gate",
                    "type": "hitl",
                    "prompt": "Configure the write",
                    "questions": self._questions(),
                },
                {"id": "write", "type": "skill", "skill_id": str(skill.id)},
            ],
            "edges": [
                {"from": "START", "to": "gate"},
                {"from": "gate", "to": "write"},
                {"from": "write", "to": "END"},
            ],
        }
        agent = await create_sub_agent(workflow, name=f"former-{uuid4().hex[:4]}")
        plan_call(
            entries=[
                {
                    "id": "s1",
                    "capability": {"type": "sub_agent", "id": str(agent.id)},
                    "task": "write it",
                    "depends_on": [],
                }
            ]
        )
        run_id = await send_chat(client, "form gate please")
        run = await wait_run(client, run_id, {"paused_hitl"})
        # resolve with answers
        fake_llm.push_ai("wrote the file")
        fake_llm.push_ai("agg")
        resp = await client.post(
            f"{API}/runs/{run_id}/hitl",
            json={
                "decision": "approve",
                "note": "go",
                "answers": {"scope": "top", "title": "Q3 brief"},
            },
        )
        assert resp.status_code == 200
        run = await wait_run(client, run_id, {"completed", "failed"})
        assert run["status"] == "completed", run["error"]
        hitl_steps = steps_of_type(run, "hitl")
        assert hitl_steps, "hitl step must be recorded"
        out = hitl_steps[-1]["output"]
        assert out.get("answers") == {"scope": "top", "title": "Q3 brief"}
        assert "scope=top" in out.get("output", "")

    async def test_plain_gate_still_works(self, client: AsyncClient) -> None:
        skill = await create_skill(name=f"plain-{uuid4().hex[:4]}")
        workflow = {
            "nodes": [
                {"id": "gate", "type": "hitl", "prompt": "Approve?"},
                {"id": "do", "type": "skill", "skill_id": str(skill.id)},
            ],
            "edges": [
                {"from": "START", "to": "gate"},
                {"from": "gate", "to": "do"},
                {"from": "do", "to": "END"},
            ],
        }
        agent = await create_sub_agent(workflow, name=f"plain-{uuid4().hex[:4]}")
        plan_call(
            entries=[
                {
                    "id": "s1",
                    "capability": {"type": "sub_agent", "id": str(agent.id)},
                    "task": "t",
                    "depends_on": [],
                }
            ]
        )
        run_id = await send_chat(client, "plain gate")
        await wait_run(client, run_id, {"paused_hitl"})
        fake_llm.push_ai("done")
        fake_llm.push_ai("agg")
        resp = await client.post(f"{API}/runs/{run_id}/hitl", json={"decision": "approve"})
        assert resp.status_code == 200
        run = await wait_run(client, run_id, {"completed", "failed"})
        assert run["status"] == "completed", run["error"]


class TestCharts:
    def _chart_ui(self) -> AnswerUi:
        return AnswerUi.model_validate(
            {
                "components": [
                    {"type": "text", "markdown": "Throughput by line"},
                    {
                        "type": "chart",
                        "title": "Throughput",
                        "chart_kind": "bar",
                        "labels": ["L3", "L4", "L5"],
                        "series": [{"name": "units", "values": [10, 12, 7]}],
                    },
                ]
            }
        )

    def test_extract_charts_normalizes(self) -> None:
        charts = extract_charts(self._chart_ui())
        assert charts == [
            {
                "kind": "bar",
                "title": "Throughput",
                "labels": ["L3", "L4", "L5"],
                "series": [{"name": "units", "values": [10.0, 12.0, 7.0]}],
            }
        ]

    def test_chart_components_do_not_break_a2ui(self) -> None:
        msgs = to_a2ui_messages(self._chart_ui())
        assert msgs[0]["createSurface"]["surfaceId"] == "answer"
        # unknown-to-a2ui chart nodes are ignored by the builder, never errored
        assert any(c["component"] == "Text" for c in msgs[1]["updateComponents"]["components"])

    async def test_generation_strips_charts_when_disabled(self) -> None:
        from app.orchestrator.answer_ui import generate_answer_ui

        async with get_session_factory()() as session:
            await update_settings(session, {"answer_ui_charts_enabled": False})
        fake_llm.push_message(
            __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "AnswerUi",
                        "args": self._chart_ui().model_dump(),
                        "id": "ui1",
                    }
                ],
            )
        )
        payload, _usage = await generate_answer_ui("fake:scripted", "t", "a", [])
        assert payload is not None
        assert "charts" not in payload

    async def test_generation_includes_charts_when_enabled(self) -> None:
        from app.orchestrator.answer_ui import generate_answer_ui

        fake_llm.push_message(
            __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(
                content="",
                tool_calls=[
                    {"name": "AnswerUi", "args": self._chart_ui().model_dump(), "id": "ui2"}
                ],
            )
        )
        payload, _usage = await generate_answer_ui("fake:scripted", "t", "a", [])
        assert payload is not None
        assert payload["charts"][0]["kind"] == "bar"


class TestRenderChartTool:
    async def test_registered_and_validates(self) -> None:
        entry = native_tools().get("render_chart")
        assert entry is not None
        result = await entry.fn(
            kind="pie", labels=["a", "b"], series=[{"name": "s", "values": [1, 2]}]
        )
        assert '"kind":"pie"' in result.replace(" ", "")

    async def test_rejects_mismatched_lengths(self) -> None:
        entry = native_tools().get("render_chart")
        assert entry is not None
        with pytest.raises(ValueError, match="values"):
            await entry.fn(kind="bar", labels=["a", "b"], series=[{"values": [1]}])
