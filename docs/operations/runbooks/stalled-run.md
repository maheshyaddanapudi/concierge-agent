# Runbook — runs stalling or hitting the wall clock

**What it is.** Two different ceilings end a run that will not finish, and
telling them apart is the whole job of this page.

- **The wall clock** (`run_wall_clock_s`, 900 s) is a timeout the runner
  wraps around the run body. Past it the run ends **`failed`** with the
  clock and the setting named in its `error`:
  `exceeded the run wall clock (900s, run_wall_clock_s) — terminated`.
  The process was alive and working the whole time — the work was just too
  long.
- **The stall reaper** (`run_stall_after_s`, 300 s) watches
  `runs.last_heartbeat_at`, which the runner refreshes every 30 s from
  inside the run's own task. A run whose heartbeat goes silent for longer
  than the window ends **`stalled`** with
  `stalled: no heartbeat for over 300s`. That means the task is **gone or
  wedged** — the loop is not running it any more — which is a different
  failure from "this is slow".

Since M51 the reaper covers **every** run kind, not just ambient ones, and
since M53 it routes the run through the same `_finalize_failure` path as
every other terminal status: open steps close, the run is priced, the
terminal event reaches any open SSE stream, and — for an ambient run — the
owning **routine is auto-paused** with the reason on the row.

## The metric that reveals it

| Signal | Wall clock | Stalled |
|---|---|---|
| run `status` | `failed` | `stalled` |
| run `error` | `exceeded the run wall clock (Ns, run_wall_clock_s) — terminated` | `stalled: no heartbeat for over Ns` |
| `concierge_runs_total{status}` | `failed` steps up | `stalled` steps up |
| `concierge_run_duration_seconds{status}` | a sample at ≈ `run_wall_clock_s` | a sample at ≈ `run_stall_after_s` |
| `concierge_ambient_ops_total{kind="stall",status="reaped"}` | flat | increments once per reaped run |
| log | — | WARNING `ambient_run_stalled` with `run_id` (the event name is historical — it fires for chat runs too) |
| routine side effect | none | an ambient run's routine flips to `paused` with `auto-paused: run <id> stalled (no heartbeat)` |

