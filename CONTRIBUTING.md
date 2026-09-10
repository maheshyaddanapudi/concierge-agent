# Contributing

Thanks for looking. This project is developed **spec-first**: `spec.md` is
the binding specification, `CLAUDE.md` is the working agreement, and every
milestone ships with executed proof. The full guide — the spec-driven
workflow, the milestone loop, the hard constraints reviews enforce, what a
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
3. **Gates before you push**: `cd backend && ruff check . && ruff format --check . && mypy app && python -m app.doclint && python -m app.prompts.check && pytest`,
   and `cd frontend && npm run lint && npm run test -- --run && npm run build`.
4. **Conventional commits**, one per coherent change.
5. **Never** put a provider key, a session token or a password anywhere but
   the environment; never add a broker, a queue or a fourth compose service.

Adding your organisation's authentication is a fork, by design: see
[docs/extending.md](./docs/extending.md). A change to the core that only
your provider needs is a seam defect — open an issue rather than a patch.

Local setup, the two dev loops and the test database are in
[docs/development/local-development.md](./docs/development/local-development.md)
and [QUICK_START.md](./QUICK_START.md).
