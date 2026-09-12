#!/usr/bin/env bash
# M53 §14p-83..90 on the stack that is up, live on ACC_MODEL: readiness vs
# liveness (db paused → /ready 503 degraded while /health stays 200; SIGUSR1
# → draining, POST /chat 503 + Retry-After, the polite stream close, the
# drained process replaced), /metrics with the §10 labels and the operator
# gauges (a scripted provider 429 when the fake provider is on), the six
# retention gates (seeded rows aged 400 days: gates as shipped delete only
# the expired session; every gate on deletes one row per table and the
# protected rows survive), the spend ceiling (chat 429 + Retry-After, an
# ambient fire HELD, gate off → 201 priced), MCP reconnect (the seeded fetch
# server killed → error → active; a /bin/false server trips the breaker;
# re-ingest keeps intent), the supervised LISTEN sessions terminated and
# back with a fire drained on the fresh session, a 6-chat burst under
# run_max_concurrent=3 sampled from /metrics, then the one-host halves of
# the deploy drill (deploy.sh under an open curl stream; reconnect with
# Last-Event-ID resolves from the record) and the restore drill (backup.sh
# → restore.sh round trip into the running db; RTO printed by restore.sh).
# Not portable from one host and left to the transcripts: the Prometheus/
# Grafana dashboards (docs/acceptance/prod/M53/load-and-dashboards.md), the
# browser deploy pass (browser-deploy.md), the volume-destroying restore
# (restore-drill.md — ACC_DESTROY_VOLUME=1 runs that variant here). Output:
# transcript on stdout; frames under ACC_SHOTS; backups under ACC_OUT.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ACC_SHOTS=${ACC_SHOTS:-$ACC_HERE/shots/m53}; mkdir -p "$ACC_SHOTS"
OUT=${ACC_OUT:-$ACC_HERE/out}; mkdir -p "$OUT"
cd "$ACC_ROOT" || exit 1
ROOT=${API%/api/v1}
fake_on() { [ "$(curl -s -o /dev/null -w '%{http_code}' -X POST $API/_fake/clear)" = "200" ]; }
m() { curl -s $ROOT/metrics | grep -E "$1" || echo "(no series matching $1)"; }
chat() { curl -s -X POST $API/chat -H "$H" -d "{\"message\":\"$1\"}" | py 'print(d["run_id"])'; }
inflight() { curl -s $ROOT/ready | py 'print(d["running"]+d["queued"])'; }
kill_proc() { docker exec "$ACC_BACKEND_CONTAINER" python -c "import os,signal; pids=[int(p) for p in os.listdir('/proc') if p.isdigit() and b'$1' in open(f'/proc/{p}/cmdline','rb').read()]; [os.kill(p, signal.SIGKILL) for p in pids]; print('killed:', pids)"; }
srv() { curl -s $API/mcp-servers | py "print(' | '.join(str(s.get(k) or '') for s in d if s['name']=='$1' for k in ('status','last_error','tool_count')) or 'no server named $1')"; }
counts() { psql_ "select 'events='||(select count(*) from ambient_events where kind='m53')||' deliveries='||(select count(*) from deliveries where category='m53')||' policies='||(select count(*) from ambient_policies where category='m53')||' patterns='||(select count(*) from pattern_instances where rule_key='m53')||' a2a='||(select count(*) from a2a_tasks where remote_agent_id='$RA')||' sessions='||(select count(*) from auth_sessions where token_hash like 'm53hash%')"; }
tablecounts() { psql_ "select 'runs='||(select count(*) from runs)||' run_steps='||(select count(*) from run_steps)||' memories='||(select count(*) from memories)||' memory_embeddings='||(select count(*) from memory_embeddings)||' ambient_events='||(select count(*) from ambient_events)||' deliveries='||(select count(*) from deliveries)||' tools='||(select count(*) from tools)"; psql_ "select string_agg(indexname, ' ') from pg_indexes where tablename='memory_embeddings'"; }

