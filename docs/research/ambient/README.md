# Ambient mode research suite

**Branch:** `ambient_mode_exp` · **Date:** 2026-08-25 · Successor campaign to
`docs/research/memory/` (the memory layers this design builds on merged in
PR #14).

Ambient mode = the concierge doing useful, governed work **while the user is
not chatting**: watching for events, holding standing intents ("tell me
when…"), running routines, anticipating during idle time, and deciding when —
and whether — to initiate contact.

| Doc | What it holds | Read it for |
|---|---|---|
| [01-current-state.md](01-current-state.md) | Inventory of the platform against the trigger→decide→execute→deliver→govern pipeline: what memory/M13–M18 already provides (scheduler, headless runs, HITL, ledger) and the honest gap list (no trigger substrate, idle detector specced-not-built, no standing-intent store, no delivery policy) | why this is a promotion of existing assets, again |
| [02-landscape-production.md](02-landscape-production.md) | ChatGPT Tasks/monitoring/Pulse lifecycle, Claude Code Routines (the most complete shipped design), Claude Tag, Letta sleep-time, LangChain ambient agents + Agent Inbox, Gemini/Copilot caps, Home Assistant, Postgres-only eventing verdicts — 12 transferable mechanisms + anti-patterns | which shipped ideas transfer, with limits and pricing |
| [03-landscape-research.md](03-landscape-research.md) | Mixed-initiative foundations, proactive-agent benchmark ceilings, interruption science, prospective-memory failure data, standing-query heritage, autonomy/safety findings, evaluation recipes — 15 evidence-backed design rules | the numbers behind every design call |
| [04-architecture-proposal.md](04-architecture-proposal.md) | **The design**: five planes (A1 triggers, A2 three-tier wake gate, A3 routines/intents/anticipation, A4 digest-first delivery, A5 governance), schemas, §8.9 UI, measured goals, milestones **M20–M24**, settled decisions + open questions for sign-off | what we propose to build |

## The design in one paragraph

Events (schedules, webhooks, pollers, internal signals) land as untrusted
rows in an append-only table and wake the existing advisory-locked scheduler
via NOTIFY pings; a three-tier gate — typed matchers, then one cheap
significance judgment, then a full run — decides fire vs hold, and every
decision is audited. Fires create ordinary runs with trigger provenance,
executing routines (trusted stored prompts over a narrowed registry
projection, hard budgets, an abstain instruction, autonomy ceilings that
route consequential actions through the existing HITL gates with
absent-user timeouts). Results flow through a delivery outbox governed by a
predictable digest with an urgency bypass, a daily notification budget,
quiet hours, and per-category feedback that tunes itself. Standing intents
are typed Postgres rows — never remembered prompts — compiled once from
natural language and evaluated by the scheduler. All of it is dark by
default behind `ambient_enabled=false`, byte-identical when off, and
measured on a simulated-clock event harness before anything ships on.
