"""Startup audit: routines whose allowlist is narrower than their own history
(spec §17.4, code_setting_ui_hardening).

A routine's allowlist is a ceiling on what its run may reach, and this wave
made that ceiling real in both orchestrator modes — the planner catalog and
all three registry middlewares filter through `apply_ambient_allowlist`, and
the resolution ladder refuses an entry outside it even when a checkpoint or
a pinned plan names one.

That is the right behavior and it is also a silent behavior change for any
routine whose allowlist was written when it was decorative. Such a routine
does not fail loudly at boot; it fails the next time it fires, inside an
autonomous run nobody is watching. So at startup we read what each routine's
recent runs ACTUALLY used and name the ones the new ceiling would have
refused — once, at boot, with the entries listed, so an operator can widen
the allowlist before the routine next wakes up rather than after.

Read-only and best-effort: it logs, it never edits a routine, and a failure
here never delays or fails boot.
"""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from app.db import get_session_factory
from app.models import Routine, Run, RunStep

logger = structlog.get_logger("ambient")

# how many recent runs per routine to read back. Enough to catch a routine
# that uses a tool occasionally, small enough that boot stays cheap.
RUNS_PER_ROUTINE = 20

# which step types name a registry entry the allowlist governs, and under
# which allowlist kind it falls (the same three kinds the projection uses)
_STEP_KIND = {"tool_call": "tools", "skill": "skills", "sub_agent": "sub_agents"}


def _allowed_set(allowlist: dict[str, Any] | None, kind: str) -> set[str] | None:
    """None means "this kind is unconstrained" — the same rule the runtime
    projection applies, so the audit cannot warn about something that would
    not actually be refused."""
    if not isinstance(allowlist, dict):
        return None
    allowed = allowlist.get(kind)
    if allowed is None:
        return None
    return {str(a) for a in allowed}


async def narrower_than_history() -> list[dict[str, Any]]:
    """Returns one entry per routine whose allowlist would refuse something
    its own recent runs used: {routine_id, routine_name, kind, entries}."""
    findings: list[dict[str, Any]] = []
    async with get_session_factory()() as session:
        routines = list(
            (
                await session.execute(
                    select(Routine).where(
                        Routine.status == "active", Routine.allowlist.is_not(None)
                    )
                )
            ).scalars()
        )
        for routine in routines:
            if not any(_allowed_set(routine.allowlist, k) is not None for k in _STEP_KIND.values()):
                continue  # an allowlist that constrains no kind constrains nothing
            run_ids = list(
                (
                    await session.execute(
                        select(Run.id)
                        .where(Run.trigger["routine_id"].astext == str(routine.id))
                        .order_by(Run.started_at.desc())
                        .limit(RUNS_PER_ROUTINE)
                    )
                ).scalars()
            )
            if not run_ids:
                continue
            steps = list(
                (
                    await session.execute(
                        select(RunStep.step_type, RunStep.entity_name, RunStep.node_id).where(
                            RunStep.run_id.in_(run_ids),
                            RunStep.step_type.in_(list(_STEP_KIND)),
                        )
                    )
                ).all()
            )
            used: dict[str, set[str]] = {}
            for step_type, entity_name, node_id in steps:
                # entity_name is what the step ran against, pinned at the
                # time; node_id is the fallback for rows written before it
                name = entity_name or (node_id or "").split(".")[-1]
                if name:
                    used.setdefault(_STEP_KIND[step_type], set()).add(name)
            for kind, names in used.items():
                allowed = _allowed_set(routine.allowlist, kind)
                if allowed is None:
                    continue
                missing = sorted(n for n in names if n not in allowed)
                if missing:
                    findings.append(
                        {
                            "routine_id": str(routine.id),
                            "routine_name": routine.name,
                            "kind": kind,
                            "entries": missing,
                        }
                    )
    return findings


async def log_narrow_allowlists() -> int:
    """Boot hook. Never raises — an audit that fails must not fail the boot
    it is auditing. Returns the number of findings logged."""
    try:
        findings = await narrower_than_history()
    except Exception as exc:  # noqa: BLE001 — advisory only
        logger.warning("ambient_allowlist_audit_failed", tier="ambient", error=str(exc))
        return 0
    for finding in findings:
        logger.warning(
            "ambient_allowlist_narrower_than_history",
            tier="ambient",
            kind="allowlist_audit",
            entity_id=finding["routine_id"],
            entity_name=finding["routine_name"],
            allowlist_kind=finding["kind"],
            entries=finding["entries"],
            detail=(
                f"routine {finding['routine_name']!r} used "
                f"{', '.join(finding['entries'])} in its recent runs, but its "
                f"allowlist does not name them under {finding['kind']}. The "
                "allowlist is enforced now, so the next fire will be refused "
                "these — widen it or expect the refusal."
            ),
        )
    return len(findings)


async def audit_routine(routine_id: UUID) -> list[dict[str, Any]]:
    """Single-routine form, for the API and the tests."""
    return [f for f in await narrower_than_history() if f["routine_id"] == str(routine_id)]
