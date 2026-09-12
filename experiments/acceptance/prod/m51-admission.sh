#!/usr/bin/env bash
# M51 §14n-70..72 on the stack that is up, live on ACC_MODEL: the three
# admission keys validated (422 out of range); run_max_concurrent=1 with
# run_queue_max=0 → the second chat is shed with 503 + Retry-After while the
# first runs; run_queue_max=2 → the second lands `queued`, visible on /runs
# and /ready, and runs when the slot frees; the wall clock ends a long run
# truthfully (the scripted 300 s provider answer under a 45 s clock when the
# fake provider is on — the transcript's mechanism — else a long essay on
# the live model under a 30 s clock); the provider-429 classification (fake
# provider only); the API limiter's own 429 via rate_limit_burst /
# rate_limit_per_s; an unknown model refused at validation. Output:
# transcript on stdout; frames under ACC_SHOTS.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ACC_SHOTS=${ACC_SHOTS:-$ACC_HERE/shots/m51}; mkdir -p "$ACC_SHOTS"
ROOT=${API%/api/v1}
fake_on() { [ "$(curl -s -o /dev/null -w '%{http_code}' -X POST $API/_fake/clear)" = "200" ]; }
wait_idle() { for i in $(seq 1 120); do [ "$(curl -s $ROOT/ready | py 'print(d["running"]+d["queued"])')" = "0" ] && { echo "idle after ${i}s (a lowered run_max_concurrent applies once no run holds the semaphore)"; return; }; sleep 1; done; echo "still busy after 120 s"; }
chat() { curl -s -X POST $API/chat -H "$H" -d "{\"message\":\"$1\"}"; }
run_st() { curl -s $API/runs/$1 | py 'print(d["status"])'; }

echo "# M51 admission drill — $(date -u +%FT%TZ) — model $ACC_MODEL"
say "PATCH /settings run_max_concurrent=0 → 422; run_queue_max=-1 → 422; run_wall_clock_s=10 → 422 (floor 30)"
for body in '{"run_max_concurrent":0}' '{"run_queue_max":-1}' '{"run_wall_clock_s":10}'; do curl -s -X PATCH $API/settings -H "$H" -d "$body" -w ' HTTP %{http_code}\n'; done
say "PATCH /settings default_model=$ACC_MODEL (live), formatter off, run_max_concurrent=1, run_queue_max=0, run_wall_clock_s=900"
curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\",\"formatter_enabled\":false,\"run_max_concurrent\":1,\"run_queue_max\":0,\"run_wall_clock_s\":900}" | py 'print({k:d[k] for k in ("default_model","run_max_concurrent","run_queue_max","run_wall_clock_s")})'
wait_idle
say "POST /chat #1 (live); POST /chat #2 while #1 runs — the queue is 0 deep → 503 + Retry-After"
R1=$(chat "In two sentences: what does a semaphore guarantee?" | py 'print(d["run_id"])'); echo "run #1 $R1 status=$(run_st $R1)"
curl -s -X POST $API/chat -H "$H" -d '{"message":"In one sentence: what is a queue?"}' -D - | grep -iE "^HTTP|retry-after|detail" | tr -d '\r'
say "GET /ready during the run"; curl -s $ROOT/ready; echo
T0=$(date +%s); echo "run #1 → $(wait_run $R1 180) after $(( $(date +%s) - T0 ))s"; curl -s $API/runs/$R1 | py 'print("answer:", (d.get("final_answer") or "")[:160])'

say "PATCH /settings run_queue_max=2 — now the second run waits, visibly"
curl -s -X PATCH $API/settings -H "$H" -d '{"run_queue_max":2}' | py 'print({k:d[k] for k in ("run_max_concurrent","run_queue_max")})'
wait_idle
say "POST /chat #1 and #2 back to back (live)"
Q1=$(chat "List three properties of a bounded queue, one line each." | py 'print(d["run_id"])')
Q2=$(chat "In one sentence: why is a visible queue better than a silent one?" | py 'print(d["run_id"])')
echo "run #1 $Q1 status=$(run_st $Q1)"; echo "run #2 $Q2 status=$(run_st $Q2)   ← expected: queued, not running"
say "GET /ready with one running and one queued; GET /runs?limit=2 — the queued status is a first-class row"
curl -s $ROOT/ready; echo
curl -s "$API/runs?limit=2" | py 'items=d if isinstance(d,list) else d["items"]; print([(r["id"][:8], r["status"]) for r in items])'
shot 01-runs-page-queued-and-wall-clock runs
echo "run #1 → $(wait_run $Q1 180)"; echo "run #2 status right after #1 finished: $(run_st $Q2)"; echo "run #2 → $(wait_run $Q2 180)"
say "psql: both runs, in order (started_at is the submit time; #2 finishes after #1)"
psql_ "select left(id::text,8), status, to_char(started_at,'HH24:MI:SS.MS'), to_char(finished_at,'HH24:MI:SS.MS'), left(final_answer,90) from runs where id in ('$Q1','$Q2') order by started_at"

