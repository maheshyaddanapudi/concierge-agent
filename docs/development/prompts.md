# Prompt Catalog

**The governing rule (CLAUDE.md / spec §13): every LLM prompt lives as a file in `backend/app/prompts/` — no inline prompt strings anywhere in the codebase.** Prompts are versioned like code, provider-neutral by construction (spec §2.1 neutrality rules), and loaded through one function:

```python
from app.prompts import load_prompt
text = load_prompt("planner")   # reads backend/app/prompts/planner.md, cached, stripped
```

`load_prompt` (`backend/app/prompts/__init__.py`) is `@cache`d — a prompt edit takes effect on the next process (re)start, which the uvicorn `--reload` dev loop handles automatically.

## Golden sets — the regression harness (M49)

Every prompt file has a **golden set** beside it in `backend/app/prompts/golden/<stem>.yaml`, and `python -m app.prompts.check` (`backend/app/prompts/check.py`) renders each prompt exactly the way its consumer does — `format` (`str.format(**vars)`), `replace` (chained `str.replace("{name}", …)`), or `verbatim` — then grades the rendered text with the spec §15 `contains` grader. A golden set names its consumer module (the harness verifies that module really calls `load_prompt("<stem>")`), the placeholders a `replace` consumer substitutes, and one or more cases: the vars to render with, the sentences that must survive (`must_contain`), and optionally the ones that must not (`must_not_contain`, e.g. an escaped `{{}}` that must render as `{}`).

What it catches, before a request does: a binding sentence edited out of a prompt (the planner's `no_confident_match` contract, an untrusted-data fence, the ambient abstain protocol); a placeholder renamed in the file while the consumer still passes the old name (`.format` would `KeyError`; `.replace` would silently leave the token in the prompt); a prompt file that no code loads any more. It runs three ways, like doclint: `pytest tests/test_prompt_golden.py`, by hand, and as a Docker build gate (`RUN python -m app.prompts.check` in `backend/Dockerfile`). The golden directory is the authoritative per-prompt index — the catalog below describes the orchestration prompts in prose; the memory, ambient, A2A, eval and salience prompts are documented by their golden sets.

## Catalog

| File | Loaded by | When it runs | Template slots |
|---|---|---|---|
| `planner.md` | `backend/app/orchestrator/planner.py:145` | Graph-mode plan step, at the start of every graph-mode run | `{task}`, `{history}`, `{sub_agent_cards}`, `{direct_capabilities}`, `{max_plan_steps}` |
| `concierge.md` | `backend/app/orchestrator/agentic_mode.py:92` | System prompt of the agentic-mode `create_agent` concierge — active for the whole agentic run | none (static) |
| `aggregator.md` | `backend/app/orchestrator/graph_mode.py:330` | Graph-mode aggregate step, after all dispatches finish — produces the streamed final answer | `{task}`, `{outputs}` |
| `direct_tool.md` | `backend/app/orchestrator/ladder.py:306` | Rung-1 direct-tool execution: a plan entry resolved to an exposed tool | `{task}` |
| `router.md` | `backend/app/factory/worker.py:488` | Inside a running worker, whenever a workflow node with multiple conditional edges finishes — picks the edge | `{output}`, `{conditions}` |
| `tool_guidance.md` | `backend/app/factory/worker.py:279` (`assemble_skill_prompt`) | Appended verbatim as the final section of **every** skill-node system prompt (workers, rung-1 inline loops, ephemeral workers, fallback skill runs) | none (appended, not formatted) |
| `formatter.md` | `backend/app/orchestrator/answer_ui.py` | After the final answer text, before the `done` SSE event, when `formatter_enabled` — the formatter role's transformation contract producing the declarative answer UI (M8/M24; it replaced the earlier `answer_ui.md`, removed in M49 once the golden harness showed it had no consumer) | `{task}`, `{answer}`, `{chart_rules}`, `{existing_charts}` (filled with `.replace()` — the body is brace-heavy) |
| `overlap_judge.md` | `backend/app/overlap.py:120` (`_judge`) | On `POST /skills/check-overlap` and `POST /sub-agents/check-overlap`, i.e. before the UI saves a skill/sub agent draft | `{draft_type}`, `{draft}`, `{candidates}` |
| `summarize_and_structure.md` | `backend/app/native/tools.py:48` | Inside the `summarize-and-structure` native subgraph tool, whenever a skill loop calls it | `{text}` |

## Per-prompt notes

- **`planner.md`** — decomposes the user request into a validated plan over sub agent cards and directly usable capabilities, or returns `direct_answer` / `no_confident_match`. Filled with `str.format`, so literal JSON braces inside the file are escaped as `{{...}}`. The `{direct_capabilities}` section additionally carries retrieval footers ("showing N of M…") when the §7.4 ranker truncated the catalog.
- **`concierge.md`** — the agentic orchestrator's operating manual: todo discipline, when to answer directly, how to use `use_skill_*` / `dispatch_*` tools, and the two fallbacks (`spin_worker(skill_ids, task)`, `use_full_catalog()`). No slots — capabilities arrive via the registry middlewares, not the prompt.
- **`aggregator.md`** — merges dispatched step outputs into one user-facing answer without exposing plan mechanics; failures are stated plainly.
- **`direct_tool.md`** — constrains a rung-1 direct tool step to exactly one tool call derived from the plan entry's task.
- **`router.md`** — natural-language condition routing: node output + numbered condition list in, structured `ConditionChoice` index out (clamped defensively in `worker.py`).
- **`tool_guidance.md`** — the fixed closing section of the spec §6 prompt assembly order (sub agent persona → skill persona → skill instructions → node addendum → this). Explains that `{tool:server.tool}` mentions map to underscore-normalized tool names. The `{tool:...}` text inside it is prose, not a template variable — the file is appended, never `.format()`ed.
- **`formatter.md`** — the formatter role's binding contract (preserve everything, invent nothing, prose stays prose, warnings sacred, self-check) plus the component vocabulary (`card`, `text`, `stat`, `table`, `list`, `badge`, `divider`, `link`, `sources`, and `chart` when `answer_ui_charts_enabled`). `{chart_rules}` and `{existing_charts}` are filled at call time; `{task}`/`{answer}` with `.replace()` because the body contains literal braces. Output is schema-validated and translated deterministically to A2UI — generation failure is dropped silently (the text answer stays the source of truth).
- **`overlap_judge.md`** — the LLM-as-judge rubric (90–100 near-duplicate … 0–39 distinct) for the advisory pre-save overlap check; returns a structured `OverlapVerdict`. Filled with `.replace()`; the guard fails open if the judge is unreachable.
- **`summarize_and_structure.md`** — the single LLM call of the seeded native subgraph tool: raw text → strict JSON (`title`, `summary`, `key_points[]`, `entities[]`), with format requirements tightened for repair-retry (`backend/tests/test_native_provider.py::TestSummarizeRepairRetry`).

## Adding a prompt

1. Create `backend/app/prompts/<name>.md`. Keep it provider-neutral — no vendor-specific phrasing, no reliance on a particular model's formatting quirks (spec §2.1).
2. Load it with `load_prompt("<name>")` at the call site; fill slots with `str.format` (escape literal braces as `{{}}`) or chained `.replace()` when the body is brace-heavy — both patterns exist in the codebase.
3. Run the model through `get_model(...)`; use LangChain structured output when you need typed results — never hand-rolled JSON parsing of a raw completion.
4. Do not build prompt strings inline "just this once" — reviews reject it (see [contributing.md](./contributing.md)); even two-line prompts like `direct_tool.md` are files.
