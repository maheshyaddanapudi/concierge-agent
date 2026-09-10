#!/usr/bin/env bash
# M50 §14m-68/69 on the stack that is up: four malformed triggers refused
# with 422 at the API, then a `once.at` corrupted PAST the API (direct SQL)
# beside a healthy routine — the healthy one fires on the same ticks, the
# broken one reaches status=error after three ticks with the reason
# recorded, the evaluator-error counter moves, the tick keeps ticking; then
# ambient_timezone validated (200 for Europe/Lisbon, 422 for an unknown zone
# and for a non-string). The "quarantine" here is the ROUTINE quarantine of
# §14m-68 (the M50 transcript); memory quarantine kinds are M47's and not
# part of it. ACC_M50_HARNESS=1 also re-runs the sse,runs-scale harness
# scenarios the M50 after-record used (needs the fake provider on the
# backend and the backend venv). Output: transcript on stdout; frames under
# ACC_SHOTS.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ACC_SHOTS=${ACC_SHOTS:-$ACC_HERE/shots/m50}; mkdir -p "$ACC_SHOTS"
ROOT=${API%/api/v1}
rids() { curl -s "$API/routines" | py "print(' '.join(r['id'] for r in d if r['name'] in ($1)))"; }
post_bad() { say "POST /routines $1"; curl -s -X POST $API/routines -H "$H" -d "$1" -w '\nHTTP %{http_code}\n' | cut -c1-300; }

echo "# M50 quarantine + timezone drill — $(date -u +%FT%TZ)"
say "PATCH /settings ambient on, tick 15 s, ambient_timezone Europe/Lisbon"
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_enabled":true,"ambient_tick_interval_s":15,"ambient_timezone":"Europe/Lisbon"}' | py 'print({k:d[k] for k in ("ambient_enabled","ambient_tick_interval_s","ambient_timezone")})'
curl -s $API/settings | py 'print("default_model (the healthy routine runs on it):", d["default_model"])'
for id in $(rids "'m50-broken-trigger','m50-healthy'"); do curl -s -X DELETE $API/routines/$id -o /dev/null; done
post_bad '{"name":"m50-bad-once","prompt":"p","triggers":[{"type":"once","at":"not-a-date"}]}'
post_bad '{"name":"m50-bad-interval","prompt":"p","triggers":[{"type":"interval","seconds":5}]}'
post_bad '{"name":"m50-bad-cron","prompt":"p","triggers":[{"type":"cron","cron":"bogus"}]}'
post_bad '{"name":"m50-bad-filter","prompt":"p","triggers":[{"type":"webhook","filters":[{"field":"x","op":"nope","value":"1"}]}]}'

say "POST /routines m50-broken-trigger (a valid once trigger — corrupted below, past the API)"
AT=$(python3 -c "import datetime; print((datetime.datetime.now(datetime.UTC)+datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))")
BROKEN=$(curl -s -X POST $API/routines -H "$H" -d "{\"name\":\"m50-broken-trigger\",\"prompt\":\"Reply with the single word ok.\",\"triggers\":[{\"type\":\"once\",\"at\":\"$AT\"}]}" | py 'print(d["id"])'); echo "id=$BROKEN"
say "POST /routines m50-healthy (interval 3600)"
HEALTHY=$(curl -s -X POST $API/routines -H "$H" -d '{"name":"m50-healthy","prompt":"Reply with the single word ok.","triggers":[{"type":"interval","seconds":3600}]}' | py 'print(d["id"])'); echo "id=$HEALTHY"
say "UPDATE routines SET triggers = garbage once.at (direct SQL — the shape the API now refuses)"
psql_ "update routines set triggers='[{\"type\":\"once\",\"at\":\"garbage\"}]' where id='$BROKEN'"

