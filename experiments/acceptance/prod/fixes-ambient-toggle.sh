#!/usr/bin/env bash
# The campaign v1 finding 2 re-verified: flipping `ambient_enabled` off and
# on must not stall the leader tick. Two kinds of cycle, each judged by the
# advisory lease in pg_locks, the leader gauge on /metrics, the
# `ambient_leader_acquired` log count and a tier-0 probe row the tick has
# to flush afterwards:
#   switch cycles — off, one second, on: what the Settings switch does; a
#                   tick lands inside the dark second only by chance, so
#                   the transcript says whether one did;
#   held cycles   — off for a full tick interval so the tick sees ambient
#                   dark and surrenders the lease (lease 0, gauge 0), then
#                   on: the loop must lead again within a tick.
# Before the fix the first dark tick ended the loop: no lease, gauge 0,
# nothing logged, the probe never delivered, until a restart.
#   ACC_TICK_S   tick interval to run the drill at (default 15, the floor)
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ROOT=${API%/api/v1}
TICK=${ACC_TICK_S:-15}
echo "# finding 2 re-verified — $(date -u +%FT%TZ)"

lease()  { psql_ "select count(*) from pg_locks where locktype='advisory' and classid=427017 and objid=1 and granted"; }
gauge()  { curl -s "$ROOT/metrics" | grep '^concierge_ambient_leader ' | awk '{print $2}'; }
acq()    { docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -c ambient_leader_acquired; }
crash()  { docker logs "$ACC_BACKEND_CONTAINER" 2>&1 | grep -c -E 'ambient_tick_crashed|ambient_tick_failed'; }
state()  { echo "$1: lease=$(lease) gauge=$(gauge) acquired_lines=$(acq) crash_lines=$(crash)"; }
# a tier-0 row the leader's flush pass must deliver (as an interrupt while
# the daily notification budget lasts — the drill raises it — or demoted
# to the digest once it is spent; either way `delivered_at` is the proof)
probe() {
  local id; id=$(psql_ "with ins as (insert into deliveries (id, category, tier, urgency, title, body, created_at) values (gen_random_uuid(), 'ops', 0, 5, '$1', 'probe', now()) returning id) select id from ins")
  for i in $(seq 1 $((TICK * 4))); do
    [ "$(psql_ "select delivered_at is not null from deliveries where id='$id'")" = "t" ] && { echo "probe '$1' flushed by the tick after ${i}s"; return 0; }
    sleep 1
  done
  echo "probe '$1' NOT flushed within $((TICK * 4))s — the tick is stalled"; return 1
}
on()  { curl -s -X PATCH "$API/settings" -H "$H" -d '{"ambient_enabled": true}' -o /dev/null; }
off() { curl -s -X PATCH "$API/settings" -H "$H" -d '{"ambient_enabled": false}' -o /dev/null; }

initial=$(curl -s "$API/settings" | py 'print(json.dumps({k: d[k] for k in ("ambient_enabled", "ambient_tick_interval_s", "ambient_notification_budget_per_day")}))')
say "initial settings: $initial"
say "settings ← ambient_enabled=true, ambient_tick_interval_s=$TICK, ambient_notification_budget_per_day=50 (so every probe can interrupt)"
curl -s -X PATCH "$API/settings" -H "$H" -d "{\"ambient_enabled\": true, \"ambient_tick_interval_s\": $TICK, \"ambient_notification_budget_per_day\": 50}" | py 'print({k: d[k] for k in ("ambient_enabled", "ambient_tick_interval_s", "ambient_notification_budget_per_day")})'
echo "the loop picks the new interval up after its current wait — one old interval at most"
state baseline
probe "baseline: tick alive"

for cycle in 1 2; do
  say "switch cycle $cycle: off, 1s, on (the Settings switch)"
  before=$(acq); off; sleep 1; on
  echo "waiting two ticks ($((TICK * 2))s)"; sleep $((TICK * 2 + 2))
  state "after switch cycle $cycle"
  echo "a tick landed inside the dark second: $([ "$(acq)" -gt "$before" ] && echo yes — the lease was surrendered and re-acquired || echo no — the loop never saw it dark)"
  probe "switch cycle $cycle: tick alive after off→on"
done

for cycle in 1 2; do
  say "held cycle $cycle: off for a full tick ($((TICK + 3))s) so the tick sees ambient dark, then on"
  before=$(acq); off
  sleep $((TICK + 3))
  state "while dark"
  on
  echo "waiting two ticks ($((TICK * 2))s)"; sleep $((TICK * 2 + 2))
  state "after held cycle $cycle"
  echo "re-acquired: $([ "$(acq)" -gt "$before" ] && echo "yes (ambient_leader_acquired +$(( $(acq) - before )))" || echo NO)"
  probe "held cycle $cycle: tick alive after off→on"
done

say "the loop's own log lines during the drill"
docker logs --since "$((TICK * 14 + 60))s" "$ACC_BACKEND_CONTAINER" 2>&1 | grep -E 'ambient_leader|ambient_tick|ambient_delivered|ambient_interrupt' | cut -c1-160 | tail -n 16

say "settings restored ← $initial"
curl -s -X PATCH "$API/settings" -H "$H" -d "$initial" -o /dev/null
say "verdict: lease=$(lease) gauge=$(gauge) crash_lines=$(crash) — $([ "$(lease)" = 1 ] && [ "$(gauge)" = 1.0 ] && echo 'the tick leads after every off→on cycle' || echo 'STALLED')"
