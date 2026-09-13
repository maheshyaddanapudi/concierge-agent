"""The eval batch runner (spec §15): admin-direct, sequential, on the
EXISTING run machinery — every case becomes an ordinary Run (is_eval=true),
then the case grades against the run's final answer. Config snapshots make
every eval run reproducible.

An eval run is ISOLATED from the rest of the platform: it writes nothing to
the memory layer, does not appear in the human approval queue, and resolves
any gate it reaches under the DATASET's own policy — refusing by default,
and recording the decision on the run as machine-cleared either way."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.evals.grade import grade_case
from app.models import EvalCase, EvalDataset, EvalResult, EvalRun, Run

logger = structlog.get_logger("evals")

CASE_TIMEOUT_S = 600.0
_POLL_S = 0.05


async def _target_snapshot(dataset: EvalDataset) -> dict[str, Any]:
    from app.registry_cache import get_cache

    cache = get_cache()
    if dataset.level == "skill":
        return dict(await cache.skill_by_id(str(dataset.target_id)) or {})
    # the definition the eval actually runs (spec §15 "reproducible against
    # the exact definition evaluated"): the assembled snapshot with every
    # skill's persona, instructions and bound tools, not only the workflow
    snapshot = await cache.sub_agent_snapshot(str(dataset.target_id))
    if snapshot is not None:
        return dict(snapshot)
    return dict(await cache.sub_agent_by_id(str(dataset.target_id)) or {})


async def _record_machine_gate(run_id: UUID, decision: str, note: str) -> None:
    """Write the harness's gate decision onto the run as a `hitl` step marked
    `decision_source='eval'`, so the trace shows plainly that a machine
    cleared it. Best-effort: a recording failure never fails the case."""
    from app.models import RunStep

    try:
        async with get_session_factory()() as session:
            session.add(
                RunStep(
                    run_id=run_id,
                    step_type="hitl",
                    status="completed",
                    input={"gate": "eval harness"},
                    output={
                        "decision": decision,
                        "note": note,
                        "decision_source": "eval",
                    },
                    finished_at=datetime.now(UTC),
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 — the trace note never fails a case
        logger.warning("eval_gate_record_failed", run_id=str(run_id), error=str(exc)[:200])


async def _await_run(run_id: UUID, *, allow_autoapprove: bool = False) -> Run:
    """Wait for the child run, resolving HITL gates under the DATASET's policy
    until it reaches a terminal state.

    §15: the harness no longer approves by default. It used to auto-approve
    every gate, so a one-case dataset pointing at a sub agent whose workflow
    gates a destructive node ran that node to completion with no human
    decision recorded anywhere but a log line. Now a gate is DENIED unless the
    dataset was uploaded with `allow_hitl_autoapprove`, and either way the
    decision is recorded on the run as a machine-cleared one."""
    from app.orchestrator.runner import RUNNING_TASKS, resume_run

    deadline = asyncio.get_event_loop().time() + CASE_TIMEOUT_S
    while True:
        task = RUNNING_TASKS.get(run_id)
        if task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=CASE_TIMEOUT_S)
        async with get_session_factory()() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise RuntimeError("run vanished mid-operation")
            status = run.status
        if status == "paused_hitl":
            decision = "approve" if allow_autoapprove else "deny"
            note = (
                "eval harness: auto-approved (dataset allows it) — no human decided"
                if allow_autoapprove
                else "eval harness: refused (dataset does not allow auto-approval)"
            )
            await _record_machine_gate(run_id, decision, note)
            logger.info(
                "eval_hitl_machine_decision",
                tier="evals",
                kind="hitl",
                run_id=str(run_id),
                decision=decision,
            )
            await resume_run(run_id, decision, note, None)
            await asyncio.sleep(_POLL_S)
            continue
        if status not in {"running", "queued"}:
            async with get_session_factory()() as session:
                final = await session.get(Run, run_id)
                if final is None:
                    raise RuntimeError("final vanished mid-operation")
                return final
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(f"eval case run {run_id} exceeded {CASE_TIMEOUT_S}s")
        await asyncio.sleep(_POLL_S)


async def reap_stalled_eval_runs(stale_after_s: float = 2 * CASE_TIMEOUT_S) -> int:
    """Fail eval runs left `running` by a process that is no longer running
    them. A restart mid-batch used to leave a row at `running` forever, with
    no reaper and (until now) no cancel, so the page polled a batch that
    could never finish. Returns rows reaped."""
    from app.api.evals import _RUN_TASKS

    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_s)
    reaped = 0
    async with get_session_factory()() as session:
        rows = list(
            (
                await session.execute(
                    select(EvalRun).where(EvalRun.status == "running", EvalRun.started_at < cutoff)
                )
            ).scalars()
        )
        for row in rows:
            task = _RUN_TASKS.get(row.id)
            if task is not None and not task.done():
                continue  # this process is still working on it
            row.status = "failed"
            row.finished_at = datetime.now(UTC)
            reaped += 1
        if reaped:
            await session.commit()
            logger.warning("eval_runs_reaped", tier="evals", kind="run", count=reaped)
    return reaped


async def execute_eval_run(dataset_id: UUID, eval_run_id: UUID | None = None) -> EvalRun:
    """Run every case of a dataset sequentially; returns the finished
    EvalRun row (status 'completed', or 'failed' on a harness error)."""
    from app.orchestrator.graph_mode import load_settings_snapshot
    from app.orchestrator.runner import create_run, start_run_task

    async with get_session_factory()() as session:
        dataset = await session.get(EvalDataset, dataset_id)
        if dataset is None:
            raise ValueError(f"eval dataset {dataset_id} not found")
        cases = list(
            (
                await session.execute(
                    select(EvalCase)
                    .where(EvalCase.dataset_id == dataset_id)
                    .order_by(EvalCase.position)
                )
            ).scalars()
        )
        if eval_run_id is None:
            eval_run = EvalRun(dataset_id=dataset_id, total_cases=len(cases))
            session.add(eval_run)
        else:
            eval_run = await session.get(EvalRun, eval_run_id)  # type: ignore[assignment]
            if eval_run is None:
                raise RuntimeError("eval_run vanished mid-operation")
            eval_run.total_cases = len(cases)
        settings = await load_settings_snapshot()
        from app.evals.grade import _judge_model
        from app.orchestrator.snapshot import prompt_hashes

        target_snapshot = await _target_snapshot(dataset)
        judge_ref, _judge = await _judge_model()
        target_model = str(
            (target_snapshot.get("sub_agent") or {}).get("model")
            or target_snapshot.get("model")
            or settings.get("default_model")
            or ""
        )
        # every model the target can resolve to: a workflow skill with its
        # own model runs under it (review round 3 — the flag looked only at
        # the sub agent's), so the judge is "the model under test" when it
        # is any of them
        target_models = {target_model} | {
            str(s.get("model"))
            for s in (target_snapshot.get("skills") or {}).values()
            if isinstance(s, dict) and s.get("model")
        }
        eval_run.config_snapshot = {
            # every setting, structured ones included (model params, prices,
            # quarantine kinds): the knobs that shaped the scores
            "settings": dict(settings),
            "prompts": prompt_hashes(),
            "target": target_snapshot,
            # the judge that graded, and whether it is the model under test
            # grading itself (review round 2: said on the record, not only
            # in the Settings hint)
            "judge_model": judge_ref,
            "judge_is_target_model": judge_ref in target_models,
            "level": dataset.level,
            "target_id": str(dataset.target_id),
        }
        await session.commit()
        await session.refresh(eval_run)
        run_row_id = eval_run.id

    passed = failed = errored = 0
    allow_autoapprove = bool(getattr(dataset, "allow_hitl_autoapprove", False))
    try:
        for case in cases:
            # a cancel (the new endpoint, or an operator flipping the row)
            # stops the batch at the case boundary instead of grinding through
            # every remaining case against an expensive model
            async with get_session_factory()() as session:
                current = await session.get(EvalRun, run_row_id)
                if current is not None and current.status != "running":
                    logger.info(
                        "eval_run_stopped",
                        tier="evals",
                        kind="run",
                        status=current.status,
                        remaining=len(cases) - (passed + failed + errored),
                    )
                    return current
            run = await create_run(
                None,
                case.input,
                mode="direct",
                target_sub_agent_id=dataset.target_id if dataset.level == "sub_agent" else None,
                is_eval=True,
                eval_skill_id=dataset.target_id if dataset.level == "skill" else None,
            )
            start_run_task(run.id)
            try:
                finished = await _await_run(run.id, allow_autoapprove=allow_autoapprove)
                answer = finished.final_answer or ""
                if finished.status != "completed":
                    verdict = {
                        "status": "error",
                        "passed": False,
                        "score": 0.0,
                        "reason": f"run {finished.status}: {finished.error or 'no answer'}",
                    }
                else:
                    verdict = await grade_case(
                        grader=case.grader,
                        answer=answer,
                        expected=case.expected,
                        judge_notes=case.judge_notes,
                    )
            except Exception as exc:  # noqa: BLE001 — a broken case never kills the batch
                answer = ""
                verdict = {
                    "status": "error",
                    "passed": False,
                    "score": 0.0,
                    "reason": f"harness error: {exc}"[:2000],
                }
            if verdict["status"] == "error":
                errored += 1
            elif verdict["passed"]:
                passed += 1
            else:
                failed += 1
            async with get_session_factory()() as session:
                session.add(
                    EvalResult(
                        eval_run_id=run_row_id,
                        case_id=case.id,
                        run_id=run.id,
                        status=str(verdict["status"]),
                        passed=bool(verdict["passed"]),
                        score=float(verdict["score"]),  # type: ignore[arg-type]
                        grader_reason=str(verdict["reason"]),
                        answer=answer[:20000],
                    )
                )
                row = await session.get(EvalRun, run_row_id)
                if row is None:
                    raise RuntimeError("row vanished mid-operation")
                row.passed_cases, row.failed_cases, row.error_cases = passed, failed, errored
                await session.commit()
        langsmith_url = await _maybe_publish(run_row_id)
        async with get_session_factory()() as session:
            row = await session.get(EvalRun, run_row_id)
            if row is None:
                raise RuntimeError("row vanished mid-operation")
            row.status = "completed"
            row.langsmith_url = langsmith_url
            row.finished_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            final_row = row
    except Exception as exc:  # noqa: BLE001 — harness failure is recorded, not raised
        logger.warning("eval_run_failed", tier="evals", kind="run", error=str(exc))
        async with get_session_factory()() as session:
            row = await session.get(EvalRun, run_row_id)
            if row is None:
                raise RuntimeError("row vanished mid-operation") from exc
            row.status = "failed"
            row.finished_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            final_row = row
    logger.info(
        "eval_run_finished",
        tier="evals",
        kind="run",
        status=final_row.status,
        passed=passed,
        failed=failed,
        errors=errored,
    )
    return final_row


async def _maybe_publish(eval_run_id: UUID) -> str | None:
    """LangSmith publishing (spec §15): dataset + results when
    langsmith_enabled and the env key exist; otherwise skipped silently —
    Postgres traces remain the full record either way."""
    try:
        from app.evals.publish import publish_eval_run

        return await publish_eval_run(eval_run_id)
    except Exception as exc:  # noqa: BLE001 — publishing must never fail the eval
        logger.warning("eval_publish_failed", tier="evals", kind="publish", error=str(exc))
        return None
