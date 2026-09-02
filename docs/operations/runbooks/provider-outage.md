# Runbook — provider outage

**What it is.** Every model call goes through the provider port with a
timeout (`LLM_TIMEOUT_S`, 120 s) and a retry budget (`LLM_MAX_RETRIES`, 2).
When a provider degrades, calls slow down to the timeout, retries spend the
budget, and runs fail with a classified error — `rate_limited`, `timeout`,
`unknown_model` (a retired or misspelled model) or `provider_error` — that
names the model and the setting that resolved it. Since M53 the same
classes label the per-call metrics, so the outage is visible before a user
reports it.

## The metric that reveals it

| Signal | Healthy | Outage |
|---|---|---|
| `rate(concierge_llm_calls_total{status!="ok"}[5m])` by `provider`,`model` | ~0 | rising; the `status` says which kind |
| `histogram_quantile(0.95, rate(concierge_llm_latency_seconds_bucket[5m]))` | seconds | climbing to `LLM_TIMEOUT_S` (a hang) or falling to ~0 (an immediate 4xx/5xx) |
| `concierge_llm_errors_total{kind}` | flat | rising (runs that failed on the class) |
| `concierge_runs_total{status="failed"}` | rare | rising in step with the above |
| `concierge_runs_in_flight{state="running"}` | turning over | pinned at the slot ceiling for `LLM_TIMEOUT_S` × retries |
| run `error` text | — | `provider rate-limited (429) after the port's retry budget — … (model settings in play: default_model=…)` |

## First checks

```bash
curl -s http://localhost:8000/metrics | grep -E 'concierge_llm_(calls|errors)_total'
curl -s http://localhost:8000/api/v1/providers | python3 -m json.tool | grep -E '"provider_id"|"configured"'
curl -s 'http://localhost:8000/api/v1/runs?limit=5' | python3 -c "import sys,json;[print(r['status'], (r['error'] or '')[:120]) for r in json.load(sys.stdin)]"
curl -s http://localhost:8000/api/v1/spend        # a reached ceiling refuses runs too (429), but at admission, not at the provider
```

Distinguish by `status`:

- `rate_limited` — quota or concurrency limit at the provider; every
  retry already backed off.
- `timeout` — the provider hangs; the port cut the call at `LLM_TIMEOUT_S`.
- `unknown_model` — the model was retired or the ref is misspelled; this
  never recovers on its own.
- `provider_error` — an auth failure, a 5xx, a network error; the run's
  error text (sanitized) says which.

## The action that resolves it

- `rate_limited` / `timeout` / `provider_error`: **switch the role model** —
  Settings → Models: `default_model` (and the planner/aggregator/formatter
  overrides if set) to another configured provider. Settings apply to the
  next run, no restart; ambient routines with their own `model_ref`
  override it and need their own change. Lower `run_max_concurrent` while
  the provider recovers so fewer runs spend the timeout.
- `unknown_model`: pick a current model — the Settings save validates the
  ref and refuses a retired one (M51).
- Runs that failed are `failed`, not lost: retry them from the Runs page
  once the provider is back.

## Recovery looks like

`status="ok"` dominates `concierge_llm_calls_total` again, p95 latency
returns to its baseline, `concierge_runs_total{status="completed"}` grows.
