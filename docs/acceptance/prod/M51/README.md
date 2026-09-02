# M51 — bounded work: executed proof

Every unit of work gets a ceiling and a truthful end state. This directory is
the fault injection the plan's exit criteria ask for — a provider that hangs,
a provider that rate-limits, Redis killed under a live cache mode, a process
stopped and a process killed mid-run — plus the admission proof on the real
model, a soak with the ambient loop live, and the screenshots. Same stack,
rebuilt image, fresh migration; the fake provider (`FAKE_LLM_ENABLED=1`, the
scriptable one the test suite uses) is the fault injector, and the admission
and live samples run on `openrouter:qwen/qwen3.8-max`.

| file | what it is |
|---|---|
| `wall-clock-and-429.md` | §14n-70/71: a scripted 300 s provider answer ends the run at `run_wall_clock_s` (45 s) with the clock named in the error and the heartbeat on record at +30 s; a scripted 429 fails the run with an error that says rate-limited, names the model and the settings in play, and increments `concierge_llm_errors_total{kind="rate_limited"}`; an unknown model is a 422 at validation |
| `admission.md` | §14n-72, live on qwen: `run_max_concurrent=1`, `run_queue_max=0` → the second chat is `503` + `Retry-After: 5` while the first runs; `run_queue_max=2` → the second lands `queued`, shows as such on `/runs` and `/ready`, and completes after the first |
| `restart.md` | §14n-73: SIGTERM with a short and a long run in flight — the drain lets the short one finish (25 s grace) and cancels the long one with "cancelled by shutdown … (drain grace 25s, SHUTDOWN_GRACE_S)"; SIGKILL with two runs in flight — the next boot logs `runs_orphaned_by_restart count=2`, marks them failed "orphaned by a restart", cancels their open steps; zero non-terminal rows after either |
| `redis-fail-open.md` | §14n-74: `registry_cache_mode=redis`, redis container stopped — `/tools`, `/skills`, `/sub-agents`, `/settings` all 200 from Postgres, a run still executes, `concierge_cache_degraded_total{backend="redis"}` = 19, the log names the backend and the error |
| `delivery-retry.md` | §14n-75: the webhook channel pointed at a closed port — the tick dispatches, then commits the row delivered with `external.webhook` = `{ok:false, attempts:1, next_attempt_at:+60s}`; attempt 2 lands on the real clock after the 60 s backoff; the 5-min and 30-min backoffs are skipped by moving `next_attempt_at` (said so in the transcript) and the fourth attempt dead-letters the entry (`dead:true`, `next_attempt_at:null`); a further clock skip changes nothing; `concierge_delivery_sends_total` counts retry/dead |
| `soak.md` / `soak.csv` | the exit criterion "ambient enabled for an extended run with flat RSS": 30 minutes with an interval routine firing every 60 s, a webhook fire every 10 s and a chat run every 30 s on the fake provider, resident memory sampled every 30 s from `/metrics` — 247.7 MB → 264.2 MB in the first five minutes (warm-up), then **+1.1 MB over the final 15 minutes** across 103 runs, file descriptors flat; the webhook fires hit the §17.3a per-routine kill switch at 50/h and were refused with 429 from then on, which the transcript says |
| `live-sample.md` | an ordinary chat on the real model under every bound: heartbeat advanced at +30 s of a 38 s run, answer and token totals recorded |
| `tests.md` | `pytest tests/test_m51_bounded.py -v` — 29 passed, including the three strict-session tests behind §14n-76 |
| `01-runs-page-queued-and-wall-clock.png` | The Runs page: a `queued` run behind a `running` one (`run_max_concurrent=1`), the wall-clock run `failed` at 45.0 s, the drained run `cancelled`, the orphaned runs `failed` |
| `02-settings-api-guardrails.png` | The API guardrails section of Settings with the three M51 keys beside the rate limiter |

## What each fault did before M51

| fault | before | after (this directory) |
|---|---|---|
| provider hangs | the run stayed `running` for as long as the provider took — no timeout at the port, no wall clock, the reaper only covered ambient runs | port timeout `LLM_TIMEOUT_S`; the run ends `failed` at `run_wall_clock_s` with the clock named; a heartbeat every 30 s; the reaper covers every run |
| provider returns 429 | an opaque `RuntimeError: 429 …` in the run, no metric | classified `rate_limited`, the error names the model and the settings that resolved it, `concierge_llm_errors_total{kind}` counts it; the port's retry budget (`LLM_MAX_RETRIES`) backs off first |
| 50 chats at once | 50 tasks immediately, all contending (M49 baseline: latency grew linearly) | `run_max_concurrent` slots, `run_queue_max` visible `queued` rows, explicit 503 + `Retry-After` past that, `/ready` as the gate |
| `docker stop` mid-run | tasks died with the process; rows stayed `running` forever | 25 s drain, the remainder `cancelled` with the shutdown named; the next boot reaps anything still non-terminal |
| Redis dies | a `ConnectionError` out of the cache layer — 500s | served from Postgres, degraded counter, no 5xx |
| webhook sink down | one attempt, `ok:false` ledgered, never retried | attempt counter, backoff 60 s → 5 min → 30 min, dead-letter after 4, a per-tick retry stage bounded to 20 sends |
| memory write / digest / drain | a pooled connection held for the life of a provider round trip (arch-H15/H8) | read → close → call → write in every path; the fake provider's strict mode fails the suite on a regression |

## Reproduce

```bash
FAKE_LLM_ENABLED=1 AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook \
COMPOSE_PROFILES=redis REDIS_URL=redis://redis:6379/0 docker compose up -d --build
# drivers live in the campaign scratchpad; each is a curl/psql transcript against the
# shipped API (see the commands echoed at the top of every .md here)
cd backend && FAKE_LLM_ENABLED=1 pytest tests/test_m51_bounded.py -v
```

Note on readiness during `docker stop`: uvicorn closes the listening socket at
SIGTERM before the lifespan drain runs, so a client polling `/ready` sees
connection-refused rather than the 503 the gate returns; the 503 is what a
pre-stop probe sees, and that deploy-lifecycle hook is M53's.