say "§14n-70 the wall clock: a run that outlives run_wall_clock_s ends failed with the clock named; the heartbeat advanced at 30 s; no step left running"
if fake_on; then
  curl -s -X PATCH $API/settings -H "$H" -d '{"default_model":"fake:scripted","run_wall_clock_s":45}' | py 'print("PATCH →", d["default_model"], "run_wall_clock_s", d["run_wall_clock_s"])'
  echo "POST /_fake/script — the next provider answer takes 300 s to arrive (a hung provider)"
  curl -s -X POST $API/_fake/script -H "$H" -d '{"calls":[{"content":"late","delay_s":300}]}'; echo
  WC=$(chat "late" | py 'print(d["run_id"])')
else
  curl -s -X PATCH $API/settings -H "$H" -d '{"run_wall_clock_s":30}' | py 'print("PATCH → run_wall_clock_s", d["run_wall_clock_s"], "(no fake provider on this backend: a 1500-word essay on the live model outlives 30 s)")'
  WC=$(chat "Write a 1500-word essay on the history of container orchestration, with sections and a conclusion." | py 'print(d["run_id"])')
fi
T0=$(date +%s); echo "run $WC → $(wait_run $WC 400) after $(( $(date +%s) - T0 ))s"
curl -s $API/runs/$WC | py 'print({k:d.get(k) for k in ("status","error","started_at","finished_at")})'
psql_ "select status||'|'||to_char(started_at,'HH24:MI:SS')||'|heartbeat '||coalesce(to_char(last_heartbeat_at,'HH24:MI:SS'),'-')||'|'||to_char(finished_at,'HH24:MI:SS')||'|'||extract(epoch from finished_at-started_at)::int||'s' from runs where id='$WC'"
psql_ "select step_type||'|'||status from run_steps where run_id='$WC'"
curl -s $ROOT/metrics | grep -E '^concierge_runs_total.*status="failed"' || echo "(no failed runs_total series)"

if fake_on; then
  say "§14n-71 POST /_fake/script — the provider answers 429: the run fails naming the class, the model and the settings; llm_errors_total{kind=rate_limited} moves"
  curl -s -X POST $API/_fake/script -H "$H" -d '{"calls":[{"error":"429 Too Many Requests: rate limit exceeded, retry after 20s"}]}'; echo
  E=$(chat "rate limited" | py 'print(d["run_id"])'); echo "run $E → $(wait_run $E 120)"
  curl -s $API/runs/$E | py 'print({"status": d["status"], "error": (d.get("error") or "")[:240]})'
  curl -s $ROOT/metrics | grep -E '^concierge_llm_errors_total' || echo "(no llm_errors_total series)"
  curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\"}" -o /dev/null
else echo; echo "(the provider-429 classification needs the fake provider on the backend — docs/acceptance/prod/M51/wall-clock-and-429.md)"; fi

say "the API limiter's own 429: rate_limit_burst=5, rate_limit_per_s=1, then 12 GET /settings in a burst (the M40 limiter answers a bare 429 — no Retry-After; that header is the admission 503's and the spend 429's)"
curl -s -X PATCH $API/settings -H "$H" -d '{"rate_limit_burst":5,"rate_limit_per_s":1}' | py 'print({k:d[k] for k in ("rate_limit_burst","rate_limit_per_s")})'
for i in $(seq 1 12); do curl -s -o /dev/null -w '%{http_code} ' $API/settings; done; echo
curl -s $API/settings -D - | grep -iE "^HTTP|retry-after|detail" | tr -d '\r'
sleep 8   # let the bucket refill before the restore, which must itself pass the limiter
for i in $(seq 1 10); do [ "$(curl -s -X PATCH $API/settings -H "$H" -d '{"rate_limit_burst":120,"rate_limit_per_s":10}' -o /dev/null -w '%{http_code}')" = "200" ] && break; sleep 2; done
echo "restored rate_limit_burst=120 rate_limit_per_s=10 (after $i attempt(s))"

say "PATCH /settings default_model=openrouter:qwen/no-such-model → 422 (unknown model refused at validation)"
curl -s -X PATCH $API/settings -H "$H" -d '{"default_model":"openrouter:qwen/no-such-model"}' -w ' HTTP %{http_code}\n'
say "restore defaults: run_max_concurrent=8 run_queue_max=32 run_wall_clock_s=900"
curl -s -X PATCH $API/settings -H "$H" -d '{"run_max_concurrent":8,"run_queue_max":32,"run_wall_clock_s":900}' | py 'print({k:d[k] for k in ("run_max_concurrent","run_queue_max","run_wall_clock_s")})'
shot 02-settings-api-guardrails settings
echo "# end — $(date -u +%FT%TZ)"
