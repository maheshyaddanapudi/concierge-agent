#!/usr/bin/env bash
# Ceremony addendum: step 8 via direct invocation (the DAG's error edge
# taken to a tool-less recover skill), and step 11 with a multi-step ask so
# the agentic todo list streams as plan events. Runs after m56-ceremony.sh
# on the same stack.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
cd "$ACC_ROOT" || exit 1
echo "# ceremony addendum — $(date -u +%FT%TZ)"

say "step 8 (second pass) — the sub agent invoked DIRECTLY (spec §7.5) so its DAG runs: a tool-less 'apology-note' skill on the recover branch, the stub broken, the error edge taken, the run completes via recover"
curl -s -X PATCH $API/settings -H "$H" -d '{"orchestrator_mode":"graph"}' -o /dev/null
AGENT=$(curl -s $API/sub-agents | py 'print([a["id"] for a in d if a["name"]=="site-reporter"][0])')
SKILL=$(curl -s $API/skills | py 'print([s["id"] for s in d if s["name"]=="summarize-site"][0])')
for id in $(curl -s $API/skills | py 'print(" ".join(s["id"] for s in d if s["name"]=="apology-note"))'); do curl -s -X DELETE $API/skills/$id -o /dev/null; done
NOTE=$(curl -s -X POST $API/skills -H "$H" -d '{"name":"apology-note","description":"Writes a one-line note explaining that the summary could not be produced.","persona":"You are a candid operator.","instructions":"# Purpose\nIn one line, say the summary could not be produced and why, using no tools.","tool_ids":[]}' | py 'print(d["id"])')
WF="{\"nodes\":[{\"id\":\"sum\",\"type\":\"skill\",\"skill_id\":\"$SKILL\"},{\"id\":\"approve\",\"type\":\"hitl\",\"prompt\":\"Publish the summary?\"},{\"id\":\"recover\",\"type\":\"skill\",\"skill_id\":\"$NOTE\"}],\"edges\":[{\"from\":\"START\",\"to\":\"sum\"},{\"from\":\"sum\",\"to\":\"approve\",\"condition\":\"if a summary was produced\"},{\"from\":\"sum\",\"to\":\"END\",\"condition\":\"if nothing to summarize\"},{\"from\":\"sum\",\"to\":\"recover\",\"on\":\"error\"},{\"from\":\"recover\",\"to\":\"END\"},{\"from\":\"approve\",\"to\":\"END\"}]}"
curl -s -X PATCH $API/sub-agents/$AGENT -H "$H" -d "{\"workflow\":$WF}" | py 'print("PATCH sub agent → nodes", [n["id"] for n in d["workflow"]["nodes"]])'
kill_stub
STUB=$(curl -s $API/mcp-servers | py 'print([s["id"] for s in d if s["name"]=="demo-stub"][0])')
curl -s -X PATCH $API/mcp-servers/$STUB -H "$H" -d '{"command":"/nonexistent-mcp-binary"}' -o /dev/null; curl -s -X POST $API/mcp-servers/$STUB/reconnect | py 'print("server:", d["status"], "|", (d.get("last_error") or "")[:60])'
R8=$(curl -s -X POST $API/sub-agents/$AGENT/invoke -H "$H" -d '{"message":"Summarize this: 2 and 3 make five; publish it."}' | py 'print(d["run_id"])')
echo "direct invocation run $R8 → $(wait_run $R8)"
curl -s $API/runs/$R8 | py 'print([(s["step_type"], s.get("node_id"), s["status"]) for s in d["steps"]]); print("answer:", (d.get("final_answer") or "")[:160])'
curl -s -X PATCH $API/mcp-servers/$STUB -H "$H" -d '{"command":"python"}' -o /dev/null; curl -s -X POST $API/mcp-servers/$STUB/reconnect | py 'print("server restored:", d["status"], "tools", d["tool_count"])'

say "step 11 (addendum) — agentic mode with a multi-step ask: the todo list streams as plan events"
curl -s -X PATCH $API/settings -H "$H" -d '{"orchestrator_mode":"agentic"}' -o /dev/null
R11=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Plan this as a todo list and work through it: first use demo-stub add to add 40 and 2, then use demo-stub echo to echo the result, then report both."}' | py 'print(d["run_id"])')
echo "run $R11 → $(wait_run $R11)"
curl -s "$API/chat/stream/$R11" --max-time 5 | grep -A1 "^event: plan" | grep "^data:" | python3 -c "
import sys,json
for line in sys.stdin:
    d=json.loads(line[6:]); p=d['payload']; print('plan event seq', d['seq'], 'mode', p.get('mode'), 'todos', [(t['content'][:45], t['status']) for t in (p.get('todos') or [])])" | head -6
curl -s -X PATCH $API/settings -H "$H" -d '{"orchestrator_mode":"graph"}' -o /dev/null
echo "# end — $(date -u +%FT%TZ)"
