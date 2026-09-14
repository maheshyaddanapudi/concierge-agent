"""Runs API (spec §4): list/detail with ordered steps, cancel, retry, delete,
history purge."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.auth import owns_row, scope_to_user, tenancy_on
from app.models import Run, RunStep
from app.orchestrator.runner import cancel_run, forget_run_events, retry_run

router = APIRouter(prefix="/runs", tags=["runs"])

# LangGraph checkpointer tables (owned by AsyncPostgresSaver.setup(), outside
# app metadata). Checkpoint rows ride the run lifecycle: the orchestrator
# thread is the run id, worker threads are "run_id:entry_id" — so deleting a
# run deletes its checkpoints (spec §8.7: purge leaves no run residue).
_CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


async def _purge_checkpoints(session: AsyncSession, run_id: UUID | None = None) -> None:
    for table in _CHECKPOINT_TABLES:
        exists = await session.execute(text("SELECT to_regclass(:t)"), {"t": table})
        if exists.scalar_one_or_none() is None:
            continue  # saver has not created its tables yet (e.g. no run ever)
        if run_id is None:
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table names
        else:
            await session.execute(
                text(
                    f"DELETE FROM {table} "  # noqa: S608 - fixed table names
                    "WHERE thread_id = :thread OR thread_id LIKE :prefix"
                ),
                {"thread": str(run_id), "prefix": f"{run_id}:%"},
            )


def _step_out(step: RunStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "parent_step_id": str(step.parent_step_id) if step.parent_step_id else None,
        "sub_agent_id": str(step.sub_agent_id) if step.sub_agent_id else None,
        "node_id": step.node_id,
        "step_type": step.step_type,
        "input": step.input,
        "output": step.output,
        "model": step.model,
        # the entity version the step ran against (a tool's schema version
        # and hash on tool_call steps) — the trace reads against the
        # registry as it was, not as it is
        "entity_version": step.entity_version,
        "entity_hash": step.entity_hash,
        "entity_name": step.entity_name,
        "model_params": step.model_params,
        "input_tokens": step.input_tokens,
        "output_tokens": step.output_tokens,
        "status": step.status,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "finished_at": step.finished_at.isoformat() if step.finished_at else None,
        "error": step.error,
    }


def _run_out(
    run: Run, with_steps: bool = False, cost: dict[str, Any] | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(run.id),
        "conversation_id": str(run.conversation_id),
        "chat_message": run.chat_message,
        "status": run.status,
        "orchestrator_mode": run.orchestrator_mode,
        "target_sub_agent_id": str(run.target_sub_agent_id) if run.target_sub_agent_id else None,
        "include_history_summary": run.include_history_summary,
        "include_memories": run.include_memories,
        # §17.4 ambient provenance — None for interactive runs
        "trigger": run.trigger,
        # M54 (spec §18.9): who executes it, and a cancel intent it has not
        # yet acted on
        "owner_replica": run.owner_replica,
        "cancel_requested_at": (
            run.cancel_requested_at.isoformat() if run.cancel_requested_at else None
        ),
        "plan": run.plan,
        "final_answer": run.final_answer,
        "answer_ui": run.answer_ui,
        "charts": run.charts,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_input_tokens": run.total_input_tokens,
        "total_output_tokens": run.total_output_tokens,
        # M53 cost model: the cost STAMPED at finish with the prices of that
        # moment (hardening wave — a later price change never rewrites a
        # finished run); an unfinished or pre-wave run is priced live from
        # its usage; null when a model in play has no price (reported,
        # never guessed)
        "cost_usd": run.cost_usd
        if run.cost_priced is not None
        else (cost["cost_usd"] if cost else None),
        "cost_priced": (
            bool(run.cost_priced)
            if run.cost_priced is not None
            else (bool(cost["cost_priced"]) if cost else False)
        ),
    }
    if with_steps:
        data["steps"] = [_step_out(s) for s in run.steps]
        # DETAIL ONLY. Both are large — the frozen registry catalog, up to 200
        # injected-context entries, every resolution payload, the price table
        # — and the Runs page polls the LIST every few seconds while only the
        # detail drawer reads them (RunsPage.tsx: both live in RunDetail,
        # which fetches GET /runs/{id}).
        data["snapshot"] = run.snapshot
        data["price_snapshot"] = run.price_snapshot
    return data


async def _costs(session: AsyncSession, runs: list[Run]) -> dict[UUID, dict[str, Any]]:
    from app.cost import attach_costs
    from app.settings_store import get_settings

    return await attach_costs(session, runs, await get_settings(session))


@router.get("")
async def list_runs(
    session: SessionDep,
    response: Response,
    routine_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Newest first, paged (M50): `limit`/`offset`, total in X-Total-Count.
    The list never carries steps — GET /runs/{id} does. Before M50 this
    returned every run with every step (9.5 MB at 10k runs, M49 baseline)."""
    query = scope_to_user(select(Run), Run)
    if routine_id is not None:
        # §18.5: the routine drawer's run history — trigger provenance match
        query = query.where(Run.trigger["routine_id"].astext == str(routine_id))
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    # the id is the tiebreaker, not decoration: runs created in the same
    # transaction share `started_at` to the microsecond, and an ORDER BY with
    # ties is free to order them differently per query — so a row could
    # appear on two pages, or on none.
    page = query.order_by(Run.started_at.desc(), Run.id.desc()).limit(limit).offset(offset)
    runs = list((await session.execute(page)).scalars())
    response.headers["X-Total-Count"] = str(total)
    costs = await _costs(session, runs)
    return [_run_out(r, cost=costs.get(r.id)) for r in runs]


