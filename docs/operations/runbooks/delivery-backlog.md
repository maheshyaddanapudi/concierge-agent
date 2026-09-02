# Runbook — delivery backlog

**What it is.** Everything ambient wants a human to see is a `deliveries`
row: the flush (each leader tick) delivers tier-0/1 rows at once and tier-2
rows at the digest times, then fans out to the in-app stream and the
external channels (`ambient_channels`). Since M51 an external send that
fails is retried with backoff (60 s → 5 min → 30 min) and dead-lettered after
the budget; the in-app outbox is the source of truth either way. A backlog
is rows that stay `delivered_at IS NULL` for longer than their tier allows.

## The metric that reveals it

| Signal | Healthy | Backlog |
|---|---|---|
| `concierge_backlog_depth{queue="deliveries"}` | near 0 between digests | climbing across ticks |
| `concierge_delivery_sends_total{channel,status="retry"}` | occasional | rising; `status="dead"` appearing |
| `concierge_ambient_ops_total{kind="deliver"}` | increments each tick with work | flat |
| `concierge_ambient_leader` | 1 somewhere | 0 — no flush without a leader |
| `GET /api/v1/deliveries/unread-count` | small | large `count` with old `created_at` |

Not a backlog: rows held by **quiet hours**, the **notification budget**
(`ambient_notification_budget_per_day`) or **pursuit** (`ambient_pursuit`) —
those are the policy working; the ledger says so.

## First checks

```bash
curl -s http://localhost:8000/metrics | grep -E 'concierge_backlog_depth|concierge_delivery_sends_total|concierge_ambient_leader'
curl -s 'http://localhost:8000/api/v1/deliveries?pending=true&limit=20'
docker compose logs --since 15m backend | grep -E 'ambient_(deliver|delivery_send_failed|delivery_dead)'
curl -s http://localhost:8000/api/v1/settings | grep -oE '"ambient_(channels|quiet_hours|digest_times|pursuit|notification_budget_per_day)": *[^,]*'
```

Distinguish:

1. **No flush is running** — leader gauge 0 or the tick wedged; see
   [leader-loss.md](./leader-loss.md) / [wedged-tick.md](./wedged-tick.md).
2. **External channel failing** — `status="retry"` rising for one channel;
   the in-app rows ARE delivered (the badge and inbox show them), only the
   external copy lags. The log names the sanitized error (SMTP refused,
   webhook 5xx, egress refused).
3. **Policy holding rows** — quiet hours in `ambient_timezone`, a spent
   notification budget, or tier-2 rows waiting for the next digest time.

## The action that resolves it

- Cause 1: restore the leader / unwedge the tick; the flush catches up in
  one tick (dispatch-then-commit, nothing is double-sent).
- Cause 2: fix the channel (`SMTP_*`, `AMBIENT_WEBHOOK_URL`, the egress
  allowlist for an internal sink) — env changes need a rolling deploy —
  or remove the channel from `ambient_channels` to stop the retries. Rows
  already dead-lettered (`external.<channel>.dead=true`) are not retried
  again; resend by hand if they mattered.
- Cause 3: nothing, or change the policy: widen quiet hours, raise the
  budget, add a digest time.
- A backlog of *processed* history rather than pending rows is retention's
  job: Settings → Retention (`retention_deliveries_enabled`, born off).

## Recovery looks like

`concierge_backlog_depth{queue="deliveries"}` returns to its between-digest
baseline, `status="ok"` sends resume on the channel, no new `dead` rows.
