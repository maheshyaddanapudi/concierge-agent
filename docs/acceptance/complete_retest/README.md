# Complete from-scratch retest — UI-driven, genuine model

Fresh `docker compose down -v && docker compose up` (empty DB, seeds only), then
**everything below done through the admin UI in a real Chromium browser** with
genuine `anthropic:claude-sonnet-4-6` decisions — no scripted model turns anywhere.
Driver log: `walkE.log`.

Key design point verified on this pass: the `site-analyst` description does **not**
contain the file path — it only says it *"reads the site notes and produces whatever
summary or analysis is required, asking for human approval before finishing"* — and
the orchestrator still routed to it implicitly in **both** modes.

| # | Screenshot | Proves |
|---|---|---|
| 01–02 | fresh home, seeded servers only | clean slate: two seeded MCP servers, nothing else |
| 03–04 | register form filled → `sitefiles` active | MCP server plugged from the UI, no restart |
| 05 | tools page | `sitefiles.*` ingested with `server.tool` keys |
| 06–07 | skill editor filled → saved | `summarize-site` authored: tool tag, `{tool:...}` mention, markdown body |
| 08 | tools page | skill badge appears on the bound tool |
| 09–11 | duplicate skill editor → **overlap dialog** → cancelled | LLM-judge guard flagged `site-summarizer` vs `summarize-site` ≥70%; cancel path; nothing saved |
| 12–13 | sub agent builder (Branch + HITL) → saved | `site-analyst` authored with path-free description |
| 12b | overlap dialog on first save | judge flagged the sub agent vs the skill it wraps — **Save anyway** path |
| 14 | duplicate sub agent dialog → cancelled | guard flagged `site-reviewer` vs `site-analyst`; cancel path |
| 15–19 | implicit chat: plan stream → HITL card → queue → answer+A2UI → trace | **graph mode routed `custom_sub_agent→site-analyst` with no sub agent named and no path in its description**; 1 hitl step; full trace |
| 20 | follow-up answer | conversation history reaches the planner |
| 21–23 | exposure toggle → chat → trace | rung 1: exposed tool wins for a plain listing (`direct_tool`) |
| 24 | settings | orchestrator switched to agentic from the UI |
| 25–26 | live todo card, two moments | agentic plan displayed **and updated** mid-run |
| 27–29 | agentic HITL card → answer → trace | agentic mode also dispatched site-analyst implicitly; pause/approve/resume |
| 30 | runs page | final run history for the whole retest |
