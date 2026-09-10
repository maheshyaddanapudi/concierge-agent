# M53 — deploy and operate: executed proof

The wave where the system becomes something an operator can deploy, watch
and trim. Every §14p item (83–90) was driven on the shipped stack — the
image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`,
ambient on with the M51 soak routine still firing in the background — from
sandbox drivers made of `curl`, `psql`, `docker compose` and one Playwright
script. Transcripts are verbatim. Three of the drills found defects that
were fixed in this wave and re-run (the honest notes at the end).

| file | what it is |
|---|---|
| `deploy-drill.md` | §14p-83 (live model): three chat runs with a stream client each, then `deploy.sh`. `/ready` reads 503 `draining` 0.5 s after `SIGUSR1` while the port is still open, the old port closes ~1 s later, the new process is `/ready` 200 at +37 s (the script returns after 40.3 s). Every client reconnects with `Last-Event-ID=3`, receives ids 4/5 from the record (`replayed_from: "record"`), folds zero duplicates; one run completed inside the drain, two ended `cancelled by shutdown … retry it` (the 10 s drain is shorter than a research run — the truthful outcome, not a lie of "completed"); no row left running or queued; the new process acquired the leader lease 5 s after start |
| `browser-deploy.md` + `08-chat-stream-before-deploy.png`, `09-chat-stream-after-deploy.png`, `10-chat-follow-up-after-deploy.png` | §14p-83 as the browser sees it: the Chat page streaming a research run through the nginx proxy, `deploy.sh` rolling the backend under it. The browser's own reconnect (`Last-Event-ID: 3`) meets the proxy's 502 and `EventSource` gives up; the client reopens with `?after=3` every 5 s through six more 502s, the seventh attempt reaches the new process and gets the record (`run_status: cancelled`); the cancelled card is rendered 2 s after `deploy.sh` returned with the Stop button gone, and a follow-up in the same conversation is answered by the new process 8 s later. The first pass of this drill caught the client defect described below |
| `readiness.md` | §14p-84: `docker compose pause db` → `/ready` 503 `degraded` in 2.0 s with the failure named in `db`, `/health` 200 throughout; unpause → 200. `SIGUSR1` → 503 `draining`, `/health` 200, `POST /chat` 503 with `Retry-After: 10`; a stream on a run this process is not executing gets `event: reconnect` + `retry: 5000` and closes; a stream on a run completed by an earlier process is served from the record (ids continue at 4) and ends without a hint; `--force-recreate` replaces the drained process, `/ready` 200 in 5 s |
| `retention.md` | §14p-85: one finished and one protected row per table, aged 400 days. `GET /retention` counts one eligible row per table regardless of the gates; `POST /retention/run` with the gates as shipped deletes only the expired session (the one gate born on); with every gate on it deletes exactly one row per table and the protected rows (a pending event, an undelivered delivery, the live policy, an armed timer, a parked task, a live session) survive; `concierge_retention_deleted_total{table}` counts each; `retention_deliveries_days=0` is a 422 |
| `metrics.md` + `load-and-dashboards.md` + `05-grafana-saturation.png`, `06-grafana-llm.png` | §14p-86: a scripted 429 on the fake provider fails the run with the port's classification and shows as `concierge_llm_calls_total{provider="fake",model="scripted",status="rate_limited"}`; the step series carry `model` and `effort`; pool, in-flight, slots, backlog, MCP, listener, SSE and spend gauges on `/metrics`. Then Prometheus + Grafana from `docs/observability/` on the stack's network: six chats on the live model under `run_max_concurrent=3` show `running 3 / queued 3 / slots 3` draining over ~20 s, `max_over_time(queued[10m]) = 3`, p95 latency and per-model call rates on the LLM dashboard, `concierge_spend_usd_today 0.363` published by the periodic tick on a process that was 2 minutes old |
| `mcp-reconnect.md` | §14p-87: the seeded `fetch` server's process killed with `SIGKILL` inside the container — the 30 s health ping marks it `error | health ping failed`, the reconnect brings it back `active` 5 s later, `mcp_ping_failed → mcp_reconnect_scheduled → mcp_tools_ingested → mcp_reconnected` in the log, `concierge_mcp_reconnects_total{outcome="ok"} 1`. A server whose command is `/bin/false` with `mcp_reconnect_max_attempts=2` trips the breaker after two attempts — the row says `circuit open after 2 failed reconnect attempts … reconnect manually`, `concierge_mcp_servers{state="circuit_open"} 1` — and the operator's `POST …/reconnect` resets it. Re-ingest keeps intent: a tool set `inactive` stays inactive across `refresh-tools`; a soft-deleted tool stays deleted across `reconnect`; `POST /tools/{id}/restore` brings it back |
| `listen.md` | §14p-88: both supervised LISTEN sessions (named `concierge-listen:<channel>` in `pg_stat_activity`) terminated with `pg_terminate_backend` — `concierge_listener_connected{channel}` reads 0 at t+1 s and 1 at t+2 s for both, `concierge_listener_reconnects_total{channel} 1` each, `listener_lost → listener_started → listener_reconnected → cache_listener_reconnected` in the log, new pids. A routine fired after the gap is drained in **152 ms** — the wake NOTIFY is heard on the fresh session; the tick alone would have taken `ambient_tick_interval_s` (15 s) |
| `spend-ceiling.md` | §14p-89: `/spend` prices the day's live-model runs from OpenRouter's published price ($0.258 across 217 runs, split chat/ambient); each run carries `cost_usd`. A price override plus a $0.0001 ceiling with the gate on: `POST /chat` is a 429 with `Retry-After: 3600` naming the ceiling; an ambient fire is **held** on its event with `spend ceiling: …` as the reason; `concierge_spend_ceiling_refusals_total{kind}` counts one of each; gate off → the same `POST /chat` is a 201 that completes at $0.002 |
| `restore-drill.md` | §14p-90: 248 runs / 412 pgvector embeddings dumped by `backup.sh` in 4 s (2.1 MB), the volume destroyed, a fresh stack seeded on the empty volume (20 s, the reference conversation a 404), then `restore.sh`: `pg_restore` 1 s, **RTO 10 s** stop → restore → `/ready` 200; every row count identical, both pgvector indexes present, `GET /conversations/{id}` byte-identical before and after, both seeded MCP servers active. Numbers also in `docs/operations/backup-restore.md` |
| `01-settings-retention-gates.png` | Settings → Retention: six gates, six windows, live eligible counts, "Run retention now" |
| `02-settings-cost-and-ceiling.png` | Settings → Cost: spend today by kind, the ceiling gate and amount, the price-override JSON |
| `03-settings-mcp-reconnect.png` | Settings → MCP: auto-reconnect gate, max attempts, health interval, Reconnect all / Refresh all tools |
| `04-runs-cost-column.png` | Runs: the cost column, priced from captured usage per run |
| `07-tools-page.png` | Tools after the drills: no deleted rows left, the restore path exercised in `mcp-reconnect.md` |
| `tests.md` | the M53 contract suite and the frontend suite, executed |

## What the drills found and what changed because of them

- **The browser gave up on a roll.** The first browser pass ended with the
  run stuck "running" — Stop button still up — after the deploy. The Python
  harness reconnects on its own; `EventSource` does not survive an **HTTP
  error**: while the backend container is recreated the frontend proxy
  answers 502, the browser marks the source `CLOSED` and never retries, and
  a fresh `EventSource` carries no `Last-Event-ID`. `streamRun` now reopens
  the stream itself from the last folded sequence (`?after=<seq>`) after the
  hinted delay, up to 36 attempts (~3 minutes), then reports the run as lost
  rather than staying silent. Nine client tests cover the folding, the
  reopen, the hint delay, the budget and unsubscribe; the second browser
  pass (`browser-deploy.md`) is the live proof.
- **The dashboard said $0 on a process that had spent money.**
  `concierge_spend_usd_today` was only set when spend was computed, which
  with the ceiling gate off meant only when someone read `/spend`. The
  periodic loop now refreshes it every tick; the load transcript shows
  `0.363` on a two-minute-old process.
- **The LISTEN sessions could not be found.** The first pass looked for
  them by query text; the supervisor's heartbeat makes that `SELECT 1`, the
  same as the pool's. The listener now sets
  `application_name = concierge-listen:<channel>`, so an operator (and the
  drill) can tell the two supervised sessions from the pool — the
  leader-loss runbook shows the query.
- **A lowered `run_max_concurrent` applies when the process is idle**
  (M51: the semaphore is rebuilt only when no run holds it — rebuilding
  mid-flight would orphan holders). The first burst caught the semaphore
  at 8 because the soak routine's runs were in flight; the driver now waits
  for `running = 0` before the burst and the transcript shows the `idle
  after 12s` line. Not a change in behaviour — a documented property the
  drill made visible.
- **Two runs of three were cancelled in the deploy drill.** With a 10 s
  drain (`DRAIN_WAIT_S=10`) a research run on the live model does not
  finish; the shutdown cancels it and the row says so. That is the designed
  outcome — a longer `SHUTDOWN_GRACE_S` trades stop time for completion —
  and the evidence keeps it rather than hiding it behind a long grace.
- **Driver-side lessons, not product ones**: the slim image has no
  `pkill` (the MCP kill scans `/proc` from Python); the fake provider's
  script is one FIFO for every call, so a background memory extraction can
  consume a scripted 429 unless the driver lets it settle first; a broken
  server left by the M52 drill sat in `circuit_open` and polluted the MCP
  gauges until the driver deleted it.
