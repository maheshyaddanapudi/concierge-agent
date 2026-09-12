#!/usr/bin/env bash
# The hardening wave through the API and the operator's other eyes: an
# operator's tool description surviving a re-ingest, a tool_key rename
# refused on a sanitized-name collision and on a skill mention, an MCP
# config edit reconnecting at once with its log line, definition versions
# on skills, a run's pinned settings / prompts / context / catalog slices,
# the formatter as a step, the cost stamped at finish and unmoved by a
# price change, the eval judge role, and the registry overlap audit gate.
# Uses the seeded `demo-stub` server. Restores what it changed.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
API=$(api_root)
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
echo "# hardening wave — $(date -u +%FT%TZ) — model $(curl -s "$API/settings" | py 'print(d["default_model"])')"

tool_id() { curl -s "$API/tools?limit=300" | KEY="$1" py 'import os; print([t["id"] for t in d if t["tool_key"]==os.environ["KEY"]][0])'; }
tool_desc() { curl -s "$API/tools/$1" | py 'print(json.dumps({"description": d["description"], "source": d["description_source"], "hash": (d["description_hash"] or "")[:12]}))'; }
ask() {  # ask <message> → run id, waits for the end
  local run; run=$(curl -s -X POST "$API/chat" -H "$H" -d "{\"message\": \"$1\"}" | py 'print(d["run_id"])')
  echo "run $run → $(wait_run "$run" 240)" >&2; echo "$run"
}

BEFORE=$(curl -s "$API/settings" | py 'print(json.dumps({k: d[k] for k in ("formatter_enabled","evals_enabled","model_prices")}))')
say "settings ← formatter on, evals on, a price override for the live model"
MODEL=$(curl -s "$API/settings" | py 'print(d["default_model"])')
curl -s -X PATCH "$API/settings" -H "$H" -d "{\"formatter_enabled\": true, \"evals_enabled\": true, \"model_prices\": {\"$MODEL\": {\"input_per_m\": 1.0, \"output_per_m\": 2.0}}}" -o /dev/null
STUB=$(curl -s "$API/mcp-servers" | py 'print([s["id"] for s in d if s["name"]=="demo-stub"][0])')
ECHO=$(tool_id demo-stub.echo)
curl -s -X PATCH "$API/tools/$ECHO" -H "$H" -d '{"status": "active"}' -o /dev/null

say "A. the operator's wording survives a re-ingest (§3.2 description drift)"
echo "  before: $(tool_desc "$ECHO")"
curl -s -X PATCH "$API/tools/$ECHO" -H "$H" -d '{"description": "Operator: echoes the given word back - never anything else."}' -o /dev/null
echo "  operator edit: $(tool_desc "$ECHO")"
curl -s -X POST "$API/mcp-servers/$STUB/refresh-tools" -o /dev/null; sleep 2
echo "  after refresh-tools: $(tool_desc "$ECHO")"

say "A. a tool_key rename is refused on a sanitized-name collision and while a skill mentions the old key"
ADD=$(tool_id demo-stub.add)
echo "  rename add → demo-stub_echo (sanitizes like demo-stub.echo): $(curl -s -o /dev/null -w '%{http_code}' -X PATCH "$API/tools/$ADD" -H "$H" -d '{"tool_key": "demo-stub_echo"}')"
SK=$(curl -s -X POST "$API/skills" -H "$H" -d "{\"name\": \"hw-drill-skill\", \"description\": \"echoes a word through the demo-stub echo tool (hardening-wave drill)\", \"persona\": \"You echo.\", \"instructions\": \"## Steps\\n1. Call {tool:demo-stub.echo} with the word.\\n2. Reply verbatim.\", \"tool_ids\": [\"$ECHO\"], \"direct_exposure\": true}")
SKID=$(echo "$SK" | py 'print(d["id"])')
echo "  skill hw-drill-skill: definition v$(echo "$SK" | py 'print(d["definition_version"])') hash=$(echo "$SK" | py 'print((d["definition_hash"] or "")[:12])')"
echo "  rename echo → demo-stub.echo2 while the skill mentions {tool:demo-stub.echo}: $(curl -s -X PATCH "$API/tools/$ECHO" -H "$H" -d '{"tool_key": "demo-stub.echo2"}' | py 'print(d.get("detail", d)[:160] if isinstance(d.get("detail"), str) else d)')"

