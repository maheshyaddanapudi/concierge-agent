# Acceptance drivers (spec §14)

Click-driven Playwright stages and shell drills that produce the evidence under
`docs/acceptance/`. Nothing here reads a provider key or knows about a
deployment: the stack's own environment does, and every script is
parametrised by `ACC_*` variables.

## Stages (Playwright)

Each stage is one module in `stages/`, exporting `default async (ctx)`; the
runner opens one browser, runs the stages you name in order, and writes
numbered frames plus a `transcript.md` per stage under `ACC_SHOTS/<stage>/`.

```bash
cd experiments/acceptance && npm install          # Playwright (its Chromium: npx playwright install chromium)
export ACC_BASE=http://localhost:5173             # the frontend; the API is ${ACC_BASE}/api/v1 unless ACC_API is set
export ACC_SHOTS=./shots                          # where frames land
export ACC_MODEL=openrouter:qwen/qwen3.8-max      # the live model every stage uses
node run.mjs stages/00-fresh-slate.mjs stages/01-settings-models.mjs
node publish.mjs 00-fresh-slate 01-settings-models   # replaces docs/acceptance/<stage>/ with the captured frames
```

Stages assume a **fresh** stack (`docker compose down -v && docker compose up -d`)
for `00-fresh-slate` and carry state forward in order, the way the spec's script
does. `ACC_CHROMIUM` points at a system Chromium when Playwright's download is
not wanted. `publish.mjs` never publishes a stage that has a `zz-failure.png`.

| Range | What they prove |
|---|---|
| `00`–`05` | the seed, settings/models, an MCP server registered, tools, skills, sub agents (the §14 script's setup steps) |
| `06`–`09` | the four trials: graph/agentic × effort high/default, each a gated multi-turn conversation plus its trace |
| `10`–`13` | the uncovered ask (fallback), HITL deny + the Settings queue, Stop + the queued message, failure/retry/cancel |
| `14`–`18` | runs & ops, static guards, the theme gallery, data purge, registry cache + retrieval |
| `19`–`24` | multi-turn continuity, heterogeneous role models, the M8 features (form gate, chart, research), the HITL card across surfaces, ops fixes, the formatter modes |
| `25`–`32` | memory, ambient, A2A, configuration hardening, pursuit, salience, salience decisions, durable forgetting |
| `33`–`34` | evals; the builtin auth provider in the UI (run by `prod/m34-auth.sh`) |
| `35` | tool schema drift: the seeded stub server renames a parameter under a live run — badge, banner, acknowledge, the trace's pinned version, the policy toggle, quarantine |

Some stages need host-side counterparts, reached from the containers at the
docker bridge gateway (`172.18.0.1` on a default compose network):

- `27`, `28`: the repo's scripted A2A counterparty —
  `cd backend && .venv/bin/python -m tests.a2a_counterparty --port 8027 --name polyglot-agent --auth bearer`
  (and `8028 keyed-agent apikey-header`, `8029 mtls-agent mtls-only`, `8030 oauth-agent oauth2`);
  the keyed agent's credential is `env:A2A_STUB_API_KEY`, so the backend needs `A2A_STUB_API_KEY=stub-api-key`;
  and because the counterparties sit on a private address, the backend's egress policy must name that host
  (`EGRESS_ALLOW_HOSTS=172.18.0.1`) — otherwise registration is refused, which is the M52 guard doing its job.
- `29`: `python3 sinks.py --http 9099 --smtp 8025 --log sinks.log` and a backend with
  `AMBIENT_WEBHOOK_URL=http://172.18.0.1:9099/push SMTP_HOST=172.18.0.1 SMTP_PORT=8025 SMTP_FROM=… SMTP_TO=…`;
  point `ACC_SINK_LOG` at the log.
- `23`, `28`–`32`: `docker exec` into the db container (`ACC_DB_CONTAINER`, `ACC_DB_USER`, `ACC_DB_NAME`)
  for checkpoint counts and for the server-side inserts the ambient drills use.

`shot.mjs <name> <route>` screenshots one admin page for the shell drills.

## Prod drills (shell)

`prod/` holds the production-hardening drills, one script per milestone
theme, all sourcing `prod/common.sh` (`ACC_API`, `ACC_BASE`, `ACC_MODEL`,
`ACC_BACKEND_CONTAINER`, `ACC_DB_CONTAINER`, `ACC_DATABASE_URL`, `ACC_SHOTS`,
`ACC_OUT`). Each prints a transcript to stdout; frames go under `ACC_SHOTS`.
Drills that recreate the backend (`m55-seam.sh`, `m34-auth.sh`, `m51-redis-fail-open.sh`)
use `docker compose` with the caller's `COMPOSE_FILE` / profile environment.

| Script | Evidence |
|---|---|
| `m34-auth.sh` | the builtin auth provider live: dark gate, bootstrap admin, member tenancy, the fire token as the only auth on the fire path, then the UI stage |
| `m49-baseline.sh` | the load baseline through `experiments/load/harness.py` |
| `m50-quarantine-and-timezone.sh` | memory quarantine routing, ambient timezone handling |
| `m51-admission.sh`, `m51-redis-fail-open.sh` | admission control, wall clock, 429/503 boundaries; the redis-backed cache failing open |
| `m52-untrusted-and-secrets.sh` | write-only secrets, fenced untrusted output, the fence-escape probe |
| `m53-ops.sh` | readiness, metrics labels, retention gates, the spend ceiling, MCP reconnect, the rolling-deploy and restore round-trips |
| `m54-recall.sh` | recall latency 10k → 100k → 1M embeddings on the HNSW column |
| `m55-seam.sh` | the auth seam with the reference stub provider selected by environment |
| `m56-ceremony.sh`, `m56-addendum.sh` | the §14 ceremony steps 1–11 through the API with the UI screenshotted per step |
| `perf-record.sh` | the performance record (api, runs-scale, chat, sse) |
| `schema-drift.sh` | tool schema drift (spec §3.2): the stub server renames a parameter under a live run; the log line, the metric, the versioned row, the pinned tool-call step and snapshot, quarantine and acknowledgement through the API |
| `fixes-hitl-deny.sh` | the campaign's finding 1 re-verified: a gated sub agent denied with a note through the API, the steps and the answer that must report the refusal (`ACC_AGENT` names the agent; default `site-reporter`) |
| `fixes-ambient-toggle.sh` | the campaign's finding 2 re-verified: `ambient_enabled` off→on cycles (one-second and held for a tick), then the lease, gauge, log line and a tier-0 probe flush after each |
