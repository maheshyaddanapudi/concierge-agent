#!/usr/bin/env bash
# M56 — the spec §14 acceptance script (steps 1–11) driven through the
# shipped API on the live model, the admin UI screenshotted after each step.
# With ACC_BOOT=1 it starts from `docker compose down -v && up -d` using the
# caller's COMPOSE_FILE / profile environment; otherwise it runs on the stack
# already up. Output: transcript on stdout; frames under ACC_SHOTS.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
ACC_SHOTS=${ACC_SHOTS:-$ACC_HERE/shots/m56-ceremony}; mkdir -p "$ACC_SHOTS"
cd "$ACC_ROOT" || exit 1

echo "# acceptance ceremony — spec §14 steps 1–11 — $(date -u +%FT%TZ)"
if [ "${ACC_BOOT:-0}" = "1" ]; then
  say "fresh slate: docker compose down -v; docker compose up -d"
  docker compose down -v --remove-orphans 2>&1 | tail -1
  docker compose up -d 2>&1 | tail -2
  API=$(api_root); wait_ready
fi
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep concierge
curl -s $API/settings | py 'print("default_model at first boot:", d["default_model"])'
curl -s -X PATCH $API/settings -H "$H" -d "{\"default_model\":\"$ACC_MODEL\",\"formatter_enabled\":false,\"orchestrator_mode\":\"graph\"}" | py 'print("PATCH /settings →", d["default_model"], d["orchestrator_mode"])'

say "step 1 — the seed: MCP servers, static tools, native skills, research-concierge"
curl -s $API/mcp-servers | py 'print("mcp servers:", [(s["name"], s["status"], s["tool_count"]) for s in d])'
curl -s "$API/tools?limit=100" | py 'import collections; print("tools:", len(d), dict(collections.Counter((t["kind"], t["source"]) for t in d)))'
curl -s $API/skills | py 'print("skills:", [(s["name"], s["kind"]) for s in d])'
curl -s $API/sub-agents | py 'print("sub agents:", [(s["name"], s["kind"]) for s in d])'
shot 01-seed-tools tools

say "step 2 — register a new stdio MCP server → its tools appear with {server}.{tool} keys"
for id in $(curl -s $API/mcp-servers | py 'print(" ".join(s["id"] for s in d if s["name"]=="demo-stub"))'); do curl -s -X DELETE $API/mcp-servers/$id -o /dev/null; done
STUB=$(curl -s -X POST $API/mcp-servers -H "$H" -d '{"name":"demo-stub","description":"the test stub server: echo, add, mutate_toolset","transport":"stdio","command":"python","args":["/app/tests/stub_mcp_server.py"]}' | py 'print(d["id"])')
sleep 2; curl -s $API/mcp-servers/$STUB | py 'print("server:", d["name"], d["status"], "tools", d["tool_count"])'
curl -s "$API/tools?limit=100" | py 'print("new tool keys:", sorted(t["tool_key"] for t in d if t["tool_key"].startswith("demo-stub.")))'
shot 02-mcp-registered mcp-servers

say "step 3 — custom skill summarize-site from those tools + persona; badges on Tools and Skills"
TIDS=$(curl -s "$API/tools?limit=100" | py 'print(json.dumps([t["id"] for t in d if t["tool_key"] in ("demo-stub.echo","demo-stub.add")]))')
SKILL=$(curl -s -X POST $API/skills -H "$H" -d "{\"name\":\"summarize-site\",\"description\":\"Echo the user's text back and add two numbers with the demo-stub tools, then summarize in one line.\",\"persona\":\"You are a terse site summarizer.\",\"instructions\":\"# Purpose\\nUse demo-stub.echo to echo the request, demo-stub.add to add any two numbers mentioned, then answer in one line.\",\"tool_ids\":$TIDS}" | py 'print(d["id"])')
curl -s $API/skills/$SKILL | py 'print("skill:", d["name"], d["kind"], "tools", [t["tool_key"] for t in d.get("tools", [])])'
curl -s $API/tools/$(echo $TIDS | py 'print(d[0])') | py 'print("tool badge (used by skills):", [s["name"] for s in d.get("skills", [])])'
shot 03-skill-created skills