say "A. an MCP config edit is hashed, logged and reconnected at once"
ARGS=$(curl -s "$API/mcp-servers/$STUB" | py 'print(json.dumps(d["args"]))')
curl -s -X PATCH "$API/mcp-servers/$STUB" -H "$H" -d "{\"args\": $(echo "$ARGS" | py 'print(json.dumps(d + ["--hardening-wave"]))')}" | py 'print("  patched:", d["status"], "last_connected_at", d["last_connected_at"])'
docker logs --since 1m "$ACC_BACKEND_CONTAINER" 2>&1 | grep -E 'mcp_server_config_changed|mcp_tools_ingested' | tail -n 2 | cut -c1-240
curl -s -X PATCH "$API/mcp-servers/$STUB" -H "$H" -d "{\"args\": $ARGS}" -o /dev/null; sleep 2
echo "  args restored"

say "B. definition versions: a toggle is not a version, an edit is"
echo "  direct_exposure off: v$(curl -s -X PATCH "$API/skills/$SKID" -H "$H" -d '{"direct_exposure": false}' | py 'print(d["definition_version"])')"
echo "  direct_exposure on:  v$(curl -s -X PATCH "$API/skills/$SKID" -H "$H" -d '{"direct_exposure": true}' | py 'print(d["definition_version"])')"
echo "  persona edited:      v$(curl -s -X PATCH "$API/skills/$SKID" -H "$H" -d '{"persona": "You echo exactly."}' | py 'print(d["definition_version"])')"

say "B. a run pins its settings, prompts, context and catalog slices; the formatter is a step; the cost is stamped"
R1=$(ask "Use the hw-drill-skill skill to echo the word pinned.")
curl -s "$API/runs/$R1" > "$TMP"
python3 - "$TMP" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for s in d["steps"]:
    if s["step_type"] in ("skill", "format", "route"):
        print(f"  {s['step_type']:6} {s.get('node_id') or '':10} entity={s.get('entity_name')} version={s.get('entity_version')} model={s.get('model')} params={s.get('model_params')}")
snap = d.get("snapshot") or {}
print(f"  snapshot keys: {sorted(snap)}")
print(f"  settings.default_model={snap.get('settings', {}).get('default_model')} prompts={len(snap.get('prompts') or {})} files build={snap.get('build')}")
print(f"  context surfaces: {[c.get('surface') for c in snap.get('context') or []]} catalog_calls={len(snap.get('catalog_calls') or [])}")
print(f"  cost_usd={d.get('cost_usd')} cost_priced={d.get('cost_priced')} price_snapshot={json.dumps(d.get('price_snapshot'))[:200]}")
EOF
COST=$(curl -s "$API/runs/$R1" | py 'print(d["cost_usd"])')
say "B. the price doubles afterwards: the finished run does not move"
curl -s -X PATCH "$API/settings" -H "$H" -d "{\"model_prices\": {\"$MODEL\": {\"input_per_m\": 2.0, \"output_per_m\": 4.0}}}" -o /dev/null
echo "  run cost before=$COST after=$(curl -s "$API/runs/$R1" | py 'print(d["cost_usd"])') price_snapshot input_per_m=$(curl -s "$API/runs/$R1" | py 'print(list(d["price_snapshot"]["prices"].values())[0]["input_per_m"])')"

say "C. the eval judge's own role and the overlap audit gate"
echo "  eval_judge_model=$MODEL: $(curl -s -o /dev/null -w '%{http_code}' -X PATCH "$API/settings" -H "$H" -d "{\"eval_judge_model\": \"$MODEL\"}")"
echo "  params without a model: $(curl -s -o /dev/null -w '%{http_code}' -X PATCH "$API/settings" -H "$H" -d '{"eval_judge_model": null, "eval_judge_model_params": {"effort": "low"}}') (422 like the other roles)"
echo "  registry_overlap_audit_enabled=yes: $(curl -s -o /dev/null -w '%{http_code}' -X PATCH "$API/settings" -H "$H" -d '{"registry_overlap_audit_enabled": "yes"}') (422)"
echo "  registry_overlap_audit_enabled=true: $(curl -s -o /dev/null -w '%{http_code}' -X PATCH "$API/settings" -H "$H" -d '{"registry_overlap_audit_enabled": true}')"
echo "  the audit job in the lifecycle map: $(docker exec "$ACC_BACKEND_CONTAINER" python -c 'from app.memory import lifecycle as l; print(l._JOB_NAMES[l.JOB_OVERLAP_AUDIT], l.JOB_GATES[l.JOB_OVERLAP_AUDIT], l._INTERVALS_S[l.JOB_OVERLAP_AUDIT], "s")')"

say "restored"
curl -s -X DELETE "$API/skills/$SKID" -o /dev/null
curl -s -X PATCH "$API/settings" -H "$H" -d "$(echo "$BEFORE" | py 'd.update({"eval_judge_model": None, "eval_judge_model_params": None, "registry_overlap_audit_enabled": False}); print(json.dumps(d))')" -o /dev/null
echo "  skill deleted; formatter, evals, prices, judge and audit as before"