echo "# M53 ops drill — $(date -u +%FT%TZ) — model $ACC_MODEL"
curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\",\"formatter_enabled\":false,\"ambient_enabled\":true,\"ambient_tick_interval_s\":15}" | py 'print("PATCH /settings →", d["default_model"], "ambient", d["ambient_enabled"])'
W=$(chat "What is the capital of Portugal? One word."); echo "warm-up run $W → $(wait_run $W 120) (a completed run for the record-stream check; today's spend for the ceiling)"

say "§14p-84 GET /ready, /health; docker compose pause db → /ready 503 degraded (db names the failure), /health 200; unpause → 200"
curl -s $ROOT/ready -w ' HTTP %{http_code}\n'; curl -s $ROOT/health -w ' HTTP %{http_code}\n'
docker compose pause db 2>&1 | tail -1
curl -s $ROOT/ready -w ' HTTP %{http_code} in %{time_total}s\n'; curl -s $ROOT/health -w ' HTTP %{http_code}\n'
docker compose unpause db 2>&1 | tail -1; sleep 1; curl -s $ROOT/ready -w ' HTTP %{http_code}\n'
say "psql: a run owned by ANOTHER replica (inserted directly, status=running)"
C=$(psql_ "insert into conversations(id,title) values (gen_random_uuid(),'m53-other-replica') returning id")
OR=$(psql_ "insert into runs(id,conversation_id,chat_message,status,orchestrator_mode,include_history_summary,include_memories,is_eval,owner_replica,total_input_tokens,total_output_tokens) values (gen_random_uuid(),'$C','owned elsewhere','running','graph',false,false,false,'other-replica',0,0) returning id"); echo "run $OR"
say "docker compose kill -s USR1 backend → /ready 503 draining, /health 200; POST /chat 503 + Retry-After; a stream on a run this process is not executing gets event: reconnect; a completed run's record streams from ?after=3 with no hint"
docker compose kill -s USR1 backend 2>&1 | tail -1; sleep 1
curl -s $ROOT/ready -w ' HTTP %{http_code}\n'; curl -s $ROOT/health -w ' HTTP %{http_code}\n'
curl -s -X POST $API/chat -H "$H" -d '{"message":"during the drain"}' -D - | grep -iE "^HTTP|retry-after|detail" | tr -d '\r'
curl -s -N --max-time 4 $API/chat/stream/$OR | head -4
curl -s -N --max-time 4 "$API/chat/stream/$W?after=3" | grep -aE "^(id|event):" | paste -d' ' - - | head -4
psql_ "delete from runs where id='$OR'; delete from conversations where id='$C'" >/dev/null
say "docker compose up -d --force-recreate --no-deps backend (a drained process is replaced, never resumed)"
T0=$(date +%s); docker compose up -d --force-recreate --no-deps backend 2>&1 | tail -1; API=$(api_root); wait_ready; ROOT=${API%/api/v1}; curl -s $ROOT/ready; echo

say "§14p-86 /metrics: the §10 labels on the step series, the port series, saturation, in-flight, backlog, MCP, listener, SSE, spend"
if fake_on; then
  curl -s -X PATCH $API/settings -H "$H" -d '{"default_model":"fake:scripted"}' -o /dev/null
  curl -s -X POST $API/_fake/script -H "$H" -d '{"calls":[{"error":"429 rate limit exceeded: retry later"}]}' -o /dev/null
  E=$(chat "m53 rate limited"); echo "scripted provider 429 → run $E $(wait_run $E 60): $(curl -s $API/runs/$E | py 'print((d.get("error") or "")[:120])')"
  curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\"}" -o /dev/null
else echo "(the scripted provider 429 needs the fake provider on the backend; the live series below stand on their own)"; fi
curl -s $ROOT/metrics | python3 -c '
import sys; want = ["tier", "kind", "source", "model", "effort", "status"]
rows = [l for l in sys.stdin if l.startswith("concierge_steps_total{")]
print("concierge_steps_total series:", len(rows), "| every one carries", want, "→", all(all(w + "=" in r for w in want) for r in rows)); print("".join(rows[:3]).rstrip())'
m '^concierge_llm_calls_total|^concierge_llm_latency_seconds_count'
m '^concierge_db_pool_(connections|saturation)|^concierge_runs_in_flight|^concierge_run_slots|^concierge_backlog_depth|^concierge_mcp_servers|^concierge_listener_connected|^concierge_sse_subscribers|^concierge_spend_usd_today'

