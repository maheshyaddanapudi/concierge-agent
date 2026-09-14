# Contributing

Thanks for looking. This project is developed **spec-first**: `spec.md` is
the binding specification, `CLAUDE.md` is the working agreement, and every
change ships with executed proof. The milestone line is finished (M1–M56,
`1.0.0`); work now arrives as **reviewer waves** — a review pass produces
findings, each finding is put to the operator as an explicit decision
before any code is written, and the accepted decisions land as the wave's
commit with a `CHANGELOG.md` entry. The full guide — the spec-driven
workflow, the wave loop, the hard constraints reviews enforce, what a
pull request must carry — is
[docs/development/contributing.md](./docs/development/contributing.md).

The short version:

1. **Read the spec section you are changing.** If it is ambiguous, open an
   issue and say so; do not invent behaviour. If you think the spec is wrong,
   propose the change first.
2. **Tests first, then code, then evidence.** Unit and integration suites
   run key-free on the fake provider (`FAKE_LLM_ENABLED=1`); anything that
   touches a live model needs a transcript or screenshot under
   `docs/acceptance/`.
3. **Gates before you push** — through `uv`, which is the project
   environment; the bare `pytest` / `mypy` / `python` on your `PATH` are
   not and will fail on import:
   `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run python -m app.doclint && uv run python -m app.prompts.check && uv run pytest`,
   and `cd frontend && npm run lint && npm run test && npm run build`.
   The backend suite needs a pgvector Postgres it can own — see
   [docs/development/local-development.md](./docs/development/local-development.md#backend).
4. **Conventional commits**, one per coherent change.
5. **Never** put a provider key, a session token or a password anywhere but
   the environment — the gitignored `.env`, never the database, the UI or a
   log. Never add a broker, a queue or a Celery; compose is `db`, `backend`,
   `frontend` and the profile-gated `redis` cache backend, and nothing else.

Adding your organisation's authentication is a fork, by design: see
[docs/extending.md](./docs/extending.md). A change to the core that only
your provider needs is a seam defect — open an issue rather than a patch.

Local setup, the two dev loops and the test database are in
[docs/development/local-development.md](./docs/development/local-development.md)
and [QUICK_START.md](./QUICK_START.md).
