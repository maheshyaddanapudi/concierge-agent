## What and why

<!-- the spec section(s) this implements or fixes; one coherent change -->

## Evidence

- [ ] tests first: the new/changed tests are named here and were red before the change
- [ ] `cd backend && ruff check . && ruff format --check . && mypy app && python -m app.doclint && python -m app.prompts.check && pytest` green
- [ ] `cd frontend && npm run lint && npm run test -- --run && npm run build` green (if the frontend changed)
- [ ] live-model proof under `docs/acceptance/` for anything that touches a model, a stream or a deploy path

## Constraints checked

- [ ] no provider key, token or password outside the environment
- [ ] no broker, queue or fourth compose service
- [ ] every span/log/metric carries the spec §10 label set
- [ ] no file outside `backend/app/auth/` reads the auth switch
- [ ] docs updated (README milestone table, configuration reference, the page that describes the changed surface)