say "§14p-85 psql: one finished and one protected row per retention table, aged 400 days"
UID_=$(psql_ "select id from users limit 1"); MADE_USER=0
[ -z "$UID_" ] && { UID_=$(psql_ "insert into users(id,username,password_hash,role) values (gen_random_uuid(),'m53-retention','x','member') returning id"); MADE_USER=1; }
RA=$(psql_ "insert into remote_agents(id,name,description,source,status,card_url) values (gen_random_uuid(),'m53-retention-agent','','dynamic','inactive','https://example.invalid/agent.json') returning id")
psql_ "insert into ambient_events(id,kind,source,depth,occurred_at,received_at,verdict) values (gen_random_uuid(),'m53','webhook',0,now()-interval '400 days',now()-interval '400 days','fired'),(gen_random_uuid(),'m53','webhook',0,now()-interval '400 days',now()-interval '400 days',null)"
psql_ "insert into deliveries(id,category,tier,urgency,title,delivered_at,created_at) values (gen_random_uuid(),'m53',2,2,'m53 old delivered',now()-interval '400 days',now()-interval '400 days'),(gen_random_uuid(),'m53',2,2,'m53 old pending',null,now()-interval '400 days')"
psql_ "insert into ambient_policies(id,category,reason,source,created_at) values (gen_random_uuid(),'m53','old','rule',now()-interval '401 days'),(gen_random_uuid(),'m53','latest','rule',now()-interval '400 days')"
psql_ "insert into pattern_instances(id,rule_key,partition_key,state,created_at) values (gen_random_uuid(),'m53','','matched',now()-interval '400 days'),(gen_random_uuid(),'m53','','armed',now()-interval '400 days')"
psql_ "insert into a2a_tasks(id,remote_agent_id,state,delivered,created_at,updated_at) values (gen_random_uuid(),'$RA','completed',true,now()-interval '400 days',now()-interval '400 days'),(gen_random_uuid(),'$RA','parked',false,now()-interval '400 days',now()-interval '400 days')"
psql_ "insert into auth_sessions(id,user_id,token_hash,expires_at) values (gen_random_uuid(),'$UID_','m53hash-expired',now()-interval '400 days'),(gen_random_uuid(),'$UID_','m53hash-live',now()+interval '7 days')"
echo "rows seeded: $(counts)"
GATES='"retention_ambient_events_enabled":%s,"retention_deliveries_enabled":%s,"retention_ambient_policies_enabled":%s,"retention_pattern_instances_enabled":%s,"retention_a2a_tasks_enabled":%s'
say "GET /retention (gates as shipped: five off, auth_sessions on) — eligible counted regardless of the gate"
curl -s $API/retention | py 'print("\n".join("%-20s enabled=%-6s days=%-5s eligible=%s" % (t["table"], t["enabled"], t["days"], t["eligible"]) for t in d["tables"]))'
say "POST /retention/run with the gates as shipped → only the expired session goes"
curl -s -X POST $API/retention/run; echo; echo "rows after: $(counts)"
say "PATCH /settings: every retention gate on; POST /retention/run → exactly one row per table; the protected rows survive"
curl -s -X PATCH $API/settings -H "$H" -d "{$(printf "$GATES" true true true true true)}" -o /dev/null -w 'HTTP %{http_code}\n'
curl -s -X POST $API/retention/run; echo; echo "rows after: $(counts)"
psql_ "select 'events|'||coalesce(verdict,'pending') from ambient_events where kind='m53' union all select 'deliveries|'||title from deliveries where category='m53' union all select 'policies|'||reason from ambient_policies where category='m53' union all select 'patterns|'||state from pattern_instances where rule_key='m53' union all select 'a2a|'||state from a2a_tasks where remote_agent_id='$RA' union all select 'sessions|'||token_hash from auth_sessions where token_hash like 'm53hash%'"
m '^concierge_retention_deleted_total'
curl -s -X PATCH $API/settings -H "$H" -d "{$(printf "$GATES" false false false false false)}" -o /dev/null -w 'gates back to the shipped defaults: HTTP %{http_code}\n'
curl -s -X PATCH $API/settings -H "$H" -d '{"retention_deliveries_days":0}' -w ' HTTP %{http_code}\n'
psql_ "delete from ambient_events where kind='m53'; delete from deliveries where category='m53'; delete from ambient_policies where category='m53'; delete from pattern_instances where rule_key='m53'; delete from a2a_tasks where remote_agent_id='$RA'; delete from remote_agents where id='$RA'; delete from auth_sessions where token_hash like 'm53hash%'" >/dev/null
[ "$MADE_USER" = 1 ] && psql_ "delete from users where id='$UID_'" >/dev/null
shot 01-settings-retention-gates settings

