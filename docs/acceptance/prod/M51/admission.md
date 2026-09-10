# §14n-72 — admission is explicit (live on openrouter:qwen/qwen3.8-max)

Real model, real latency: with `run_max_concurrent=1` and `run_queue_max=0` a second chat is shed with 503 + Retry-After while the first runs; with `run_queue_max=2` the second lands `queued`, is visible as such on `/runs` and `/ready`, and runs when the slot frees. Captured by `m51-fault.sh` (admission section).

```text
$ PATCH /settings default_model=openrouter:qwen/qwen3.8-max (live), run_max_concurrent=1, run_queue_max=0, run_wall_clock_s=900
{'default_model': 'openrouter:qwen/qwen3.8-max', 'run_max_concurrent': 1, 'run_queue_max': 0}

$ PATCH /settings run_max_concurrent=0 → 422; run_queue_max=-1 → 422
{"detail":"run_max_concurrent must be an integer between 1 and 64"} HTTP 422
{"detail":"run_queue_max must be an integer between 0 and 500"} HTTP 422

$ POST /chat #1 (qwen, live)
run_id=f96f37bb-b0b1-40be-925f-5f630aba1cd3  status=running

$ POST /chat #2 while #1 runs — the queue is 0 deep
HTTP/1.1 503 Service Unavailable
retry-after: 5
{"detail":"server at capacity: 1 running, 0 queued (run_max_concurrent=1, run_queue_max=0) — retry later"}
$ GET /ready during the run
{"status": "ready", "accepting": true, "running": 1, "queued": 0, "max_concurrent": 1}
→ completed after 12s
{'status': 'completed'}
answer: A semaphore bounds the number of concurrent threads or processes that may access a shared resource at the same time. It enforces this with a fixed pool of permits: a thread must acquire one to proceed, and once all permits are taken, further threads block until one is released.

$ PATCH /settings run_queue_max=2 — now the second run waits, visibly
{'run_max_concurrent': 1, 'run_queue_max': 2}

$ POST /chat #1 and #2 back to back (qwen, live)
run #1 48f01e63-a7da-4d1d-965a-54b7f877fa74 status=running
run #2 f3c59849-fecd-443d-9f19-d3aec171a644 status=queued   ← queued, not running

$ GET /ready with one running and one queued
{"status": "ready", "accepting": true, "running": 1, "queued": 1, "max_concurrent": 1}

$ GET /runs?limit=2 — the queued status is a first-class row
[('f3c59849', 'queued'), ('48f01e63', 'running')]
→ completed after 10s
run #2 status right after #1 finished: running
→ completed after 11s

$ both runs, in order
48f01e63|completed|23:56:55.494|23:57:04.604|1. Fixed capacity — it has a maximum size; enqueue attempts block or fail once full.
2. FIFO ordering — elements are rem
f3c59849|completed|23:56:55.544|23:57:14.796|A visible queue is better because it makes progress tangible and the wait predictable — people can see the line moving, 

$ restore defaults: run_max_concurrent=8 run_queue_max=32
{'run_max_concurrent': 8, 'run_queue_max': 32}
```
