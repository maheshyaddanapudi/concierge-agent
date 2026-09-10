#!/usr/bin/env bash
# M51 §14n-73/74/75 — fault injection with docker compose and the API:
# Redis stopped under registry_cache_mode=redis (every registry read keeps
# answering 200 from Postgres, a run still executes, the degraded counter
# and log line, recovery on start), the webhook delivery channel pointed
# at a closed port (dispatch → ledger → 60 s backoff on the real clock →
# clock-skipped attempts 3/4 → dead letter), and a restart mid-run (SIGTERM
# drains: the short run finishes, the long one is cancelled with the
# shutdown named; SIGKILL: the next boot reaps the orphans). The backend is
# recreated ONCE with FAKE_LLM_ENABLED=1 (the fault injector), REDIS_URL
# and AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook (docker compose, the
# caller's COMPOSE_FILE / profile environment; the redis service is the
# compose `redis` profile) and put back at the end. ACC_REDIS_URL overrides
# the compose-network redis URL. Output: transcript on stdout.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$ACC_ROOT" || exit 1
REDIS_URL_=${ACC_REDIS_URL:-redis://redis:6379/0}
codes() { for p in "$@"; do curl -s -o /dev/null -w "GET /$p → HTTP %{http_code} %{time_total}s\n" "$API/$p"; done; }
chat() { curl -s -X POST $API/chat -H "$H" -d "{\"message\":\"$1\"}" | py 'print(d["run_id"])'; }
script() { curl -s -X POST $API/_fake/script -H "$H" -d "$1"; echo; }
nonterm() { psql_ "select count(*) from runs where status not in ('completed','failed','cancelled')"; }
rows() { psql_ "select left(id::text,8)||'|'||status||'|'||coalesce(left(error,110),'')||'|'||coalesce(to_char(finished_at,'HH24:MI:SS'),'') from runs where id in ('$1','$2') order by started_at"; psql_ "select step_type||'|'||status from run_steps where run_id in ('$1','$2')"; }

echo "# M51 fail-open / delivery-retry / restart drill — $(date -u +%FT%TZ)"
say "docker compose --profile redis up -d redis; FAKE_LLM_ENABLED=1 REDIS_URL=$REDIS_URL_ AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook docker compose up -d --force-recreate backend"
docker compose --profile redis up -d redis 2>&1 | tail -1
FAKE_LLM_ENABLED=1 REDIS_URL="$REDIS_URL_" AMBIENT_WEBHOOK_URL=http://127.0.0.1:9/hook docker compose up -d --force-recreate backend 2>&1 | tail -1
API=$(api_root); wait_ready; ROOT=${API%/api/v1}
curl -s -X PATCH $API/settings -H "$H" -d '{"default_model":"fake:scripted","formatter_enabled":false,"memory_enabled":false,"orchestrator_mode":"graph","run_wall_clock_s":900}' | py 'print("PATCH /settings →", d["default_model"], "formatter", d["formatter_enabled"], "wall clock", d["run_wall_clock_s"])'

say "§14n-74 PATCH /settings registry_cache_mode=redis; GET /cache/status; GET /tools ×3 (warm the redis path)"
curl -s -X PATCH $API/settings -H "$H" -d '{"registry_cache_mode":"redis"}' -o /dev/null -w 'HTTP %{http_code}\n'
curl -s $API/cache/status | py 'print({"mode": d["mode"], "tools": d["registries"]["tools"]})'
codes tools tools tools
curl -s $ROOT/metrics | grep -E '^concierge_cache_degraded_total' || echo "cache_degraded (before): none yet"
say "docker compose --profile redis stop redis"
docker compose --profile redis stop redis 2>&1 | tail -1
say "GET /tools, /skills, /sub-agents, /settings — served from Postgres"
codes tools skills sub-agents settings
say "POST /chat on the fake provider — a run still executes with redis down"
script '{"calls":[{"content":"ok with redis down"}]}'
R=$(chat "say ok"); echo "run $R → $(wait_run $R 120)"
curl -s $ROOT/metrics | grep -E '^concierge_cache_degraded_total' || echo "cache_degraded (after): none"
docker logs --since 2m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a cache_backend_degraded | tail -2 | cut -c1-220
curl -s -o /dev/null -w 'GET /cache/status with redis down → HTTP %{http_code}\n' $API/cache/status
say "docker compose --profile redis start redis; GET /tools ×2; registry_cache_mode back to bypass"
docker compose --profile redis start redis 2>&1 | tail -1; sleep 2; codes tools tools
curl -s -X PATCH $API/settings -H "$H" -d '{"registry_cache_mode":"bypass"}' | py 'print("registry_cache_mode →", d["registry_cache_mode"])'

say "§14n-75 backend env AMBIENT_WEBHOOK_URL (a closed port: every send is refused at once)"
docker exec "$ACC_BACKEND_CONTAINER" printenv AMBIENT_WEBHOOK_URL
say "PATCH /settings ambient on, tick 15 s, quiet hours off, interrupt → in_app + webhook"
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_quiet_hours":[],"ambient_channels":{"interrupt":["in_app","webhook"]}}' | py 'print({k:d[k] for k in ("ambient_enabled","ambient_tick_interval_s","ambient_channels","ambient_quiet_hours")})'
curl -s $ROOT/metrics | grep -E '^concierge_delivery_sends_total' || echo "delivery_sends (before): none yet"
say "insert one pending tier-0 delivery through the app's own add_delivery (inside the backend container)"
D=$(docker exec "$ACC_BACKEND_CONTAINER" python -c "import asyncio; from app.ambient.deliver import add_delivery; d=asyncio.run(add_delivery(category='interrupt', tier=0, urgency=5, title='m51 delivery retry drill')); print(d.id)" 2>&1 | tail -1)
echo "delivery=$D"
ledger() { psql_ "select coalesce(to_char(delivered_at,'HH24:MI:SS'),'')||'|'||to_char(created_at,'HH24:MI:SS')||'|'||category||'|'||coalesce((external->'webhook')::text,'') from deliveries where id='$D'"; }
attempts() { psql_ "select coalesce((external->'webhook'->>'attempts')::int,0) from deliveries where id='$D'"; }
wait_attempts() { local t0; t0=$(date +%s); for i in $(seq 1 "$2"); do [ "$(attempts)" -ge "$1" ] && { echo "attempts=$1 after $(( $(date +%s) - t0 ))s"; return; }; sleep 1; done; echo "attempts still $(attempts) after $2 s"; }
skip() { psql_ "update deliveries set external = jsonb_set(external, '{webhook,next_attempt_at}', to_jsonb(to_char(now() - interval '1 minute','YYYY-MM-DD\"T\"HH24:MI:SS\"+00:00\"'))) where id='$D'" >/dev/null; }
ledger
say "wait for the tick to flush it (≤ 15 s): dispatched → webhook refused → committed delivered together with the ledger"
wait_attempts 1 40; ledger
docker logs --since 1m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a ambient_channel_failed | tail -1 | cut -c1-300
say "attempt 2 on the real clock: backoff 60 s, retried on the first tick after it is due"
wait_attempts 2 110; ledger
say "attempts 3 and 4: the 5-min and 30-min backoffs are skipped by moving next_attempt_at into the past (a clock skip, stated as such — not a code path); the fourth attempt dead-letters"
skip; wait_attempts 3 40; ledger
skip; wait_attempts 4 40; ledger
say "dead-lettered (dead=true): a further clock skip changes nothing"
skip; sleep 20; ledger
curl -s $ROOT/metrics | grep -E '^concierge_delivery_sends_total' || echo "(no delivery_sends series)"
docker logs --since 6m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a ambient_channel_retry | tail -3 | cut -c1-200
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_channels":{}}' | py 'print("restore ambient_channels →", d["ambient_channels"], "(in-app only)")'

say "§14n-73 part A: POST /_fake/script — one answer in 8 s (a short run), one in 300 s (a long one); POST /chat ×2; docker compose stop backend (SIGTERM; stop_grace_period 40 s > SHUTDOWN_GRACE_S 25 s)"
script '{"calls":[{"content":"short done","delay_s":8},{"content":"long done","delay_s":300}]}'
S=$(chat "short"); L=$(chat "long"); sleep 1
echo "short=$S ($(curl -s $API/runs/$S | py 'print(d["status"])'))  long=$L ($(curl -s $API/runs/$L | py 'print(d["status"])'))"
T0=$(date +%s); docker compose stop backend 2>&1 | tail -1; echo "stopped after $(( $(date +%s) - T0 ))s"
echo "(GET /ready while draining: uvicorn closes the listener at SIGTERM before the lifespan drain — a client sees connection refused, not the 503; the 503 is for a pre-stop probe, M53)"
docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a -E "runs_drained|Application shutdown complete" | tail -2 | cut -c1-200
say "psql: the short run finished inside the grace; the long one is terminal — cancelled with the shutdown named — not left running"
rows "$S" "$L"
say "docker compose start backend"
docker compose start backend 2>&1 | tail -1; API=$(api_root); wait_ready
echo "non-terminal runs after the restart: $(nonterm)"
say "part B: two long answers, POST /chat ×2, then docker compose kill backend (SIGKILL — no drain possible)"
script '{"calls":[{"content":"k1","delay_s":300},{"content":"k2","delay_s":300}]}'
K1=$(chat "k1"); K2=$(chat "k2"); sleep 2; rows "$K1" "$K2"
docker compose kill backend 2>&1 | tail -1
say "psql: rows are still 'running' — the process died without a word"
psql_ "select left(id::text,8)||'|'||status from runs where id in ('$K1','$K2')"
say "docker compose start backend — reap at boot: runs_orphaned_by_restart, the orphans failed with the truth, their steps cancelled"
docker compose start backend 2>&1 | tail -1; API=$(api_root); wait_ready
docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a runs_orphaned_by_restart | tail -1 | cut -c1-200
rows "$K1" "$K2"
echo "non-terminal runs after the restart: $(nonterm)"; curl -s ${API%/api/v1}/ready; echo

say "docker compose up -d --force-recreate backend (fake provider, REDIS_URL and the webhook sink off again); default_model back to $ACC_MODEL, tick 60 s"
docker compose up -d --force-recreate backend 2>&1 | tail -1; API=$(api_root); wait_ready
curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\",\"ambient_tick_interval_s\":60}" | py 'print("default_model →", d["default_model"])'
echo "# end — $(date -u +%FT%TZ)"
