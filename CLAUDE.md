# CLAUDE.md — Concierge Agent POC

## Source of truth
`spec.md` at repo root is the complete specification. Implement it as written. If the spec is ambiguous or two sections conflict, stop and ask — do not invent behavior. If you believe the spec is wrong, say so and propose the change before coding it.

Where a document and the code disagree, the code wins — **unless** the document describes intent the code failed to implement. That is a code finding to raise, not a document to quietly reword.

## Workflow — reviewer waves
The milestone line is finished: M1–M56 are complete and `1.0.0` is cut (`CHANGELOG.md`). Work no longer arrives as a milestone; it arrives as a **reviewer wave**:

1. **A review pass reads the system along one or more dimensions** — deployment posture, registry intent, orchestrator correctness, memory, providers, prompts, untrusted input, the formatter, observability, retention, the frontend, the build, the seed, the tests, the documentation — and produces findings. A finding names the file, the behavior, and the evidence.
2. **Every finding is put to the operator as an explicit decision before any code is written.** Fix / accept / defer / "that is the spec being wrong" is the operator's call, not yours. Do not start coding a finding you have not had answered. Findings that change described behavior need their spec section amended in the same wave.
3. **The accepted decisions become the wave's commit** — a single conventional commit for the wave's coherent body of work (`401914a feat: the code/setting/UI hardening wave — ~470 reviewer findings closed`), with a follow-up reading or a separated doc fix landing as its own commit (`3891914 docs: the acceptance script is eleven steps, not ten`). Evidence commits (`docs(acceptance): …`) stay separate from the change they prove. An Alembic migration lands in the same commit as its model change.
4. **`CHANGELOG.md` gets one section per wave**, titled by the wave, listing Migration notes / Fixed / Changed / Documentation honesty / Known limitations stated rather than fixed. A wave with no changelog entry did not happen.
5. **Verification means executed proof.** Show test output; show `curl` output for API changes; show screenshots for UI work. Never declare anything done without it. A number you have not measured this session does not go in a document — mark the gap instead.

Pause and ask ONLY when the spec is ambiguous or self-contradictory, or when a finding needs a decision that is the operator's to make. Otherwise resolve and continue.

## Hard constraints
- **Provider layer is non-negotiable basic design (spec §2.1)**: the `ModelProvider` port + registry in `backend/app/llm/` is used for every provider including Anthropic — never bypassed, never special-cased. All model access via `get_model("provider:model")`. No provider SDK or LangChain provider package imports outside `app/llm/`. Structured outputs via LangChain abstractions only; token usage via `usage_metadata`. Every adapter must pass the shared adapter contract test suite (`backend/tests/test_llm_contract.py`).
- **Middleware precedence (spec §7.0)**: out-of-box LangChain middleware first, configured via options; compose/subclass hooks second; custom middleware only when nothing OOB fits — the only sanctioned custom middlewares are the three registry projections. All stacks built through `build_middleware_stack(context)`; never attach registry middlewares other than scoped ToolsRegistry to a skill loop.
- **Switchability (spec §3.7.1)**: no behavior the system performs on its own may be unswitchable. Any job, sweep, judge or evaluator that runs without a human asking — on a timer, on idle, on a tick — has its own named gate in §3.7, **enforced inside the behavior, not only at its scheduler**, because these jobs are directly awaitable and a check that lives only in the caller is a check every other path walks past. A master switch over a family is not sufficient when the members have materially different consequences. A setting that reads as "off" must be off. `backend/tests/test_switchability.py` is the guard; the last wave had to push the master switch down into eleven ambient tick evaluators and the memory job family for exactly this reason.
- No message broker, task queue, or Celery — asyncio in one FastAPI process (spec §2). `docker-compose.yml` has **four** services: `db`, `backend`, `frontend`, and `redis` behind the `redis` profile. Redis is the optional registry-cache backend only (spec §7.3) — the default stack never starts it and nothing else may depend on it. Do not add a fifth service.
- Provider API keys: env only. Never in DB, never in UI, never logged. Keep them in the **gitignored `.env`** at the repo root (`.gitignore` lists `.env`), not only in a shell — a container that dies must not take the only copy of a key with it. `.env.example` is the committed template and carries no secrets.
- All LLM prompts live in `backend/app/prompts/` as files, loaded through `load_prompt()`. No inline prompt strings. Every prompt has a golden set in `backend/app/prompts/golden/`; `python -m app.prompts.check` gates the Docker build.
- Registry `id`s immutable. Static records: definition writes rejected; only `status`/`direct_exposure` togglable (spec §4).
- Every span/log/metric carries the label set from spec §10.