Related and different: `concierge_runs_in_flight{state="queued"}` at
`run_queue_max` with `{state="running"}` at `concierge_run_slots` is
**admission**, not a stall — runs are waiting for a slot, and `POST /chat`
sheds with 503 + `Retry-After`. And a run reaped at **boot** ends `failed`
with `orphaned by a restart`, while a run whose owning replica died ends
`failed` with `owner replica gone` (`runs_reaped_dead_owner` in the
survivors' logs) — see [dead-replica.md](./dead-replica.md).

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/metrics" \
  | grep -E 'concierge_runs_total|concierge_runs_in_flight|concierge_run_slots|kind="stall"'
docker compose logs --since 2h backend \
  | grep -E 'ambient_run_stalled|runs_reaped_dead_owner|orphaned by a restart'

# which ceiling, and how often
docker compose exec db psql -U concierge -d concierge -c \
  "select status, count(*), min(started_at), max(started_at), left(max(error),90) sample
     from runs where started_at > now() - interval '24 hours'
       and status in ('failed','stalled') group by 1;"

# the shape of the runs that hit it: where did they stop?
docker compose exec db psql -U concierge -d concierge -c \
  "select r.id, r.orchestrator_mode, r.trigger->>'routine_id' routine,
          count(s.id) steps, max(s.step_type) last_type,
          extract(epoch from (r.finished_at - r.started_at)) secs
     from runs r left join run_steps s on s.run_id = r.id
     where r.status in ('failed','stalled') and r.started_at > now() - interval '24 hours'
     group by 1,2,3,6 order by 6 desc limit 10;"

# routines the reaper paused
docker compose exec db psql -U concierge -d concierge -c \
  "select id, name, status, status_reason from routines where status='paused';"

curl -s "http://localhost:${PORT}/api/v1/settings" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:d[k] for k in ("run_wall_clock_s","run_stall_after_s","run_max_concurrent","run_queue_max","max_tool_iterations","agentic_recursion_limit") if k in d})'
# `LLM_TIMEOUT_S` is an env var, not a setting — it is not in /settings.
# Read it off the container: docker compose exec backend printenv LLM_TIMEOUT_S
```

Distinguish:

1. **Wall clock, legitimately slow work** — the run has many completed steps,
   a long tool loop or a big fan-out, and the duration sits right at
   `run_wall_clock_s`. The ceiling did its job.
2. **Wall clock, a loop that will not converge** — the tail of the steps is
   the same `tool_call` over and over, or an agentic loop re-planning. Check
   `max_tool_iterations` (global, and the per-skill override on
   `skills.max_tool_iterations`) and `agentic_recursion_limit`.
3. **Wall clock, a provider that is not answering** — few steps, the last one
   `running` for minutes, `concierge_llm_latency_seconds` p95 at
   `LLM_TIMEOUT_S`, `concierge_llm_errors_total{kind="timeout"}` climbing.
   That is [provider-outage.md](./provider-outage.md), surfacing as a wall
   clock.
4. **Stalled, the task died** — the run has steps that stop abruptly with no
   error, the process logged an unhandled exception or was OOM-killed
   (`docker compose ps` shows a restart, `docker inspect` an `OOMKilled`
   flag). The heartbeat stopped because nothing was running.
5. **Stalled, the event loop was blocked** — several runs stall at the same
   moment across the replica, and the heartbeat (a 30 s task) missed its
   window too. Something ran synchronously on the loop: a large regex (the
   §M52 guard runs matching off the loop precisely for this), a big JSON
   parse, a blocking driver call.
6. **Stalled at the window, not at the work** — `run_stall_after_s` is close
   to a legitimate gap in the run. A run paused at HITL does **not** stall
   (the reaper only looks at `running` rows), but a step that legitimately
   takes longer than the window between heartbeats does not exist — the
   heartbeat is 30 s and independent of step boundaries, so this should not
   happen; if it does, treat it as cause 5.

## The action that resolves it

- Cause 1: raise `run_wall_clock_s` (Settings → API guardrails) to fit the
  work, and expect the run to hold an admission slot that whole time —
  budget `run_max_concurrent` accordingly. `POST /runs/{id}/retry` re-plans a
  failed run; the retry preserves the trigger, allowlist, model pin, owner
  and project.
- Cause 2: lower the loop budget so it fails fast and visibly, or fix the
  skill's instructions. A skill that loops is usually one whose bound tool
  set cannot actually finish the task — the trace's repeated `tool_call`
  names it.
- Cause 3: see the provider runbook; the wall clock is the messenger.
- Cause 4: read the process logs for the real cause; raise the container
  memory limit if it was OOM. Restart reaps anything left `running` as
  `failed` with `orphaned by a restart`, so nothing is left lying.
- Cause 5: find the blocking call. `concierge_step_duration_seconds` with a
  long tail on a step that does no I/O is the tell.
- **A paused routine stays paused on purpose.** Un-pause it deliberately
  (`PATCH /routines/{id}` `status: "active"`, clearing `status_reason`) once
  you know why its run stalled — that is the point of the auto-pause: a
  routine that stalls once will usually stall every tick.
- Tuning note: keep `run_stall_after_s` comfortably above the 30 s heartbeat
  interval (its floor is 60 s) and **below** `run_wall_clock_s`, so a dead
  task is reaped as `stalled` rather than waiting out the wall clock.

## Recovery looks like

`concierge_runs_total{status="stalled"}` flat, no new `ambient_run_stalled`
lines, `concierge_runs_in_flight{state="running"}` tracking real work rather
than sitting at the ceiling, `concierge_run_duration_seconds` samples spread
across their real range instead of piling at `run_wall_clock_s`, and no
routines in `paused` with an `auto-paused:` reason.
