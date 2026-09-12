# Runbook — wedged ambient tick

**What it is.** The ambient loop ticks every `ambient_tick_interval_s` (60 s):
the leader runs the evaluators (schedules, pollers, state probes, wakeups,
the drain, deliveries, retries, salience, learning, the A2A poller) and every
replica drains. Since M50 each stage runs under `run_evaluator` with a
timeout and an error counter, so one stage cannot hang the tick — but a tick
can still be *effectively* wedged: a stage timing out every time, a leader
whose lease session is alive while its process is stuck, or a fire whose
executor never returns.

## The metric that reveals it

| Signal | Healthy | Wedged |
|---|---|---|
| `concierge_backlog_depth{queue="ambient_events"}` | drains to ~0 each tick | climbs tick after tick |
| `concierge_ambient_evaluator_errors_total{evaluator,kind}` | flat | rising for one evaluator (`kind="timeout"` or `"error"`) |
| `concierge_loop_errors_total{loop="ambient"}` | flat | rising — the tick body itself raised |
| `concierge_ambient_ops_total{kind="drain"}` | increments when events exist | stops increasing |
| log `ambient_drain` / `ambient_tick_failed` | `ambient_drain handled=n` | `ambient_tick_failed error=…` or `ambient_evaluator_timeout evaluator=…` |

## First checks

```bash
curl -s http://localhost:8000/metrics | grep -E 'concierge_backlog_depth|concierge_ambient_evaluator_errors_total|concierge_loop_errors_total|concierge_ambient_leader'
docker compose logs --since 10m backend | grep -E 'ambient_(tick_failed|evaluator_timeout|drain)|ambient_leader'
curl -s 'http://localhost:8000/api/v1/ambient/ledger?limit=20'     # pending rows with no verdict?
curl -s http://localhost:8000/api/v1/settings | grep -o '"ambient_enabled": *[a-z]*'
```

Distinguish:

1. **One evaluator times out every tick** — the counter names it (a poll
   source against a dead host, a state probe that hangs). The rest of the
   tick still runs; the backlog grows only if the stuck stage is the drain.
2. **The tick body raises before the evaluators** — `loop="ambient"`
   rises; usually the settings read or the lease (database trouble).
3. **The drain runs but events never finish** — fires queue as runs; see
   `concierge_runs_in_flight{state="queued"}` and the spend ceiling
   (`GET /spend`: `reached: true` holds every fire with the reason on the
   event).
4. **Nobody leads** — `concierge_ambient_leader` is 0 everywhere; see
   [leader-loss.md](./leader-loss.md).

## The action that resolves it

- Cause 1: pause or fix the routine/watch whose source is stuck (Ambient →
  Routines/Watches). The evaluator's timeout is the M50 isolation working;
  the fix is at the source.
- Cause 2: fix the database; the loop survives and resumes on its own.
- Cause 3: raise `run_max_concurrent` / `run_queue_max`, or raise the spend
  ceiling; held events show `spend ceiling: …` in `verdict_reason`.
- A tick wedged for a reason you cannot see: `./deploy.sh` (or
  `docker compose restart backend`) — the lease is released on the way out,
  the next process leads within one tick, events are drained by claim →
  commit → process, so nothing is lost.

## Recovery looks like

`concierge_backlog_depth{queue="ambient_events"}` returns to ~0, the
`ambient_drain` line appears each tick with `handled>0` while there is
work, the evaluator error counter stops rising.
