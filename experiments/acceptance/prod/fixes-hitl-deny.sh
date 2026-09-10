#!/usr/bin/env bash
# The campaign v1 finding 1 re-verified through the API: a gated sub agent
# is asked to summarize and publish, the gate is DENIED with a note, and
# the final answer must say the action was not performed and quote the
# note — before the fix the aggregator saw only the pre-gate draft and
# answered "[Published successfully]…". The sub agent must exist with a
# HITL node named `approve` after its summarizing skill (the stage 05
# `site-analyst` or the seeded `site-reporter`).
#   ACC_AGENT   sub agent to address (default site-reporter)
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
AGENT=${ACC_AGENT:-site-reporter}
NOTE="Do not publish — the source is a demo page, not a real site."
TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT
echo "# finding 1 re-verified — $(date -u +%FT%TZ) — agent $AGENT, model $(curl -s "$API/settings" | py 'print(d["default_model"])')"

say "POST /chat: Ask the $AGENT sub agent to summarize this: the demo site says 21 and 21 make the answer; publish the summary."
RUN=$(curl -s -X POST "$API/chat" -H "$H" -d "{\"message\": \"Ask the $AGENT sub agent to summarize this: the demo site says 21 and 21 make the answer; publish the summary.\"}" | py 'print(d["run_id"])')
echo "run $RUN"
for i in $(seq 1 150); do
  st=$(curl -s "$API/runs/$RUN" | py 'print(d["status"])')
  case "$st" in paused_hitl|completed|failed|cancelled) break;; esac
  sleep 2
done
echo "status after $((i * 2))s: $st"
[ "$st" = "paused_hitl" ] || { echo "no gate armed — the run ended $st:"; steps "$RUN"; exit 1; }

say "the gate (GET /hitl/pending for this run)"
curl -s "$API/hitl/pending" > "$TMP"
RUN="$RUN" python3 - "$TMP" <<'EOF'
import json, os, sys
d = json.load(open(sys.argv[1]))
items = d if isinstance(d, list) else d.get("items", [])
mine = [p for p in items if str(p.get("run_id")) == os.environ["RUN"]]
print(json.dumps(mine[0], indent=None)[:400] if mine else f"(no pending gate listed for this run; {len(items)} pending in all)")
EOF
say "POST /runs/$RUN/hitl {decision: deny, note: \"$NOTE\"}"
curl -s -X POST "$API/runs/$RUN/hitl" -H "$H" -d "{\"decision\": \"deny\", \"note\": \"$NOTE\"}"; echo
echo "$(wait_run "$RUN" 200)"

say "the steps (type, node, status, output/error excerpt)"
curl -s "$API/runs/$RUN" > "$TMP"
python3 - "$TMP" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for s in d["steps"]:
    o = s.get("output") or {}
    ex = s.get("error") or (o.get("output") if isinstance(o, dict) else "") or ""
    if isinstance(o, dict) and s["step_type"] == "hitl":
        ex = f"status={o.get('status')} note={o.get('note')}"
    if isinstance(o, dict) and s["step_type"] == "skill" and o.get("status") == "denied":
        ex = "status=denied — " + str(o.get("output"))[-170:]
    print(f"  {s['step_type']:10} {str(s.get('node_id') or '-'):14} {s['status']:10} {str(ex)[:220]!r}")
EOF
say "the answer"
ANSWER=$(curl -s "$API/runs/$RUN" | py 'print(d.get("answer") or d.get("final_answer") or "")')
echo "$ANSWER"
say "verdict"
echo "$ANSWER" | grep -q -i "not published\|was not performed\|not perform\|denied\|refused" && ! echo "$ANSWER" | grep -q -i "published successfully" \
  && echo "the answer reports the refusal$(echo "$ANSWER" | grep -q "demo page, not a real site" && echo ' and quotes the note')" \
  || echo "FAIL: the answer does not report the refusal"