say "step 4 — toggle direct_exposure on one tool; the next chat's trace shows a rung-1 route step"
ECHO_ID=$(curl -s "$API/tools?limit=100" | py 'print([t["id"] for t in d if t["tool_key"]=="demo-stub.echo"][0])')
curl -s -X PATCH $API/tools/$ECHO_ID -H "$H" -d '{"direct_exposure":true}' | py 'print("PATCH →", d["tool_key"], "direct_exposure", d["direct_exposure"])'
R4=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Use the demo-stub echo tool to echo exactly: ceremony step four"}' | py 'print(d["run_id"])')
echo "run $R4 → $(wait_run $R4)"; steps $R4
shot 04-direct-exposure-run runs

say "step 5 — sub agent with a branch, an error edge and an HITL node; a validation error is rejected inline, then fixed"
WF_BAD="{\"nodes\":[{\"id\":\"sum\",\"type\":\"skill\",\"skill_id\":\"$SKILL\"},{\"id\":\"approve\",\"type\":\"hitl\",\"prompt\":\"Publish the summary?\"},{\"id\":\"recover\",\"type\":\"skill\",\"skill_id\":\"$SKILL\"}],\"edges\":[{\"from\":\"START\",\"to\":\"sum\"},{\"from\":\"sum\",\"to\":\"approve\",\"condition\":\"if a summary was produced\"},{\"from\":\"sum\",\"to\":\"END\",\"condition\":\"if nothing to summarize\"},{\"from\":\"sum\",\"to\":\"recover\",\"on\":\"error\"},{\"from\":\"recover\",\"to\":\"END\"},{\"from\":\"approve\",\"to\":\"ghost\"}]}"
curl -s -X POST $API/sub-agents -H "$H" -d "{\"name\":\"site-reporter\",\"description\":\"Summarizes a site and asks before publishing.\",\"persona\":\"You are a careful reporter.\",\"workflow\":$WF_BAD}" -w '\n→ HTTP %{http_code}\n' | cut -c1-200
WF_OK=${WF_BAD/\"to\":\"ghost\"/\"to\":\"END\"}
AGENT=$(curl -s -X POST $API/sub-agents -H "$H" -d "{\"name\":\"site-reporter\",\"description\":\"Summarizes a site and asks before publishing.\",\"persona\":\"You are a careful reporter.\",\"workflow\":$WF_OK,\"direct_exposure\":true}" | py 'print(d["id"])')
curl -s $API/sub-agents/$AGENT | py 'print("sub agent:", d["name"], d["kind"], "nodes", [n["id"]+":"+n["type"] for n in d["workflow"]["nodes"]], "edges", len(d["workflow"]["edges"]))'
shot 05-sub-agent sub-agents

say "step 6 — multi-turn chat: message 1 invokes the new sub agent (HITL approved mid-run); message 2 follows up on message 1's result"
R6=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Ask the site-reporter sub agent to summarize this: the demo site says 21 and 21 make the answer; publish the summary."}' | py 'print(d["run_id"])')
CONV=$(curl -s $API/runs/$R6 | py 'print(d["conversation_id"])')
for i in $(seq 1 180); do st=$(curl -s $API/runs/$R6 | py 'print(d["status"])'); [ "$st" = "paused_hitl" ] && { echo "run $R6 paused at the HITL gate after ${i}s"; break; }; case "$st" in completed|failed|cancelled) echo "run ended $st before a gate"; break;; esac; sleep 1; done
shot 06a-hitl-card chat
curl -s -X POST $API/runs/$R6/hitl -H "$H" -d '{"decision":"approve","note":"ceremony approves"}' | py 'print("hitl →", d)'
echo "run $R6 → $(wait_run $R6)"; steps $R6
curl -s $API/runs/$R6 | py 'print("answer:", (d.get("final_answer") or "")[:160])'
R6B=$(curl -s -X POST $API/chat -H "$H" -d "{\"conversation_id\":\"$CONV\",\"message\":\"What number did the summary you just produced mention? Answer with the number only.\"}" | py 'print(d["run_id"])')
echo "run $R6B → $(wait_run $R6B)"; curl -s $API/runs/$R6B | py 'print("follow-up answer:", (d.get("final_answer") or "")[:120])'
shot 06b-multi-turn chat

say "step 7 — something no capability covers → the planner reports no confident match; the trace shows the fallback route rung"
R7=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Use the invoice-reconciler capability to reconcile last month'"'"'s supplier invoices against the ledger and list the mismatches."}' | py 'print(d["run_id"])')
echo "run $R7 → $(wait_run $R7)"; steps $R7
curl -s $API/runs/$R7 | py 'print("answer:", (d.get("final_answer") or "")[:140])'

