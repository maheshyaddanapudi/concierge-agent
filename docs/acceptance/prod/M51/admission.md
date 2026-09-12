# M51 admission drill — 2026-09-10T21:20:55Z — model openrouter:qwen/qwen3.8-max

$ PATCH /settings run_max_concurrent=0 → 422; run_queue_max=-1 → 422; run_wall_clock_s=10 → 422 (floor 30)
{"detail":"run_max_concurrent must be an integer between 1 and 64"} HTTP 422
{"detail":"run_queue_max must be an integer between 0 and 500"} HTTP 422
{"detail":"run_wall_clock_s must be an integer between 30 and 86400 seconds"} HTTP 422

$ PATCH /settings default_model=openrouter:qwen/qwen3.8-max (live), formatter off, run_max_concurrent=1, run_queue_max=0, run_wall_clock_s=900
{'default_model': 'openrouter:qwen/qwen3.8-max', 'run_max_concurrent': 1, 'run_queue_max': 0, 'run_wall_clock_s': 900}
idle after 1s (a lowered run_max_concurrent applies once no run holds the semaphore)

$ POST /chat #1 (live); POST /chat #2 while #1 runs — the queue is 0 deep → 503 + Retry-After
run #1 5ddc6e6e-9484-4e3a-a025-8835c4a44a09 status=queued
HTTP/1.1 503 Service Unavailable
retry-after: 5
{"detail":"server at capacity: 1 running, 0 queued (run_max_concurrent=1, run_queue_max=0) — retry later"}

$ GET /ready during the run
{"status": "ready", "db": "ok", "accepting": true, "running": 1, "queued": 0, "max_concurrent": 1, "draining_since": null}
run #1 → completed after 8s
answer: A semaphore guarantees an upper bound on concurrency: at most N threads may pass its acquire/wait at once (N = 1 for a binary semaphore acting as a mutex), and 

$ PATCH /settings run_queue_max=2 — now the second run waits, visibly
{'run_max_concurrent': 1, 'run_queue_max': 2}
idle after 1s (a lowered run_max_concurrent applies once no run holds the semaphore)

$ POST /chat #1 and #2 back to back (live)
run #1 ef358ea7-09a0-4823-8590-581fe330e2fa status=running
run #2 d577a1a4-0e12-49cf-b468-1f0941352a79 status=queued   ← expected: queued, not running

$ GET /ready with one running and one queued; GET /runs?limit=2 — the queued status is a first-class row
{"status": "ready", "db": "ok", "accepting": true, "running": 1, "queued": 1, "max_concurrent": 1, "draining_since": null}
[('d577a1a4', 'queued'), ('ef358ea7', 'running')]
shot 01-runs-page-queued-and-wall-clock.png
run #1 → completed
run #2 status right after #1 finished: running
run #2 → completed

$ psql: both runs, in order (started_at is the submit time; #2 finishes after #1)
ef358ea7|completed|21:21:06.374|21:21:12.933|Three properties of a bounded queue:

- **Fixed capacity:** it has a maximum number of ele
d577a1a4|completed|21:21:06.424|21:21:20.130|A visible queue is better than a silent one because it exposes observable state — length, 

$ §14n-70 the wall clock: a run that outlives run_wall_clock_s ends failed with the clock named; the heartbeat advanced at 30 s; no step left running
PATCH → run_wall_clock_s 30 (no fake provider on this backend: a 1500-word essay on the live model outlives 30 s)
run 68174e38-ec29-40f1-85ef-77a0ed4992ad → failed after 31s
{'status': 'failed', 'error': 'exceeded the run wall clock (30s, run_wall_clock_s) — terminated', 'started_at': '2026-09-10T21:21:20.492623+00:00', 'finished_at': '2026-09-10T21:21:50.525316+00:00'}
failed|21:21:20|heartbeat 21:21:50|21:21:50|30s
plan|cancelled
concierge_runs_total{mode="graph",status="failed"} 1.0

(the provider-429 classification needs the fake provider on the backend — docs/acceptance/prod/M51/wall-clock-and-429.md)

$ the API limiter's own 429: rate_limit_burst=5, rate_limit_per_s=1, then 12 GET /settings in a burst (the M40 limiter answers a bare 429 — no Retry-After; that header is the admission 503's and the spend 429's)
{'rate_limit_burst': 5, 'rate_limit_per_s': 1}
200 200 200 200 200 200 200 200 200 200 200 200 
HTTP/1.1 200 OK
restored rate_limit_burst=120 rate_limit_per_s=10 (after 1 attempt(s))

$ PATCH /settings default_model=openrouter:qwen/no-such-model → 422 (unknown model refused at validation)
{"detail":"default_model: model 'qwen/no-such-model' is not in provider 'openrouter''s model list"} HTTP 422

$ restore defaults: run_max_concurrent=8 run_queue_max=32 run_wall_clock_s=900
{'run_max_concurrent': 8, 'run_queue_max': 32, 'run_wall_clock_s': 900}
shot 02-settings-api-guardrails.png
# end — 2026-09-10T21:22:03Z
