#!/usr/bin/env bash
# Tool schema drift (spec §3.2) through the API and the operator's other
# eyes: the ingest log line, the metric, the tool row, a run's tool-call
# step and its frozen snapshot. The seeded `demo-stub` server renames
# `echo`'s parameter when its `mutate_schema` tool is called; a live run
# calls it. First under the warn policy, then under quarantine, acknowledged
# through the API. Leaves the policy on warn and the mutator unexposed.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ROOT=${API%/api/v1}
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
echo "# schema drift — $(date -u +%FT%TZ) — model $(curl -s "$API/settings" | py 'print(d["default_model"])')"

tool() { KEY="$1" curl -s "$API/tools?limit=300" | KEY="$1" py 'import os; t=[t for t in d if t["tool_key"]==os.environ["KEY"]][0]; print(json.dumps({k: t[k] for k in ("id","status","ingest_state","schema_version","schema_changed_at")} | {"schema_hash": (t["schema_hash"] or "")[:12], "params": list((t.get("input_schema") or {}).get("properties", {}))}))'; }
tool_id() { curl -s "$API/tools?limit=300" | KEY="$1" py 'import os; print([t["id"] for t in d if t["tool_key"]==os.environ["KEY"]][0])'; }
metric() { curl -s "$ROOT/metrics" | grep '^concierge_tool_schema_changes_total' || echo "(no concierge_tool_schema_changes_total samples yet)"; }
ask() {  # ask <message> → run id, waits for the end
  local run; run=$(curl -s -X POST "$API/chat" -H "$H" -d "{\"message\": \"$1\"}" | py 'print(d["run_id"])')
  echo "run $run → $(wait_run "$run" 240)" >&2; echo "$run"
}
mutate() {  # a run that really calls demo-stub.mutate_schema — the planner is a model call and may pick echo instead, so the route is checked and the ask repeated (3 attempts)
  for attempt in 1 2 3; do
    local run; run=$(ask "Call the tool named demo-stub.mutate_schema — not echo, not add — with no arguments, and report its reply verbatim.")
    local routed; routed=$(curl -s "$API/runs/$run" | py 'print(",".join(((s.get("output") or {}).get("resolved_to") or {}).get("entity_name","") for s in d["steps"] if s["step_type"]=="route"))')
    echo "  attempt $attempt routed to: $routed" >&2
    case "$routed" in *mutate_schema*) return 0;; esac
  done
  echo "  the planner never routed to mutate_schema" >&2; return 1
}
wait_version() {  # wait_version <key> <greater-than>
  for i in $(seq 1 30); do
    v=$(curl -s "$API/tools?limit=300" | KEY="$1" py 'import os; print([t["schema_version"] for t in d if t["tool_key"]==os.environ["KEY"]][0])')
    [ "$v" -gt "$2" ] && { echo "schema_version $2 → $v after ${i}s"; return 0; }
    sleep 1
  done
  echo "schema_version did not move past $2 within 30s"; return 1
}

say "settings ← mcp_schema_change_policy=warn; the demo-stub server reconnected (the image's stub carries mutate_schema)"
curl -s -X PATCH "$API/settings" -H "$H" -d '{"mcp_schema_change_policy": "warn"}' -o /dev/null
STUB=$(curl -s "$API/mcp-servers" | py 'print([s["id"] for s in d if s["name"]=="demo-stub"][0])')
curl -s -X POST "$API/mcp-servers/$STUB/reconnect" -o /dev/null; sleep 3
MUT=$(tool_id demo-stub.mutate_schema); ECHO=$(tool_id demo-stub.echo)
curl -s -X PATCH "$API/tools/$MUT" -H "$H" -d '{"direct_exposure": true}' -o /dev/null
curl -s -X PATCH "$API/tools/$ECHO" -H "$H" -d '{"direct_exposure": true}' -o /dev/null
curl -s -X POST "$API/tools/$ECHO/acknowledge-schema" -o /dev/null
say "demo-stub.echo before: $(tool demo-stub.echo)"
V0=$(curl -s "$API/tools/$ECHO" | py 'print(d["schema_version"])')
P0=$(curl -s "$API/tools/$ECHO" | py 'print(list(d["input_schema"]["properties"])[0])')

say "a run that calls echo (v$V0): the tool_call step and the run snapshot pin the version"
R1=$(ask "Use the demo-stub echo tool to echo the word drift, passing it as the $P0 argument.")
curl -s "$API/runs/$R1" > "$TMP"
python3 - "$TMP" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for s in d["steps"]:
    if s["step_type"] == "tool_call":
        print(f"  tool_call {s.get('node_id')}: entity_version={s.get('entity_version')} entity_hash={(s.get('entity_hash') or '')[:12]}")
snap = (d.get("snapshot") or {}).get("s1") or {}
p = snap.get("payload") or {}
print(f"  snapshot s1: rung={snap.get('rung')} schema_version={p.get('schema_version')} schema_hash={(p.get('schema_hash') or '')[:12]} params={list((p.get('input_schema') or {}).get('properties', {}))}")
EOF

say "the server renames the parameter: a run calls demo-stub.mutate_schema"
mutate
wait_version demo-stub.echo "$V0"
say "demo-stub.echo after (warn): $(tool demo-stub.echo)"
say "the ingest log line"
docker logs --since 3m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -E 'tool_schema_changed|mcp_tools_ingested' | tail -n 3 | cut -c1-260
say "the metric"; metric
say "acknowledged through the API (the flag clears, the version stays)"
curl -s -X POST "$API/tools/$ECHO/acknowledge-schema" | py 'print({k: d[k] for k in ("status","ingest_state","schema_version","schema_changed_at")})'

say "settings ← mcp_schema_change_policy=quarantine; the same change again (the stub flips the parameter back)"
curl -s -X PATCH "$API/settings" -H "$H" -d '{"mcp_schema_change_policy": "quarantine"}' -o /dev/null
V1=$(curl -s "$API/tools/$ECHO" | py 'print(d["schema_version"])')
mutate
wait_version demo-stub.echo "$V1"
say "demo-stub.echo after (quarantine): $(tool demo-stub.echo)"
say "a re-ingest does not put it back"
curl -s -X POST "$API/mcp-servers/$STUB/refresh-tools" -o /dev/null; sleep 2
echo "$(tool demo-stub.echo)"
say "an ask that needs echo while it is quarantined"
R2=$(ask "Use the demo-stub echo tool to echo the word drift.")
curl -s "$API/runs/$R2" | py 'print("  status:", d["status"], "| routes:", [ (s.get("output") or {}).get("rung") for s in d["steps"] if s["step_type"]=="route"], "| tool calls:", [s.get("node_id") for s in d["steps"] if s["step_type"]=="tool_call"])'
say "acknowledged: back in service"
curl -s -X POST "$API/tools/$ECHO/acknowledge-schema" | py 'print({k: d[k] for k in ("status","ingest_state","schema_version","schema_changed_at")})'
say "the metric now"; metric

say "restored: policy warn, mutate_schema unexposed"
curl -s -X PATCH "$API/settings" -H "$H" -d '{"mcp_schema_change_policy": "warn"}' -o /dev/null
curl -s -X PATCH "$API/tools/$MUT" -H "$H" -d '{"direct_exposure": false}' -o /dev/null
say "verdict: $(tool demo-stub.echo)"
