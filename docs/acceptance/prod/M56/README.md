# M56 — release: executed proof

The stage that turns the repository into something other people adopt.
What shipped: `LICENSE` (MIT), a root `CONTRIBUTING.md` over the
spec-driven guide, `SECURITY.md` with the auth-is-a-fork stance stated
plainly, issue and pull-request templates (no workflows), `CHANGELOG.md`
reconstructed from the milestone table for M13–M55 under a `v1.0.0`
heading, versions at 1.0.0, the README retold as what it is / what it is
not / run it / extend it, and the tag. What was proven on the release
images: the §14 acceptance script on a fresh `docker compose up`, and the
M49 load scenarios re-run as the performance record.

| file | what it is |
|---|---|
| `ceremony.md` + `01…11-*.png` | spec §14 steps 1–11 on empty volumes with the v1.0.0 images, `openrouter:qwen/qwen3.8-max`, driven through the shipped API with the admin UI screenshotted after each step: the seed (2 servers, 15 static tools, 2 skills, 3 sub agents); a stdio server registered and its four `demo-stub.*` tools keyed; `summarize-site` composed from them with the badges; `direct_exposure` on `demo-stub.echo` and the next run's trace routing at rung 1; a DAG with a branch, an error edge and a HITL node — the version with a dangling edge refused `422`, the fixed one saved; a multi-turn chat that paused at the HITL gate, was approved through the API and answered `42`, then a follow-up in the same conversation answered from message 1; an ask naming a capability that does not exist → `no_confident_match: true` and the `fallback` route rung; the stub killed and a run through the dead tools completing truthfully, the server `error | health ping failed`, then a broken command → `error | FileNotFoundError`, then restored `active tools 4`; a 10-step trace with six nested steps and token counts, a cancel (`cancelled`), a run failed truthfully under `run_wall_clock_s=30` (`exceeded the run wall clock`) and retried to `completed`; `planner_model` changed and the next trace's `plan` step labelled with it; `orchestrator_mode=agentic` repeating step 6 with the HITL gate holding and the sub agent reached as a dispatch tool |
| `ceremony-addendum.md` | steps 8 and 11 on the paths the spec intends: the sub agent invoked directly (§7.5) with a tool-less skill on its recover branch so the DAG's error edge is taken — `sum` fails, `recover` writes "Summary could not be produced because … its MCP server was not connected", the run completes; and a multi-step agentic ask whose todo list streams as three `plan` events (`in_progress` → `completed` across the items) |
| `perf-v1.md` + `perf-v1.json` | the M49 scenarios (read path, run-table growth 1k→10k, 5/10/25 concurrent chats, 60 SSE streams) on the v1.0.0 image at N=1 through the balancer, fake provider, clean settings — read path p50 33–65 ms; `/runs` flat from 1k to 10k rows (p50 14 → 15 ms at a 51 KB page); 25 concurrent chats all `completed` at e2e p50 6.3 s / p95 7.9 s, 3.1 runs/s, peak 22 connections (the per-process admission gate, `run_max_concurrent`, is the ceiling — N=3 in the M54 record does 11.3 runs/s); 60 open SSE streams with the health probe 3/3 at p50 13 ms on 12 connections |
| `tests.md` | the full suites on the release tree: backend 1068 passed / 1 skipped, frontend 94, static gates, both images built |

## Honest notes

- **The ceremony is API-driven with UI frames, not click-driven.** Earlier
  ceremonies drove the admin UI with Playwright; those scripts did not
  survive the environment reset. This one drives every step through the
  shipped API — the same calls the UI makes — and screenshots the page
  after each step. Two steps are inherently UI (the inline validation
  error, the HITL card): the API's `422` and `POST /runs/{id}/hitl` are the
  same code paths, and the `06a` frame shows the card.
- **Step 8's first pass did not reach the DAG.** The chat ask "ask the
  site-reporter sub agent to summarize …" was routed by the planner to the
  custom skill directly (a correct resolution — the skill covers the ask),
  so the tools failed inside the skill and the run completed with an honest
  answer, but the error edge lives in the sub agent's workflow and was not
  taken. The addendum invokes the sub agent directly, which is what the
  spec's "invoke again" means for a DAG. Also: the manager respawns a
  killed stdio server on its next use, so the visible `error` state was
  captured by pointing the server at a binary that does not exist, as the
  M36 ceremony recorded.
- **Step 11's todo list is the model's to write.** The one-line ask
  completed in agentic mode with the gate holding but Qwen emitted no
  todos; the addendum's multi-step ask produced three `plan` events. The
  middleware is wired either way (`TodoListMiddleware`); the events appear
  when the model uses it.
- **The retry outran the driver's wait.** The retried essay took about
  five minutes on the live model; the transcript's `timeout` is the
  driver's 240 s patience, and the run reads `completed`.
- **The first performance pass measured the ceremony's leftovers.** The
  ceremony had left `planner_model` on the live model, so the fake-provider
  chat sweep paid a live planner call per run (e2e p50 7 s at c=5). The
  record was re-taken on a clean configuration; the first pass is not the
  record.
- **The chat frames were re-taken with the conversation open.** The
  driver's first screenshots of the Chat page showed the conversation list
  only; `06a` (the HITL card, a fresh run paused at the gate and approved
  after the frame) and `06b` (the two-run conversation) were re-taken with
  the conversation selected. While re-taking them one planner call to the
  live model stalled for over five minutes with the provider reachable;
  it was cancelled through the API (`{'status': 'cancelled'}`) — the M51
  wall clock would have ended it at 900 s — and the next run paused at the
  gate in 21 s.
- **No `pkill` in the image.** `python:3.12-slim` ships no `procps`; the
  driver kills the stub by walking `/proc`. Not a product change.