say "waiting for three ticks (15 s each): the broken routine is quarantined, the healthy one fires on the same ticks"
T0=$(date +%s); st=""
for i in $(seq 1 120); do st=$(curl -s $API/routines/$BROKEN | py 'print(d.get("status",""))'); [ "$st" = "error" ] && break; sleep 1; done
echo "broken routine status='$st' after $(( $(date +%s) - T0 ))s"
say "GET /routines/$BROKEN (broken)"
curl -s $API/routines/$BROKEN | py 'print({k:d.get(k) for k in ("name","status","status_reason","consecutive_failures","last_fired_at")})'
say "GET /routines/$HEALTHY (healthy — fired on the same ticks)"
curl -s $API/routines/$HEALTHY | py 'print({k:d.get(k) for k in ("name","status","consecutive_failures","last_fired_at")})'
say "GET /metrics | grep evaluator_errors"
curl -s $ROOT/metrics | grep -E '^concierge_ambient_evaluator_errors_total' || echo "(no evaluator_errors series)"
say "backend log: ambient_trigger_failed (failures 1 → 2 → 3, quarantined on the third)"
docker logs --since 3m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a ambient_trigger_failed | tail -3 | cut -c1-260
say "the tick keeps ticking: the healthy routine's run"
curl -s "$API/runs?routine_id=$HEALTHY&limit=1" | py 'items=d if isinstance(d,list) else d["items"]; print([(r["id"][:8], r["status"]) for r in items] or "no run yet")'
shot 02-ambient-routines-quarantined ambient

say "§14m-69 PATCH /settings ambient_timezone=Europe/Lisbon → 200; Mars/Olympus → 422; 7 → 422"
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_timezone":"Europe/Lisbon"}' -o /dev/null -w 'Europe/Lisbon → HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_timezone":"Mars/Olympus"}' -w ' → HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_timezone":7}' -w ' → HTTP %{http_code}\n'
curl -s $API/settings | py 'print("ambient_timezone =", d["ambient_timezone"], "| the quiet hours it governs:", d["ambient_quiet_hours"])'
shot 03-settings-ambient-timezone settings
say "the zone logic's contract tests (a dev checkout — the image ships no pytest): tests/test_m50_ceiling.py -k 'timezone or quiet or digest or zone'"
if [ -x "$ACC_ROOT/backend/.venv/bin/pytest" ]; then (cd "$ACC_ROOT/backend" && FAKE_LLM_ENABLED=1 .venv/bin/pytest tests/test_m50_ceiling.py -k "timezone or quiet or digest or zone" -q 2>&1 | tail -3)
else echo "skipped: no backend/.venv/bin/pytest on this host — the four assertions are described in docs/acceptance/prod/M50/timezone.md"; fi

if [ "${ACC_M50_HARNESS:-0}" = 1 ]; then
  say "harness --scenarios sse,runs-scale --sse-max 60 (the M50 after-record: 60 streams on a HITL-paused run, /runs and /conversations at 1k and 10k runs)"
  OUT=${ACC_OUT:-$ACC_HERE/out}; mkdir -p "$OUT"
  (cd "$ACC_ROOT/backend" && "${ACC_PYTHON:-.venv/bin/python}" ../experiments/load/harness.py --base-url "$ROOT" --database-url "$ACC_DATABASE_URL" --scenarios sse,runs-scale --sse-max 60 --label m50-after --out "$OUT/m50-after.json" 2>&1 | tail -20)
  cat "$OUT/m50-after.md" 2>/dev/null
else echo; echo "(ACC_M50_HARNESS=1 re-runs the sse,runs-scale harness record; the 01-runs-page-paged-under-load frame needs that 10k-run table)"; fi

say "cleanup: routines deleted; tick back to 60 s, timezone UTC"
curl -s -X DELETE $API/routines/$BROKEN -o /dev/null -w 'DELETE broken → HTTP %{http_code}\n'
curl -s -X DELETE $API/routines/$HEALTHY -o /dev/null -w 'DELETE healthy → HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_tick_interval_s":60,"ambient_timezone":"UTC"}' -o /dev/null
echo "# end — $(date -u +%FT%TZ)"
