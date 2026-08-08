"""The formatter role (spec §7.1): artifact carries presentation + coverage,
off = no artifact, tool charts are formatter-independent."""

import json
from typing import Any

from httpx import AsyncClient

from app.db import get_session_factory
from app.llm import fake as fake_llm
from app.models import Run, RunStep
from app.orchestrator.answer_ui import AnswerUi, UiComponent, compute_coverage
from app.orchestrator.runner import _collect_tool_charts
from app.settings_store import update_settings


def _ui(*components: UiComponent) -> AnswerUi:
    return AnswerUi(components=list(components))


class TestCoverage:
    def test_full_retention_scores_100(self) -> None:
        answer = "Revenue grew 12.4% to $3.2M — see https://x.io/report and `run_id`."
        ui = _ui(UiComponent(type="text", markdown=answer))
        assert compute_coverage(answer, ui) == 100

    def test_dropped_tokens_lower_the_score(self) -> None:
        answer = "Line 3 made 120 units, line 4 made 80 units, uptime 99.5%."
        ui = _ui(UiComponent(type="stat", label="line 3", value="120"))
        score = compute_coverage(answer, ui)
        assert score < 100
        assert score >= 20  # at least the retained number counts

    def test_prose_only_answer_scores_100(self) -> None:
        answer = "The approach is sound and the team agrees on the direction."
        ui = _ui(UiComponent(type="text", markdown="A different paraphrase."))
        assert compute_coverage(answer, ui) == 100  # no hard tokens to lose


class TestFormatterPayload:
    async def test_payload_carries_presentation_and_coverage(self) -> None:
        from langchain_core.messages import AIMessage

        from app.orchestrator.answer_ui import generate_answer_ui

        ui = AnswerUi(components=[UiComponent(type="text", markdown="All 3 facts kept.")])
        fake_llm.push_message(
            AIMessage(
                content="", tool_calls=[{"name": "AnswerUi", "args": ui.model_dump(), "id": "u1"}]
            )
        )
        payload, _usage = await generate_answer_ui(
            "fake:scripted", "t", "There are 3 facts.", [], presentation="a2ui_first"
        )
        assert payload is not None
        assert payload["presentation"] == "a2ui_first"
        assert payload["coverage"] == 100

    async def test_formatter_off_produces_no_artifact(self, client: AsyncClient) -> None:
        async with get_session_factory()() as session:
            await update_settings(
                session, {"formatter_enabled": False, "default_model": "fake:scripted"}
            )
        resp = await client.post("/api/v1/chat", json={"message": "hello"})
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]
        import asyncio

        for _ in range(80):
            await asyncio.sleep(0.1)
            run = (await client.get(f"/api/v1/runs/{run_id}")).json()
            if run["status"] in {"completed", "failed"}:
                break
        assert run["status"] == "completed"
        assert run["answer_ui"] is None  # no artifact — no toggle, ever


class TestToolCharts:
    async def _make_run_with_chart_step(self, chart: dict[str, Any] | str) -> Run:
        from app.models import Conversation

        async with get_session_factory()() as session:
            conv = Conversation(title="t")
            session.add(conv)
            await session.flush()
            run = Run(conversation_id=conv.id, chat_message="m", status="completed")
            session.add(run)
            await session.flush()
            session.add(
                RunStep(
                    run_id=run.id,
                    step_type="tool_call",
                    node_id="render_chart",
                    status="completed",
                    output={"result": chart if isinstance(chart, str) else json.dumps(chart)},
                )
            )
            await session.commit()
            await session.refresh(run)
            return run

    async def test_render_chart_steps_are_collected(self) -> None:
        # current tool output: status envelope with the spec nested under "spec"
        spec = {
            "kind": "bar",
            "title": "T",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [1.0, 2.0]}],
        }
        run = await self._make_run_with_chart_step({"status": "chart accepted", "spec": spec})
        charts = await _collect_tool_charts(run.id)
        assert charts == [spec]

    async def test_legacy_bare_spec_output_still_collected(self) -> None:
        # runs persisted before the envelope change stored the bare spec
        spec = {
            "kind": "bar",
            "title": "T",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [1.0, 2.0]}],
        }
        run = await self._make_run_with_chart_step(spec)
        charts = await _collect_tool_charts(run.id)
        assert charts == [spec]

    async def test_invalid_chart_output_is_skipped(self) -> None:
        run = await self._make_run_with_chart_step("{truncated json")
        assert await _collect_tool_charts(run.id) == []

    async def test_non_chart_tools_are_ignored(self) -> None:
        from app.models import Conversation

        async with get_session_factory()() as session:
            conv = Conversation(title="t")
            session.add(conv)
            await session.flush()
            run = Run(conversation_id=conv.id, chat_message="m", status="completed")
            session.add(run)
            await session.flush()
            session.add(
                RunStep(
                    run_id=run.id,
                    step_type="tool_call",
                    node_id="read_file",
                    status="completed",
                    output={"result": '{"kind": "bar"}'},
                )
            )
            await session.commit()
            assert await _collect_tool_charts(run.id) == []


class TestSettingsValidation:
    async def test_presentation_validated(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/settings", json={"formatter_presentation": "sideways"})
        assert resp.status_code == 422
        resp = await client.patch("/api/v1/settings", json={"formatter_presentation": "raw_first"})
        assert resp.status_code == 200

    async def test_coverage_threshold_bounds(self, client: AsyncClient) -> None:
        assert (
            await client.patch("/api/v1/settings", json={"formatter_coverage_flag_threshold": 0})
        ).status_code == 422
        assert (
            await client.patch("/api/v1/settings", json={"formatter_coverage_flag_threshold": 95})
        ).status_code == 200

    async def test_formatter_model_validated_like_other_roles(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/settings", json={"formatter_model": "nope:not-a-model"})
        assert resp.status_code == 422
        resp = await client.patch("/api/v1/settings", json={"formatter_model": "fake:scripted"})
        assert resp.status_code == 200
