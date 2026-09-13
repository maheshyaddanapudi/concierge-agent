# Runbooks — one page per failure class

Each page names the **metric that reveals** the failure, the **first
checks**, the **action that resolves** it, and what a clean recovery looks
like. They are grounded in the signals on `/metrics` ([../../observability.md](../../observability.md))
and the operator surfaces the Settings page exposes. Every metric name, log
event and setting named on these pages is one that exists in the code —
where a signal an operator would want does **not** exist, the page says so
under a "Known gap" heading rather than inventing one.

Commands assume `docker compose`. The backend's published host port comes
from `BACKEND_PORT_RANGE` (one per replica), so the snippets ask
`docker compose port backend 8000` rather than assume `8000`; to address a
scaled replica use `docker compose exec --index=N backend …` — `backend-1`
is a *container* name and `exec` takes a *service*.

| Failure class | Page | Reveals itself as |
|---|---|---|
| Database pool exhaustion | [pool-exhaustion.md](./pool-exhaustion.md) | `concierge_db_pool_saturation` at 1.0, `/ready` `degraded`, requests waiting `DB_POOL_TIMEOUT` then failing |
| Wedged ambient tick | [wedged-tick.md](./wedged-tick.md) | `concierge_backlog_depth` climbing, `concierge_ambient_evaluator_errors_total` or `concierge_loop_errors_total{loop="ambient"}` rising, no `ambient_drain` log line |
| Leader loss | [leader-loss.md](./leader-loss.md) | `concierge_ambient_leader` 0 on every replica, evaluators silent while fires queue |
| Provider outage | [provider-outage.md](./provider-outage.md) | `concierge_llm_calls_total{status!="ok"}` rate, `concierge_llm_latency_seconds` p95 at `LLM_TIMEOUT_S`, runs failing with a classified error |
| Delivery backlog | [delivery-backlog.md](./delivery-backlog.md) | `concierge_backlog_depth{queue="deliveries"}` climbing, `concierge_delivery_sends_total{status="retry"}` then `{status="dead"}` |
| A replica died (M54) | [dead-replica.md](./dead-replica.md) | a `replicas` row with a frozen `heartbeat_at` (`GET /replicas` → `live: false`), `runs_reaped_dead_owner` in the survivors' logs, a Prometheus target down |
| Spend ceiling reached | [spend-ceiling.md](./spend-ceiling.md) | `concierge_spend_ceiling_refusals_total{kind}` climbing, `POST /chat` 429 + `Retry-After`, `GET /spend` → `ceiling.reached: true`, `spend_ceiling_refused` / `ambient_fire_held_spend_ceiling` in the log |
| An MCP server's circuit is open | [mcp-circuit-open.md](./mcp-circuit-open.md) | `concierge_mcp_servers{state="circuit_open"}` ≥ 1 with `{state="reconnecting"}` 0, `mcp_circuit_open` in the log, the row `error` with "reconnect manually" |
| A LISTEN connection is down | [listener-down.md](./listener-down.md) | `concierge_listener_connected{channel}` 0, `listener_lost` / `listener_connect_failed`, registries staying `dirty` in `GET /cache/status` |
| The checkpointer is unavailable | [checkpointer-outage.md](./checkpointer-outage.md) | runs failing at their first step with a psycopg error, `POST /runs/{id}/hitl` 500 on a paused run — while `/ready` still reads 200 |
| Redis is down at runtime | [redis-outage.md](./redis-outage.md) | `concierge_cache_degraded_total{backend="redis"}` climbing, `cache_backend_degraded` in the log — reads fall through to Postgres, nothing fails |
| The embedding backfill is not finishing | [embedding-backfill-stuck.md](./embedding-backfill-stuck.md) | outstanding rows in `GET /memories/status` flat across hours, no `memory_embedding_backfill` line, or `memory_backfill_dims_unsupported` |
| Runs stalling or hitting the wall clock | [stalled-run.md](./stalled-run.md) | runs ending `stalled` ("no heartbeat for over Ns") or `failed` ("exceeded the run wall clock"), `ambient_run_stalled` in the log, routines auto-paused |

Related: the day-2 procedures in [`../runbook.md`](../runbook.md), the
deploy lifecycle in [`../scaling.md`](../scaling.md), and the restore drill
in [`../backup-restore.md`](../backup-restore.md).
