# Quick Start

Everything below is driven by five idempotent scripts at the repo root — you should rarely need raw `docker compose` commands. Full operational detail lives in [docs/operations/runbook.md](./docs/operations/runbook.md).

## Prerequisites

- **Docker + Docker Compose** (the whole stack runs in containers)
- An **Anthropic API key** (other provider keys are optional — their presence in `.env` enables those providers in Settings)
- For local development only (not needed to just run the app): Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 20+

## 1. Set up

```bash
git clone <repo-url> && cd concierge-agent
./quick-setup.sh
```

What it does (safe to re-run any time):

- creates `.env` from `.env.example` if missing
- prompts for your `ANTHROPIC_API_KEY` (hidden input; offers to overwrite an existing value)
- asks whether to provision the **optional Redis cache backend** upfront (whether the app *uses* it stays a runtime Settings decision — the default cache mode never touches Redis)
- installs local dev dependencies (backend `uv sync`, frontend `npm install`)

Non-interactive flags:

```bash
./quick-setup.sh --key sk-ant-...        # set the API key without a prompt
./quick-setup.sh --redis                 # provision Redis without asking
./quick-setup.sh --no-redis              # skip Redis without asking
```

**No API key?** You can still run everything: set `FAKE_LLM_ENABLED=1` in `.env` and pick `fake:scripted` as the default model in Settings once the stack is up — runs, SSE streaming, HITL, and both orchestrator modes all work against the scriptable fake provider.

## 2. Build

```bash
./build.sh
```

Builds the backend and frontend Docker images. Re-run after pulling code changes.

## 3. Start

```bash
./start.sh
```

- errors out early if Docker isn't running
- creates or resumes the stack (`db`, `backend`, `frontend`); missing images are pulled/built
- **first run**: creates the database schema and loads seed data automatically (two MCP servers, native skills and tools, the `research-concierge` sub agent)
- **later runs**: resumes with all your data intact (named volumes)
- waits for backend health, then prints the URLs

Then open:

| What | Where |
|---|---|
| Admin UI | `http://localhost:${FRONTEND_PORT}` (default **5173**) |
| API | `http://localhost:${BACKEND_PORT}` (default **8000**) |
| Interactive API docs | `http://localhost:8000/docs` |

First things to try: send a prompt in **Chat**, watch the live run trace, then walk the ten-step acceptance script in [spec.md §14](./spec.md). A task-oriented tour of every page is in [docs/user-guide.md](./docs/user-guide.md).

## 4. Stop

```bash
./stop.sh
```

Stops the containers. **All data is preserved** — registries, runs, settings, checkpoints. `./start.sh` picks up exactly where you left off.

## 5. Decommission (destructive)

```bash
./decom.sh        # asks for confirmation
./decom.sh -y     # skips the confirmation
```

Dismantles everything: containers, network, **and the data volumes** — registries, run history, checkpoints, workspace files. The next `./start.sh` is a clean slate (fresh schema, seeds reloaded). Images are kept — rebuild with `./build.sh` only after code changes.

## Optional: Redis cache backend

The registry cache defaults to `bypass` (direct DB reads) and can be flipped live in Settings between `bypass`, `memory`, and `redis` — no restart. To make `redis` selectable:

1. provision it (`./quick-setup.sh --redis`, or set `REDIS_URL` in `.env` yourself)
2. start the profile: `docker compose --profile redis up -d`
3. flip **Settings → Registry cache → redis** (the save pings Redis and rejects if unreachable)

## Common issues

| Symptom | Fix |
|---|---|
| `./start.sh` says Docker isn't running | Start Docker Desktop / the docker daemon, re-run |
| Port already in use | Change `BACKEND_PORT` / `FRONTEND_PORT` in `.env`, re-run `./start.sh` |
| Runs fail with provider/credit errors | Check the key in `.env`; error text is shown verbatim on the run in the Runs page |
| Selecting redis cache mode is rejected | `REDIS_URL` unset or Redis not running — see the Redis section above |
| Something else | [docs/operations/troubleshooting.md](./docs/operations/troubleshooting.md) |

## Where to go next

- **Use the app**: [docs/user-guide.md](./docs/user-guide.md)
- **Operate it**: [docs/operations/runbook.md](./docs/operations/runbook.md) · [configuration reference](./docs/operations/configuration.md)
- **Understand it**: [docs/architecture/overview.md](./docs/architecture/overview.md)
- **Develop on it**: [docs/development/local-development.md](./docs/development/local-development.md) · [contributing](./docs/development/contributing.md)
- **Everything**: [docs/README.md](./docs/README.md)