say "§14p-89 GET /spend (today's runs priced from the provider feed or overrides); GET /runs?limit=3 → cost_usd per run"
curl -s $API/spend | py 'print({k:d.get(k) for k in ("day","usd_today","runs_today","unpriced_tokens","by_kind","ceiling")})'
curl -s "$API/runs?limit=3" | py 'items=d if isinstance(d,list) else d["items"]; print([{k:r.get(k) for k in ("status","total_input_tokens","total_output_tokens","cost_usd","cost_priced")} for r in items])'
say "PATCH /settings: model_prices override for $ACC_MODEL, ceiling 0.0001 USD/day, gate ON → /spend reached → POST /chat 429 + Retry-After"
curl -s -X PATCH $API/settings -H "$H" -d "{\"spend_ceiling_enabled\":true,\"spend_ceiling_usd_per_day\":0.0001,\"model_prices\":{\"$ACC_MODEL\":{\"input_per_m\":1.0,\"output_per_m\":3.0}}}" | py 'print({k:d[k] for k in ("spend_ceiling_enabled","spend_ceiling_usd_per_day","model_prices")})'
curl -s $API/spend | py 'print({k:d.get(k) for k in ("usd_today","runs_today","ceiling")})'
curl -s -X POST $API/chat -H "$H" -d '{"message":"over the ceiling"}' -D - | grep -iE "^HTTP|retry-after|detail" | tr -d '\r'
say "ambient: POST /routines (webhook trigger) → token → fire → the drain HOLDS the fire on the event with the ceiling as the reason"
for id in $(curl -s $API/routines | py 'print(" ".join(r["id"] for r in d if r["name"] in ("m53-ceiling","m53-listen")))'); do curl -s -X DELETE $API/routines/$id -o /dev/null; done
SR=$(curl -s -X POST $API/routines -H "$H" -d '{"name":"m53-ceiling","prompt":"Reply with the single word ok.","triggers":[{"type":"webhook"}]}' | py 'print(d["id"])')
ST=$(curl -s -X POST $API/routines/$SR/token | py 'print(d["fire_token"])')
EV=$(curl -s -X POST $API/routines/$SR/fire -H "$H" -H "Authorization: Bearer $ST" -d '{"text":"ceiling probe"}' | py 'print(d.get("event_id", d))'); echo "event $EV"
for i in $(seq 1 12); do v=$(psql_ "select coalesce(verdict,'pending')||' | '||coalesce(left(verdict_reason,160),'') from ambient_events where id='$EV'"); case "$v" in pending*|processing*) sleep 5;; *) break;; esac; done; echo "t+$((i*5))s: $v"
m '^concierge_spend_usd_today|^concierge_spend_ceiling_refusals_total'
say "PATCH /settings spend_ceiling_enabled=false → POST /chat 201 (byte-identical admission), priced from the captured usage"
curl -s -X PATCH $API/settings -H "$H" -d '{"spend_ceiling_enabled":false}' -o /dev/null -w 'HTTP %{http_code}\n'
RESP=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"What is the capital of Portugal? One word."}' -w '\nHTTP %{http_code}'); echo "$RESP" | tr '\n' ' '; echo
G=$(echo "$RESP" | head -1 | py 'print(d["run_id"])'); echo "run $G → $(wait_run $G 120)"; curl -s $API/runs/$G | py 'print({k:d.get(k) for k in ("status","total_input_tokens","total_output_tokens","cost_usd","cost_priced")})'
curl -s -X DELETE $API/routines/$SR -o /dev/null; curl -s -X PATCH $API/settings -H "$H" -d '{"model_prices":{},"spend_ceiling_usd_per_day":10.0}' -o /dev/null
shot 02-settings-cost-and-ceiling settings; shot 04-runs-cost-column runs

