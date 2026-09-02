# Runbooks — one page per failure class

Each page names the **metric that reveals** the failure, the **first
checks**, the **action that resolves** it, and what a clean recovery looks
like. They are grounded in the M53 signals on `/metrics` (`docs/observability.md`)
and the operator surfaces the Settings page exposes.

| Failure class | Page | Reveals itself as |
|---|---|---|
| Database pool exhaustion | [pool-exhaustion.md](./pool-exhaustion.md) | `concierge_db_pool_saturation` at 1.0, `/ready` `degraded`, requests waiting `DB_POOL_TIMEOUT` then failing |
| Wedged ambient tick | [wedged-tick.md](./wedged-tick.md) | `concierge_backlog_depth` climbing, `concierge_ambient_evaluator_errors_total` or `concierge_loop_errors_total{loop="ambient"}` rising, no `ambient_drain` log line |
| Leader loss | [leader-loss.md](./leader-loss.md) | `concierge_ambient_leader` 0 on every replica, evaluators silent while fires queue |
| Provider outage | [provider-outage.md](./provider-outage.md) | `concierge_llm_calls_total{status!="ok"}` rate, `concierge_llm_latency_seconds` p95 at `LLM_TIMEOUT_S`, runs failing with a classified error |
| Delivery backlog | [delivery-backlog.md](./delivery-backlog.md) | `concierge_backlog_depth{queue="deliveries"}` climbing, `concierge_delivery_sends_total{status="retry"|"dead"}` |

Related: the day-2 procedures in [`../runbook.md`](../runbook.md), the
deploy lifecycle in [`../scaling.md`](../scaling.md), and the restore drill
in [`../backup-restore.md`](../backup-restore.md).
