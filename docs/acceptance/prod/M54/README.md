# M54 — horizontal scale: executed proof

The wave where the system stops being one process that happens to run behind
a load balancer. Every §14q item (91–96) was driven on the shipped stack at
`docker compose up -d --scale backend=3` — the image rebuilt with M54,
`DB_REPLICAS=3`, `default_model=openrouter:qwen/qwen3.8-max` for the runs
that needed a real model, the fake provider for the load and recall sweeps —
from sandbox drivers made of `curl`, `psql`, `docker` and one Playwright
script. Transcripts are verbatim. The drills found defects that were fixed
in this wave and re-run (the honest notes at the end).

The replicas are `concierge-agent-backend-1/2/3`; compose hands each a host
port from `BACKEND_PORT_RANGE` in start order, so the transcripts name the
replica by its `replica_id` (the container hostname) and the port it had at
the time. The frontend's nginx (`:5174`) is the balancer: it resolves
`backend` per request, so consecutive requests land on different replicas.

| file | what it is |
|---|---|
| `cold-boot.md` | §14q-96: `docker compose down -v`, then three replicas up together on an empty volume. **One** replica ran the 25 Alembic upgrades, the other two logged zero — the boot lock serialised them; the two seeded MCP servers hold 1 and 14 tools with `duplicates=0`; every replica's `concierge_mcp_servers{state="connected"}` reads 2 and each `GET /mcp-servers` lists both `active`. A stub server registered through replica 1 is connected by replicas 2 and 3 **3.3 s** later (`mcp_health_interval_s=5`), its four tools present exactly once. With `registry_cache_mode=memory`, a tool `PATCH` on replica 2 moves the tools `generation` 9→10 on all three `GET /cache/status` at once and each reads `dirty: true` until its own run plane reloads it (a chat on 1 and 3 → `dirty: false, records 29`; 2 stays dirty until its next read). `/replicas` publishes the budget: `3 × 29 + 10 = 97 ≤ 100`, `max_replicas_at_declared: 3` |
| `cross-replica-cancel.md` | §14q-91 (live model): `POST /chat` on replica A → `owner_replica` = A, one step `running`; a `curl -N` stream on replica C; `POST /runs/{id}/cancel` served by replica B returns **`200 {"status":"cancelled"}` in 117 ms** — the intent was persisted, announced on the control channel, and the owner acted before B's 3 s wait expired. The row reads `cancelled | cancelled by request (from <B>)` 265 ms after the request, with `cancel_requested_at` set and `owner_replica` still A; the owner's log carries `run_cancel_local` naming B. 30 s later: still `cancelled`, one step (`cancelled`), zero provider calls since. C's stream received `id: 1 / event: run_status / {"status":"cancelled", "replayed_from":"record"}` 10 ms after the row finished and was closed by the server |
| `delivery-fan-out.md` + `11–14-browser-*.png` | §14q-92: three `curl -N /ambient/stream` subscribers pinned to the three ports (each `ping` names its replica); `GET /replicas` shows `subscribers: 1` on each. A tier-0 interrupt queued on a **non-leader** replica is flushed by the leader's next tick and the same `delivery` (`id: 1`, `mode: interrupt`, same title) is on all three streams **9.4 s** later, each event stamped with the replica that served it. The leader's log: `ambient_pursuit_held … "watchers": 3` — the cluster audience, on a leader with one local subscriber — so the webhook was held. A routine fired through replica 2 on the live model executed on replica 3 (every replica drains). With all subscribers closed the next interrupt reaches nobody in-app and `pursuit=away` sends the webhook: the receiver container logs the envelope (`kind: ambient_delivery, mode: interrupt, items: [...]`). Then two Chromium pages through the balancer whose streams sit on two different replicas (`[ff31…,1], [5deb…,1]`), neither the leader: the toast is visible in **both** browsers 2.2 s after the queue |
| `job-clock.md` | §14q-93: memory on, `job_clock` truncated → after one 60 s tick every job has exactly one row (all stamped 00:39:41/42 by **one** replica — `memory_decay`, `memory_contradiction_sweep`, `memory_compact` appear once across the three logs together; retention and the limiter eviction ride the same clock). `docker restart backend-2` → its boot tick re-runs nothing: `job_clock` byte-identical, zero job lines. The clock advanced by hand 25 h → exactly one replica (backend-1) runs each job on the next tick, the others log nothing |
| `rate-limiter.md` | §14q-94 (limiter half), auth on: `rate_limit_burst=20 / rate_limit_per_s=1`; 60 requests through the balancer in 1.3 s → **21 × 200, 39 × 429** (`....................XXXX…`), one `rate_buckets` row for the admin holding 0.27 tokens; 60 more pinned one replica at a time — replica 1 takes the 20 tokens the 25 s pause refilled, replica 2 gets one, replica 3 gets four refills: one budget, not three |
| `load-n3-vs-n1.md` + `load-n3.json`, `load-n1.json` | §14q-94 (throughput half), the M49 scenarios through the balancer. **N=3**: chat at concurrency 25 completes in e2e p50 1.66 s / p95 2.18 s at 11.3 runs/s, peak **65** connections against the published budget of 97; read path p50 12–32 ms. **N=1**: the same 25 runs take p50 5.35 s / p95 6.07 s at 4.0 runs/s (a 3.2× e2e difference — the admission gate is per process), peak 22 connections against 39. Postgres never above `per_replica × replicas + reserved` in either run. A separate probe of 12 chats through the balancer landed 4 / 5 / 3 on the three replicas (`owner_replica`) |
| `recall.md` | §14q-95: **in progress** — the 10k → 100k → 1M recall sweep is being re-run after the environment reset; this row and the file land with the next commit |
| `tests.md` | the M54 contract suite and the full suites, executed — **lands with the next commit** (last full run: 1038 passed, 1 skipped, one timing-flaky M53 test hardened) |