say "§14p-87 the seeded fetch server: SIGKILL its process inside the container (a /proc scan — the slim image has no pkill) → the health ping (mcp_health_interval_s) marks it error → auto-reconnect brings it back active"
echo "before: $(srv fetch)"; kill_proc mcp-server-fetch
for i in $(seq 1 9); do sleep 5; echo "t+$((i*5))s: $(srv fetch)"; done
docker logs --since 1m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a -oE '"event": "mcp_(ping_failed|reconnect_scheduled|tools_ingested|reconnected)".{0,50}' | head -4
m '^concierge_mcp_servers|^concierge_mcp_reconnects_total'
say "PATCH /settings mcp_reconnect_max_attempts=2; POST /mcp-servers stdio command=/bin/false → the breaker opens after two attempts; POST …/reconnect resets it"
curl -s -X PATCH $API/settings -H "$H" -d '{"mcp_reconnect_max_attempts":2}' -o /dev/null
for id in $(curl -s $API/mcp-servers | py 'print(" ".join(s["id"] for s in d if s["name"] in ("m53-broken","m53-stub")))'); do curl -s -X DELETE $API/mcp-servers/$id -o /dev/null; done
BAD=$(curl -s -X POST $API/mcp-servers -H "$H" -d '{"name":"m53-broken","description":"cannot start","transport":"stdio","command":"/bin/false"}' | py 'print(d["id"])'); echo "server $BAD"
for i in $(seq 1 9); do sleep 5; echo "t+$((i*5))s: $(curl -s $API/mcp-servers/$BAD | py 'print(d["status"], "|", (d.get("last_error") or "")[:110])')"; done
m '^concierge_mcp_servers|^concierge_mcp_reconnects_total'; docker logs --since 1m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a mcp_circuit_open | tail -1 | cut -c1-160
curl -s -X POST $API/mcp-servers/$BAD/reconnect | py 'print("reconnect →", d["status"], "|", (d.get("last_error") or "")[:80], "(attempts restart from 0)")'; m '^concierge_mcp_servers'
curl -s -X DELETE $API/mcp-servers/$BAD -o /dev/null -w 'DELETE → HTTP %{http_code}\n'; curl -s -X PATCH $API/settings -H "$H" -d '{"mcp_reconnect_max_attempts":8}' -o /dev/null
say "re-ingest keeps intent (the stub server shipped in the image): a tool set inactive stays inactive across refresh-tools; a deleted tool stays deleted across reconnect; POST /tools/{id}/restore brings it back"
SS=$(curl -s -X POST $API/mcp-servers -H "$H" -d '{"name":"m53-stub","description":"the test stub","transport":"stdio","command":"python","args":["/app/tests/stub_mcp_server.py"]}' | py 'print(d["id"])'); sleep 2; echo "m53-stub: $(srv m53-stub)"
tool() { curl -s "$API/tools?limit=200" | py "print([t['id'] for t in d if t['tool_key']=='$1'][0])"; }
ECHO=$(tool m53-stub.echo); ADD=$(tool m53-stub.add)
curl -s -X PATCH $API/tools/$ECHO -H "$H" -d '{"status":"inactive"}' | py 'print("PATCH →", d["tool_key"], d["status"], d.get("ingest_state"))'
curl -s -X POST $API/mcp-servers/$SS/refresh-tools -o /dev/null; curl -s $API/tools/$ECHO | py 'print("after refresh-tools →", d["tool_key"], d["status"], d.get("ingest_state"))'
curl -s -X DELETE $API/tools/$ADD -o /dev/null -w 'DELETE add → HTTP %{http_code}\n'; curl -s -X POST $API/mcp-servers/$SS/reconnect -o /dev/null
psql_ "select tool_key||'|'||status||'|deleted_at '||coalesce(deleted_at::text,'-')||'|'||coalesce(ingest_state,'') from tools where mcp_server_id='$SS' order by 1"
curl -s -X POST $API/tools/$ADD/restore | py 'print("restore →", d["tool_key"], d["status"], "deleted_at", d.get("deleted_at"))'
curl -s -X DELETE $API/mcp-servers/$SS -o /dev/null -w 'cleanup DELETE stub → HTTP %{http_code}\n'
shot 03-settings-mcp-reconnect settings

