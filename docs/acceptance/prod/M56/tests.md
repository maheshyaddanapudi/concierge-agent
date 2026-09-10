# v1.0.0 — the suites and gates, executed on the release tree

## Backend (`cd backend && pytest`, fake provider)

```
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1068 passed, 1 skipped, 1 warning in 347.34s (0:05:47)
```

## Frontend (`npm run lint && npm run test -- --run && npm run build`)

```
✖ 15 problems (0 errors, 15 warnings)
lint exit 0
 Test Files  11 passed (11)
      Tests  94 passed (94)
test exit 0
✓ built in 4.99s
build exit 0
```

## Static gates

```
$ ruff check . && ruff format --check .
All checks passed!
$ mypy app
Success: no issues found in 148 source files
$ python -m app.doclint
doclint: 5 skill file(s), 1 agent file(s) — 0 error(s), 0 warning(s)
$ python -m app.prompts.check
prompt golden sets: 24 prompts, 24 cases, 0 failed
```

## Release images

```
proxy access to PyPI, then rebuild."; exit 1; }
undici || exit 1;     done
rt.html || exit 1;     done
build-backend-10.log:backend build exit 0
build-frontend-4.log:frontend build exit 0
concierge-agent-frontend:latest 77.1MB
concierge-agent-backend:latest 1.76GB
```