say "step 8 — kill the new MCP server process → invoke again → the server shows error; reconnect from the API"
kill_stub; sleep 1
R8=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Ask the site-reporter sub agent to summarize this: 2 and 3 make five; publish it."}' | py 'print(d["run_id"])')
echo "run $R8 → $(approve_when_paused $R8 120)"; steps $R8
curl -s $API/mcp-servers/$STUB | py 'print("server after the kill (a stdio server respawns on next use):", d["status"], "|", (d.get("last_error") or "")[:80])'
echo "(the visible error state: point the server at a binary that does not exist, reconnect, then restore — the same lifecycle the UI drives)"
curl -s -X PATCH $API/mcp-servers/$STUB -H "$H" -d '{"command":"/nonexistent-mcp-binary"}' -o /dev/null
curl -s -X POST $API/mcp-servers/$STUB/reconnect | py 'print("reconnect with a broken command →", d["status"], "|", (d.get("last_error") or "")[:90])'
curl -s -X PATCH $API/mcp-servers/$STUB -H "$H" -d '{"command":"python"}' -o /dev/null
curl -s -X POST $API/mcp-servers/$STUB/reconnect | py 'print("reconnect restored →", d["status"], "tools", d["tool_count"])'
shot 08-server-reconnected mcp-servers

say "step 9 — Runs page: full trace with nested steps, tokens, route reasons; cancel a running run; retry a failed one"
curl -s $API/runs/$R6 | py 'print("trace:", len(d["steps"]), "steps; tokens", sum((s.get("input_tokens") or 0) for s in d["steps"]), "→", sum((s.get("output_tokens") or 0) for s in d["steps"]), "; nested:", sum(1 for s in d["steps"] if s.get("parent_step_id")))'
R9=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Write 800 words on the history of container orchestration."}' | py 'print(d["run_id"])')
sleep 3; curl -s -X POST $API/runs/$R9/cancel | py 'print("cancel →", d)'
curl -s $API/runs/$R9 | py 'print(d["status"], (d.get("error") or "")[:60])'
echo "(a run that fails truthfully: run_wall_clock_s=30 — the admission ceiling — under a long essay)"
curl -s -X PATCH $API/settings -H "$H" -d '{"run_wall_clock_s":30}' | py 'print("run_wall_clock_s →", d["run_wall_clock_s"])'
R9F=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Write a 1500-word essay on the history of container orchestration, with sections and a conclusion."}' | py 'print(d["run_id"])'); echo "run under the 30 s wall clock $R9F → $(wait_run $R9F)"
curl -s $API/runs/$R9F | py 'print(d["status"], (d.get("error") or "")[:80])'
curl -s -X PATCH $API/settings -H "$H" -d '{"run_wall_clock_s":900}' -o /dev/null
R9R=$(curl -s -X POST $API/runs/$R9F/retry | py 'print(d.get("run_id",""))'); echo "retry → run $R9R → $(wait_run $R9R)"
shot 09-runs runs

say "step 10 — Settings: change the planner model → the next run's trace labels show it"
curl -s -X PATCH $API/settings -H "$H" -d "{\"planner_model\":\"$ACC_MODEL\"}" | py 'print("planner_model →", d["planner_model"])'
R10=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Use demo-stub add to add 40 and 2."}' | py 'print(d["run_id"])')
echo "run $R10 → $(wait_run $R10)"; curl -s $API/runs/$R10 | py 'print("step models:", [(s["step_type"], s.get("model")) for s in d["steps"] if s.get("model")][:4])'
curl -s -X PATCH $API/settings -H "$H" -d '{"planner_model":null}' -o /dev/null
shot 10-settings settings

say "step 11 — orchestrator_mode=agentic: repeat step 6's first message; the sub agent is a dispatch tool, the HITL card still gates"
curl -s -X PATCH $API/settings -H "$H" -d '{"orchestrator_mode":"agentic"}' | py 'print("orchestrator_mode →", d["orchestrator_mode"])'
R11=$(curl -s -X POST $API/chat -H "$H" -d '{"message":"Ask the site-reporter sub agent to summarize this: the demo site says 21 and 21 make the answer; publish the summary."}' | py 'print(d["run_id"])')
echo "run $R11 → $(approve_when_paused $R11 180)"
curl -s "$API/chat/stream/$R11" --max-time 5 | grep -E "^event:" | sort | uniq -c | tr '\n' ' '; echo
steps $R11
curl -s -X PATCH $API/settings -H "$H" -d '{"orchestrator_mode":"graph"}' -o /dev/null
shot 11-agentic chat
echo "# end — $(date -u +%FT%TZ)"