say "§14p-88 the supervised LISTEN sessions (application_name concierge-listen:<channel>): pg_terminate_backend on both → gauges 0 then 1, reconnect counters, new pids"
m '^concierge_listener_connected'
psql_ "select pid||'|'||application_name||'|'||state from pg_stat_activity where application_name like 'concierge-listen:%' order by 2"
psql_ "select pid||'|'||application_name||'|'||pg_terminate_backend(pid) from pg_stat_activity where application_name like 'concierge-listen:%'"
for i in $(seq 1 6); do sleep 1; echo "t+${i}s: $(curl -s $ROOT/metrics | grep -E '^concierge_listener_connected' | tr '\n' ' ')"; done
m '^concierge_listener_reconnects_total'
docker logs --since 1m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a -oE '"event": "(listener_lost|listener_started|listener_reconnected|cache_listener_reconnected)"' | sort | uniq -c
psql_ "select pid||'|'||application_name||'|'||state from pg_stat_activity where application_name like 'concierge-listen:%' order by 2"
say "a fire after the gap is drained within seconds — the wake NOTIFY is heard on the fresh session (the tick alone would take ambient_tick_interval_s=15)"
LR=$(curl -s -X POST $API/routines -H "$H" -d '{"name":"m53-listen","prompt":"Reply with the single word ok.","triggers":[{"type":"webhook"}]}' | py 'print(d["id"])'); LT=$(curl -s -X POST $API/routines/$LR/token | py 'print(d["fire_token"])')
LE=$(curl -s -X POST $API/routines/$LR/fire -H "$H" -H "Authorization: Bearer $LT" -d '{"text":"after the gap"}' | py 'print(d.get("event_id",""))')
T0=$(date +%s%N); for i in $(seq 1 300); do v=$(psql_ "select coalesce(verdict,'pending') from ambient_events where id='$LE'"); case "$v" in pending) sleep 0.1;; *) break;; esac; done
echo "verdict '$v' after $(( ($(date +%s%N) - T0) / 1000000 )) ms (psql polling at 100 ms adds its own latency)"
curl -s -X DELETE $API/routines/$LR -o /dev/null

say "§14p-86 load half: 6 chats on the live model under run_max_concurrent=3, sampled from /metrics every 3 s (Prometheus/Grafana from docs/observability/ are not part of the three shipped services — the dashboards stay in docs/acceptance/prod/M53/load-and-dashboards.md)"
curl -s -X PATCH $API/settings -H "$H" -d '{"run_max_concurrent":3}' -o /dev/null
for i in $(seq 1 90); do [ "$(inflight)" = "0" ] && { echo "idle after ${i}s (the semaphore is rebuilt only when no run holds it)"; break; }; sleep 1; done
BR=""; for i in 1 2 3 4 5 6; do BR="$BR $(chat "In one sentence: what is burst message number $i about?")"; done
for i in $(seq 1 20); do sleep 3; echo "t+$((i*3))s: $(curl -s $ROOT/metrics | grep -E '^concierge_db_pool_saturation|^concierge_runs_in_flight|^concierge_run_slots' | tr '\n' ' ')"; [ "$(inflight)" = "0" ] && break; done
for r in $BR; do wait_run "$r" 120 >/dev/null; done; curl -s -X PATCH $API/settings -H "$H" -d '{"run_max_concurrent":8}' -o /dev/null

