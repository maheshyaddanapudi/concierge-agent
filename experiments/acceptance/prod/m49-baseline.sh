#!/usr/bin/env bash
# M49 — the load baseline re-created through experiments/load/harness.py on
# the stack that is up: api, runs-scale, chat, sse on the fake provider
# (the numbers measure the system, not a model), the 40-event ambient
# burst, then the same chat scenario on the live model at small
# concurrency (live-sample), and the prompt golden-set harness inside the
# shipped image. The backend is recreated with FAKE_LLM_ENABLED=1 when the
# fake provider is not on (docker compose, the caller's COMPOSE_FILE /
# profile environment) and put back at the end. The harness needs the
# backend venv (ACC_PYTHON overrides) and a published db port
# (ACC_DATABASE_URL). ACC_OUT sets the output dir. Output: transcript on
# stdout + JSON/MD per harness run under ACC_OUT.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
OUT=${ACC_OUT:-$ACC_HERE/out}; mkdir -p "$OUT"
PY=${ACC_PYTHON:-$ACC_ROOT/backend/.venv/bin/python}
cd "$ACC_ROOT" || exit 1
fake_on() { [ "$(curl -s -o /dev/null -w '%{http_code}' -X POST $API/_fake/clear)" = "200" ]; }
harness() { (cd "$ACC_ROOT/backend" && "$PY" ../experiments/load/harness.py --base-url "${API%/api/v1}" --database-url "$ACC_DATABASE_URL" "$@" 2>&1 | tail -30); }

echo "# M49 baseline drill — $(date -u +%FT%TZ) — api $API"
RECREATED=0
if ! fake_on; then
  say "FAKE_LLM_ENABLED=1 docker compose up -d --force-recreate backend (the load scenarios run on fake:scripted)"
  FAKE_LLM_ENABLED=1 docker compose up -d --force-recreate backend 2>&1 | tail -1
  API=$(api_root); wait_ready; RECREATED=1
fi
say "psql: Postgres max_connections and connections at rest"
psql_ "select 'max_connections='||current_setting('max_connections')||' at_rest='||(select count(*) from pg_stat_activity where datname=current_database())"

say "harness --scenarios api,runs-scale,chat,sse (the M49 baseline flags: 100 GETs × c10, runs 1k→10k, chat c=5,10,25,50, sse in steps of 5 to 60)"
T0=$(date +%s)
harness --scenarios api,runs-scale,chat,sse --api-requests 100 --api-concurrency 10 --runs-sizes 1000,10000 \
  --chat-concurrency 5,10,25,50 --chat-deadline 120 --sse-step 5 --sse-max 60 --label baseline --out "$OUT/baseline.json"
echo "harness took $(( $(date +%s) - T0 )) s"
cat "$OUT/baseline.md" 2>/dev/null || echo "no $OUT/baseline.md — the harness did not finish"

say "harness --scenarios ambient --ambient-events 40 (the webhook backlog: 40 fires, time to drain, fired/held verdicts, run outcomes, connection peak)"
T1=$(date +%s)
harness --scenarios ambient --ambient-events 40 --ambient-deadline 300 --label ambient-burst --out "$OUT/ambient-burst.json"
sed -n '/Ambient backlog/,$p' "$OUT/ambient-burst.md" 2>/dev/null
say "backend log since the burst: pool exhaustion lines (ambient_execute_failed / ambient_tick_failed / QueuePool limit) — the M49 contended run had 34, a clean run 0"
docker logs --since "$(( $(date +%s) - T1 + 5 ))s" "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a -cE "ambient_execute_failed|ambient_tick_failed|QueuePool limit" | sed 's/^/matching lines: /'
echo "(the contention itself — the test suite running beside the burst — is not reproduced here: docs/acceptance/prod/M49/ambient-burst-under-contention.md)"

say "live-sample: harness --model $ACC_MODEL --scenarios chat --chat-concurrency 3,6 --chat-deadline 240 (the latency a user sees; the backend's own provider key)"
harness --model "$ACC_MODEL" --scenarios chat --chat-concurrency 3,6 --chat-deadline 240 --label live-sample --out "$OUT/live-sample.json"
sed -n '/Concurrent chat/,$p' "$OUT/live-sample.md" 2>/dev/null

say "prompt golden sets: python -m app.prompts.check inside the shipped image"
docker exec "$ACC_BACKEND_CONTAINER" python -m app.prompts.check; echo "exit=$?"
say "a deliberate regression (planner loses its no_confident_match sentence; router renames {conditions} → {choices}) fails the harness with the prompt, case and cause named — edited in the container, restored after"
docker exec "$ACC_BACKEND_CONTAINER" sh -c 'cp -a /app/app/prompts /app/app/prompts.orig && sed -i "s/no_confident_match/no_match_found/" /app/app/prompts/planner.md && sed -i "s/{conditions}/{choices}/" /app/app/prompts/router.md; python -m app.prompts.check; echo "exit=$?"; rm -rf /app/app/prompts && mv /app/app/prompts.orig /app/app/prompts' 2>&1 | head -12
docker exec "$ACC_BACKEND_CONTAINER" python -m app.prompts.check | tail -1 | sed 's/^/restored: /'

say "ruff BLE/S triage — a lint proof on a dev checkout, not an API drill (docs/acceptance/prod/M49/ruff-triage.md)"
if [ -x "$ACC_ROOT/backend/.venv/bin/ruff" ]; then
  (cd "$ACC_ROOT/backend" && .venv/bin/ruff check . | tail -1; .venv/bin/ruff check --select BLE,S --statistics app | tail -3; echo "bare 'noqa: BLE001' markers left in app/: $(grep -rn 'noqa: BLE001$' app | wc -l)")
else echo "skipped: no backend/.venv/bin/ruff on this host"; fi

if [ "$RECREATED" = 1 ]; then
  say "docker compose up -d --force-recreate backend (fake provider off again)"
  docker compose up -d --force-recreate backend 2>&1 | tail -1; API=$(api_root); wait_ready
fi
echo "# end — $(date -u +%FT%TZ) — records under $OUT"