async def _owned_or_404(session: AsyncSession, run_id: UUID) -> Run:
    """The guard the action endpoints were missing.

    `GET /runs/{id}` and `DELETE /runs/{id}` have always asked `owns_row`;
    cancel, retry and the HITL decision did not, so with auth ON any member
    could resume another member's gate, stop their run, or spend tokens
    retrying it. 404 rather than 403 — the same answer the read paths give,
    so the endpoint does not confirm that a run it will not act on exists."""
    run = await session.get(Run, run_id)
    if run is None or not owns_row(run):
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.delete("", status_code=204)
async def purge_runs(session: SessionDep) -> None:
    """Run-history purge (spec §8.7), scoped to the caller.

    It used to delete unconditionally — `delete(RunStep)`, `delete(Run)`,
    every checkpoint — with no tenancy filter and no admin gate, while
    `_ADMIN_WRITE` (app/auth/builtin.py) covers the registry and settings
    but not `/runs`. With auth ON that made destroying EVERY user's entire
    run history a plain member action. The deferred-ownership note in §18.8
    covers acting on someone else's run; it never covered erasing everyone's.

    Dark (single-user) behaviour is unchanged: the provider's tenancy filter
    is None when auth is off, so the scoped query is every row, and the
    checkpoint sweep stays the unqualified one. That distinction matters —
    §8.7 promises NO RESIDUE, and a per-run sweep only reaches threads whose
    run row still exists. An orphaned checkpoint (its run already deleted,
    or a sub-thread whose parent is gone) is only reachable by the
    unqualified purge, so narrowing it unconditionally would have quietly
    left residue behind on the single-user path the promise was made for."""
    run_ids = list((await session.execute(scope_to_user(select(Run.id), Run))).scalars())
    for run_id in run_ids:
        forget_run_events(run_id)
    if run_ids:
        await session.execute(delete(RunStep).where(RunStep.run_id.in_(run_ids)))
        await session.execute(delete(Run).where(Run.id.in_(run_ids)))
    if tenancy_on():
        # multi-user: only this caller's threads, so another user's paused
        # run keeps the checkpoints it needs to resume
        for run_id in run_ids:
            await _purge_checkpoints(session, run_id)
    else:
        await _purge_checkpoints(session)  # single-user: everything, orphans included
    await session.commit()


@router.get("/{run_id}")
async def get_run(run_id: UUID, session: SessionDep) -> dict[str, Any]:
    run = (
        await session.execute(select(Run).options(selectinload(Run.steps)).where(Run.id == run_id))
    ).scalar_one_or_none()  # M50: the one place the step tree is loaded
    if run is None or not owns_row(run):
        raise HTTPException(status_code=404, detail="run not found")
    costs = await _costs(session, [run])
    return _run_out(run, with_steps=True, cost=costs.get(run.id))


@router.post("/{run_id}/cancel")
async def cancel(run_id: UUID, session: SessionDep) -> Response:
    """M54 (spec §18.9): the response is the run's REAL status. A run
    executing on another replica gets a persisted cancel intent the owner
    acts on; `202 cancel_requested` says the owner has not acted yet."""
    await _owned_or_404(session, run_id)
    try:
        status = await cancel_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(
        {"status": status}, status_code=202 if status == "cancel_requested" else 200
    )


@router.post("/{run_id}/retry", status_code=201)
async def retry(run_id: UUID, session: SessionDep) -> dict[str, Any]:
    await _owned_or_404(session, run_id)
    try:
        new_run = await retry_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"run_id": str(new_run.id), "conversation_id": str(new_run.conversation_id)}


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: UUID, session: SessionDep) -> None:
    run = await session.get(Run, run_id)
    if run is None or not owns_row(run):
        raise HTTPException(status_code=404, detail="run not found")
    if run.status == "running":
        raise HTTPException(status_code=409, detail="cancel the run before deleting it")
    forget_run_events(run_id)
    await session.execute(delete(RunStep).where(RunStep.run_id == run_id))
    await session.delete(run)
    await _purge_checkpoints(session, run_id)
    await session.commit()