say "§14p-83 one-host half: a live run with an open curl stream; DEPLOY_SKIP_BUILD=1 DEPLOY_FORCE_RECREATE=1 DRAIN_WAIT_S=10 ./deploy.sh rolls the backend under it; the client reconnects with Last-Event-ID and resolves from the record (the 3-client harness report and the browser pass: deploy-drill.md, browser-deploy.md)"
USER_PORT=${BACKEND_PORT:-}; port_now() { echo "${USER_PORT:-$(echo "$ROOT" | sed 's#.*:##')}"; }   # deploy.sh / restore.sh probe localhost:BACKEND_PORT
export BACKEND_PORT=$(port_now)
DR=$(chat "Write 600 words on the history of container orchestration, with sections."); curl -s -N $API/chat/stream/$DR > "$OUT/m53-stream-before.txt" 2>/dev/null & SP=$!; sleep 4
echo "run $DR $(curl -s $API/runs/$DR | py 'print(d["status"])'); /ready before: $(curl -s $ROOT/ready)"
T0=$(date +%s); DEPLOY_SKIP_BUILD=1 DEPLOY_FORCE_RECREATE=1 DRAIN_WAIT_S=10 ./deploy.sh 2>&1 | grep -v '^\s*$' | sed 's/^/deploy: /' | tail -8; echo "deploy.sh returned after $(( $(date +%s) - T0 )) s"
wait $SP 2>/dev/null; API=$(api_root); wait_ready; ROOT=${API%/api/v1}
LAST=$(grep -aoE '^id: [0-9]+' "$OUT/m53-stream-before.txt" | tail -1 | tr -dc 0-9); echo "the stream saw ids up to ${LAST:-none} before the port closed ($(grep -ac '^event:' "$OUT/m53-stream-before.txt") events)"
echo "reconnect with Last-Event-ID=${LAST:-0} on the new process:"; curl -s -N --max-time 8 -H "Last-Event-ID: ${LAST:-0}" $API/chat/stream/$DR | grep -aE "^(id|event):" | paste -d' ' - - | head -6
psql_ "select left(id::text,8)||'|'||status||'|'||coalesce(left(error,110),'') from runs where id='$DR'"; echo "non-terminal rows: $(psql_ "select count(*) from runs where status not in ('completed','failed','cancelled')")"
docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -a -E "ambient_leader_acquired|listener_started" | tail -3 | cut -c1-140

say "§14p-90 one-host half: ./backup.sh (pg_dump -Fc + workspace tar) → ./restore.sh round trip into the running db (RTO printed by restore.sh); row counts, the pgvector indexes and a conversation byte-identical before and after"
CONV=$(curl -s $API/runs/$W | py 'print(d["conversation_id"])'); curl -s $API/conversations/$CONV > "$OUT/m53-conv-before.json"
echo "before: $(tablecounts | tr '\n' ' ')"
BACKUP_DIR="$OUT/backups" ./backup.sh 2>&1 | tail -3
DUMP=$(ls -t "$OUT"/backups/*.dump | head -1); WS=${DUMP%.dump}.workspace.tar
if [ "${ACC_DESTROY_VOLUME:-0}" = 1 ]; then
  say "ACC_DESTROY_VOLUME=1: docker compose down; docker volume rm <pgdata>; up -d db backend (an empty schema, the seeds) — the transcript's variant"
  docker compose down 2>&1 | tail -1; docker volume rm "$(docker volume ls -q --filter name=pgdata | head -1)" 2>&1 | tail -1
  docker compose up -d db backend 2>&1 | tail -1; API=$(api_root); wait_ready; ROOT=${API%/api/v1}
  echo "fresh: $(tablecounts | head -1)"; curl -s -o /dev/null -w "GET /conversations/{id} on the fresh stack → HTTP %{http_code}\n" $API/conversations/$CONV
fi
export BACKEND_PORT=$(port_now)
./restore.sh "$DUMP" "$WS" 2>&1 | grep -E "^==|pg_restore"
API=$(api_root); wait_ready; ROOT=${API%/api/v1}
echo "after:  $(tablecounts | tr '\n' ' ')"
curl -s $API/conversations/$CONV > "$OUT/m53-conv-after.json"; echo "GET /conversations/{id} byte-identical before/after: $(cmp -s "$OUT/m53-conv-before.json" "$OUT/m53-conv-after.json" && echo true || echo false)"
curl -s $API/mcp-servers | py 'print("mcp servers:", [(s["name"], s["status"]) for s in d])'; curl -s $ROOT/ready; echo
docker compose up -d frontend 2>&1 | tail -1
curl -s -X PATCH $API/settings -H "$H" -d '{"ambient_tick_interval_s":60}' -o /dev/null
echo "# end — $(date -u +%FT%TZ)"