## Acceptance evidence
`docs/acceptance/` is the campaign tree: one directory per stage, each with its screenshots and a `transcript.md`, all captured click-driven against a live model (`openrouter:qwen/qwen3.8-max`) by the drivers in `experiments/acceptance/`. It is evidence, so it goes stale when the behavior it photographed changes.

**A change to a prompt file (`backend/app/prompts/`) or to the recall path (`app/memory/rank.py`, `app/memory/inject.py`, `app/retrieval.py`) obliges a re-run of the stages that photographed it** — at minimum the trial stages (`06`–`09`), `10-fallback-uncovered-ask`, `24-formatter` and `25-memory`. Re-run and republish per "How to re-run" in `docs/acceptance/README.md`. If the re-run is deferred, the deferral goes **on the page, not only in a commit message**: name the stages now stale where a reader of the evidence will see it.

**The tree is stale right now.** `401914a`'s commit body records it — "the live acceptance re-run … did not happen … the published evidence under `docs/acceptance/` therefore still reflects the PREVIOUS build and predates this wave's prompt and recall changes" — and that honesty lived only in a commit message until this rule existed. Re-running and republishing remains open work.

## Conventions (spec §13)
- Python 3.12: ruff (lint **and** format; rule sets `E F I UP B SIM ASYNC BLE S` — blind excepts and bandit checks are on, every surviving `noqa: BLE001` carries a one-line justification, and `app/` has no runtime `assert`), mypy strict on `app/`, pytest, async SQLAlchemy, Pydantic v2 schemas separate from ORM models, Alembic migration per schema change.
- TypeScript: eslint + prettier, strict tsconfig, TanStack Query, no Redux.
- Conventional commits.

## Testing models
- Unit/integration suites run on the fake provider (`FAKE_LLM_ENABLED=1`) — deterministic, key-free (spec §11). `backend/tests/conftest.py` clears `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` and `OPENAI_API_KEY`, but **not** `OPENROUTER_API_KEY` or `CUSTOM_GATEWAY_*` — unset those in your shell before running the suite or the contract suite fails on a provider it thinks is configured.
- Live acceptance / wave proofs ALWAYS use a real LLM; prefer `openrouter:qwen/qwen3.8-max` as `default_model` (all roles) unless a stage specifically tests another provider.

## Commands
Run backend commands through `uv` — the bare `pytest` / `mypy` / `python -m app.…` on `PATH` are not the project environment and fail on import.

- Backend tests: `cd backend && uv run pytest` — needs a pgvector Postgres it can own (`TEST_DATABASE_URL`, default `…@localhost:5433/concierge_test`); see `docs/development/local-development.md`.
- Backend gates: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run python -m app.doclint && uv run python -m app.prompts.check`
- Seed documents (`.skill.md` / `.agent.md`) only: `cd backend && uv run python -m app.doclint` — same checks the seed applies, offline; also a Docker build gate, so a malformed document fails the build instead of surfacing at boot. `uv run python -m app.prompts.check` is the same arrangement for prompts.
- Frontend: `cd frontend && npm run lint && npm run test && npm run build`
- Full stack: `./start.sh` (or `docker compose up`)

## Definition of done
There is no milestone count left to complete, so the bar is standing rather than terminal. At any commit that claims to be done:

- backend and frontend suites green (`uv run pytest`; `npm run test`);
- lint, format and types clean (`ruff check`, `ruff format --check`, `mypy app`, `eslint`, `tsc`);
- the doc gates green (`app.doclint`, `app.prompts.check`);
- the eleven-step Acceptance Demo Script (spec §14) passes top to bottom on a fresh `docker compose up`;
- the `docs/acceptance/` tree re-run for any stage whose behavior a prompt or recall change moved, per **Acceptance evidence** above;
- a `CHANGELOG.md` entry for the wave.
