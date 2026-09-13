#!/usr/bin/env bash
# start.sh — start the full stack (db + backend + frontend), idempotently.
#   • errors out if Docker is not running
#   • creates containers if they don't exist, restarts them if they do —
#     data lives in named volumes, so a stopped stack resumes where it left off
#   • pulls/builds any missing image (postgres is pulled; app images are built)
#   • database schema is created/migrated automatically at backend startup
#     (alembic upgrade head), including on the very first run
set -euo pipefail
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker (Desktop or dockerd) and retry." >&2
  exit 1
fi

[ -f .env ] || { echo "! no .env found — run ./quick-setup.sh first (continuing with defaults)"; }

existing="$(docker compose ps -aq 2>/dev/null | wc -l | tr -d ' ')"
if [ "$existing" -gt 0 ]; then
  echo "▸ found existing containers — starting them (data preserved in volumes)"
else
  echo "▸ no existing containers — creating the stack (first run: images are"
  echo "  pulled/built as needed and the DB schema is created automatically)"
fi

# `up -d` covers every case: pulls postgres if absent, builds app images if
# absent, creates missing containers, starts stopped ones, no-ops on running.
docker compose up -d

# Ask compose which host port it ACTUALLY published for the backend.
# BACKEND_PORT is not that port: since M54 the compose file publishes the
# backend from BACKEND_PORT_RANGE (default 8000-8010) so `--scale backend=N`
# can give each replica its own port. With the defaults and one replica the
# two happen to agree on 8000, but a custom range, an already-occupied 8000,
# or any scaled run moves it — and the health poll below then hammers a port
# nothing is listening on and reports a perfectly healthy stack as failed.
backend_host_port() {
  # `0.0.0.0:8000` (or `[::]:8000`) → `8000`; first line = first replica
  docker compose port backend 8000 2>/dev/null \
    | sed -n '1s/.*:\([0-9][0-9]*\)[[:space:]]*$/\1/p'
}

BACKEND_PORT="$(backend_host_port)"
if [ -z "$BACKEND_PORT" ]; then
  # compose could not tell us (very early, or an old compose) — fall back to
  # the first port of the declared range, then to BACKEND_PORT, then 8000
  range="$(grep -E '^BACKEND_PORT_RANGE=' .env 2>/dev/null | cut -d= -f2- || true)"
  BACKEND_PORT="${range%%-*}"
  if [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env 2>/dev/null | cut -d= -f2- || true)"
  fi
  BACKEND_PORT="${BACKEND_PORT:-8000}"
  echo "! could not read the published backend port from compose — probing ${BACKEND_PORT}"
fi

FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' .env 2>/dev/null | cut -d= -f2- || true)"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

printf '▸ waiting for the backend to come up (migrations + seed run at startup)'
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    echo
    echo "▸ stack is up:"
    echo "    frontend  http://localhost:${FRONTEND_PORT}"
    echo "    api       http://localhost:${BACKEND_PORT}/api/v1"
    echo "    health    http://localhost:${BACKEND_PORT}/health"
    exit 0
  fi
  printf '.'
  sleep 2
done
echo
echo "ERROR: backend did not become healthy on port ${BACKEND_PORT} within 120 s." >&2
echo "Last 50 lines of the backend log:" >&2
docker compose logs --tail=50 backend >&2 2>/dev/null || true
echo "Full log: docker compose logs backend" >&2
exit 1
