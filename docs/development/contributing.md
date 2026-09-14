# Contributing

This repo is developed **spec-first**. `spec.md` at the repo root is the complete, binding specification; `CLAUDE.md` encodes the workflow rules that every change — human or agent — must follow. Read both before touching code.

## The spec-driven workflow

1. **`spec.md` is the single source of truth.** Implement it as written. If the spec is ambiguous or two sections conflict, stop and ask — do not invent behavior. If you believe the spec is wrong, say so and propose a spec change *before* coding it (spec changes land as their own `docs(spec):` commits, e.g. `38f9fd6 docs(spec): registry cache layer (§7.3) and progressive-disclosure retrieval (§7.4)`).
2. **The milestone line is finished** (spec §12). The POC core was M1 (registries + seed) → M2 (MCP manager) → M3 (worker factory) → M4 (orchestrator + SSE + observability) → M5 (admin UI) → M6 (test/compose polish); the project then ran to **M56**, through invocation and cache (M7, M9–M12), memory (M13–M18), ambient (M19–M30), completeness and hardening (M31–M35), the acceptance ceremony (M36), A2A (M37–M39), config and salience (M40–M43), forgetting and learners (M44–M47), switchability (M48) and the production-hardening plan (M49–M56, `docs/research/prod_hardening/PLAN.md`). `1.0.0` is cut. The per-milestone table is in [README.md](../../README.md#milestone-status) as history — nothing is appended to it any more.
3. **New work arrives as a reviewer wave.** A review pass reads the system along one or more dimensions — deployment posture, registry intent, orchestrator correctness, memory, providers, prompts, untrusted input, the formatter, observability, retention, the frontend, the build, the seed, the tests, the documentation — and produces findings. **Every finding is put to the operator as an explicit decision before any code is written**; fix / accept / defer / "the spec is wrong here" is the operator's call. Accepted decisions become the wave's commit (`401914a feat: the code/setting/UI hardening wave — ~470 reviewer findings closed`), a follow-up reading or a separated doc fix lands as its own commit (`3891914 docs: the acceptance script is eleven steps, not ten`), and the wave gets one `CHANGELOG.md` section — Migration notes / Fixed / Changed / Documentation honesty / Known limitations stated rather than fixed. A finding that changes described behaviour needs its spec section amended in the same wave.
4. **Verification means executed proof.** Show test output; show `curl` output for API changes; show screenshots for UI work. Never declare something done without it — and never write a count or a claim you have not measured against a primary source this session. Mark the gap instead.
5. **Where a document and the code disagree, the code wins** — unless the document describes intent the code failed to implement. That is a code finding to raise, not a document to quietly reword.

## Commits

Conventional commits, enforced by convention and review. Real examples from `git log`:

```
feat(cache): LISTEN/NOTIFY cross-replica invalidation + optional Redis provisioning in quick-setup
feat(m8): markdown answers + summary toggle, HITL form gates, charts, per-skill loop budgets
feat(llm): current Gemini flash models in the google_genai adapter list
fix(llm): route OpenAI reasoning-effort runs through the Responses API
fix(ui): never leave a HITL card armed after its gate was consumed
fix(scripts): bash 3.2 portability for macOS
docs(acceptance): stage 21 — M8 features on the Claude × Gemini combo
docs(spec): registry cache layer (§7.3) and progressive-disclosure retrieval (§7.4)
docs(readme): M7 milestone — registry cache + retrieval
```

Rules of thumb:

- `type(scope): summary` — types in use across the history: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `build`, plus the project's two locals, `experiment` and `spec`. Scopes in use include `llm`, `cache`, `ui`, `chat`, `orchestrator`, `memory`, `ambient`, `a2a`, `mcp`, `native`, `retrieval`, `scripts`, `docker`, `spec`, `acceptance`, `readme`, `release`, and milestone tags like `m8`, `m53`.
- One coherent change per commit. Evidence commits (`docs(acceptance): …` — 121 of them) are separate from the feature commits they prove.
- An Alembic migration accompanies every schema change, in the same commit as the model change (see `backend/alembic/versions/`).

## Branches

- **`dev` is the integration branch.** A wave or experiment gets its own descriptive branch — `prod_hardening`, `code_setting_ui_hardening`, `config_hardening`, `m48_switchboard`, `acceptance_v1` — and lands on `dev` via pull request (`28732b4 Merge pull request #25 from maheshyaddanapudi/prod_hardening`).
- **`main` is the release branch**, fed from `dev` by pull request (`fa313a4 Merge pull request #22 from maheshyaddanapudi/dev`).
- Do not commit directly to `main` or `dev`.

## Hard constraints that reviews enforce

These are the non-negotiables from `CLAUDE.md` / spec. A PR that violates any of them gets rejected regardless of how well it works:

1. **Provider layer is never bypassed** (spec §2.1). All model access goes through `get_model("provider:model")` in `backend/app/llm/registry.py` — for *every* provider, including Anthropic. No provider SDK or LangChain provider-package import outside `backend/app/llm/`. Structured outputs via LangChain abstractions only; token accounting via `usage_metadata` only. Every adapter must pass the shared contract suite (`backend/tests/test_llm_contract.py`).
2. **Middleware precedence** (spec §7.0). Out-of-box LangChain middleware first, configured via options; compose/subclass hooks second; custom middleware only when nothing OOB fits. The only sanctioned custom middlewares are the three registry projections in `backend/app/orchestrator/middleware.py`. All stacks are built through `build_middleware_stack(context)`; a skill loop gets scoped `ToolsRegistry` only — never the Skills or SubAgents registry middlewares.
3. **No broker, no queue, no Celery.** Runs are asyncio tasks in the single FastAPI process (`backend/app/orchestrator/runner.py`); SSE is plain HTTP; HITL rides the LangGraph Postgres checkpointer. Redis exists solely as the optional registry-cache backend behind the compose `redis` profile — nothing else may depend on it.
4. **Prompts are files.** Every LLM prompt lives in `backend/app/prompts/*.md` and loads via `load_prompt()`. No inline prompt strings, anywhere. See [prompts.md](./prompts.md).
5. **Env-only keys.** Provider and LangSmith API keys live in environment variables only — never in the database, never in the UI, never logged (`backend/app/config.py`).
6. **Registry `id`s are immutable; static records are protected.** `source='static'` records reject definition writes with 403; only `status` and `direct_exposure` are togglable (spec §4, enforced in `backend/app/api/deps.py` and covered by `backend/tests/test_registry_api.py`).
7. **Every span/log/metric carries the spec §10 label set** (`run_id, step_id, tier, kind, source, entity_id, entity_name, model, effort, input_tokens, output_tokens, duration_ms, status` — see `backend/app/obs.py`).
8. **Every registry write path invalidates the cache before returning** (spec §7.3). If you add a write path, call `get_cache().invalidate(<registry>)` — see [testing.md](./testing.md#adding-a-new-registry-write-path).
9. **Nothing the system does on its own is unswitchable** (spec §3.7.1). Any job, sweep, judge or evaluator that runs without a human asking — on a timer, on idle, on a tick — carries its own named §3.7 gate, **enforced inside the behaviour, not only at its scheduler**: these jobs are directly awaitable, so a check that lives only in the caller is a check every other path walks past. A master switch over a family is not enough when the members have materially different consequences, and a setting that reads as "off" must be off. `backend/tests/test_switchability.py` is the guard; the last wave had to push the master switch down into eleven ambient tick evaluators and the memory job family for exactly this reason.

## Definition of done

There is no milestone count left to complete, so the bar is standing rather than terminal. On a fresh checkout:

```bash
cd backend && uv run pytest                                     # backend suite green (needs the pgvector test Postgres, see local-development.md)
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
cd backend && uv run python -m app.doclint && uv run python -m app.prompts.check
cd frontend && npm run lint && npm run test && npm run build
docker compose up                                               # then: spec §14 acceptance script passes top to bottom
```

Run backend commands through `uv`: the bare `pytest` / `mypy` / `python -m app.…` on your `PATH` are not the project environment and fail on import.

The eleven-step Acceptance Demo Script (spec §14) on a fresh `docker compose up` is the final gate — not a formality. The full manual run that proved it lives in `docs/acceptance/`.

**The acceptance tree is evidence, so it goes stale.** A change to a prompt file (`backend/app/prompts/`) or to the recall path (`app/memory/rank.py`, `app/memory/inject.py`, `app/retrieval.py`) obliges a re-run of the stages that photographed that behaviour — at minimum the trial stages (`06`–`09`), `10-fallback-uncovered-ask`, `24-formatter` and `25-memory`. Re-run and republish per "How to re-run" in [docs/acceptance/README.md](../acceptance/README.md); if you defer, say so in the commit message and name the stages now stale.

## PR expectations

Attach **executed proof**, matched to what the change touches:

- **Any backend change**: the relevant `uv run pytest` output (at minimum the affected module, ideally the full suite) plus `uv run ruff check . && uv run ruff format --check . && uv run mypy app`.
- **API-facing change**: `curl` transcripts of the new/changed endpoints — this is the CLAUDE.md standard for API work.
- **UI-facing change**: screenshots following the `docs/acceptance/` practice — numbered stage folders (`docs/acceptance/21-m8-features/`, `docs/acceptance/22-hitl-stale-card-fix/`, …) containing before/after or walk-through screenshots, indexed in `docs/acceptance/README.md` with the spec sections each stage proves. Evidence lands as its own `docs(acceptance):` commit (see `becb1db`, `f686735`'s companion stage `22-hitl-stale-card-fix`).
- **Provider/adapter change**: contract-suite output (`uv run pytest tests/test_llm_contract.py`), and where a real key is available, a note of the live smoke result.
- **Anything touching orchestration**: confirm the orchestrator suite passes in **both** cache modes (it is parametrized over `bypass` and `memory` automatically — just run `uv run pytest tests/test_orchestrator.py` and say so).
- **Prompt or recall change**: name the `docs/acceptance/` stages you re-ran, or the ones you are leaving stale and why.

If the change alters behavior described in spec §14, state which acceptance steps you re-ran.