## What the drills found and what changed because of them

- **The decay sweep loaded the table.** The first pass of the 1M recall drill
  seeded a million memories and, with memory on, the next boot tick's decay
  sweep selected every active row as an ORM object into a replica limited
  to 1.5 GB. The kernel killed it; compose restarted it into the same tick;
  `RestartCount` reached 2,693 before the setting was switched off at the
  database. Both sweeps that touch every row (decay, contradiction) are now
  one set-based `UPDATE` each — same formula, same ranking rule — and two
  M54 tests run them over 20k / 9k seeded rows and assert the source no
  longer carries a `select(Memory)`. The row-by-row version had been
  correct at every corpus size the earlier waves used; it took the drill to
  find the ceiling. `docs/operations/scaling.md` records it.
- **Seeding a million vectors through a live HNSW index is the slow path.**
  The harness inserted one graph node per row and the seed ran for tens of
  minutes; it now drops the typed column's index for a delta of 50k or
  more, bulk-inserts and rebuilds it — the same index the migration
  declares, so the plan under test is unchanged.
- **The 429 test reset the wrong store.** `test_rate_limit_429` cleared the
  in-process fallback bucket between phases; since M54 the bucket lives in
  `rate_buckets`, so its restore-settings loop ran dry at one token a
  second. The test now empties both stores.
- **Quiet hours ate the first fan-out.** The first §92 pass produced no
  `delivery` anywhere: the shipped `ambient_quiet_hours` covered 00:30 UTC
  and both interrupts were demoted to the digest (`ambient_interrupt_demoted
  … quiet hours`). Not a defect — the drill now clears the window first, and
  the transcript keeps the line.
- **Egress refused the drill's own webhook.** With `pursuit=away` and
  nobody watching, the webhook send failed `egress refused: denied`: the
  receiver is a private-network container and M52's default policy is
  `public`. Also not a defect — the receiver is named in
  `EGRESS_ALLOW_HOSTS`, which is exactly how an operator admits an internal
  hook.
- **The cache reload is the run plane's, not the REST list's.** `GET /tools`
  reads the table; the registry cache is read by the tools projection when a
  run starts. The §96 transcript shows `dirty: true` surviving a REST read
  and clearing on the first run — documented in `rest-api.md` rather than
  changed.

Two sandbox artefacts worth naming so nobody hunts for them: the control
channel appears as `[redacted]_control` in the logs because the sandbox's
database password is the literal word `concierge` and the M52 log sanitiser
redacts it wherever it appears; and the replicas' host ports differ between
transcripts because compose reassigns them from the range on every recreate.
