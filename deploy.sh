#!/usr/bin/env bash
# Readiness-first deploy on one host (M53, PLAN scale-H1).
#
#   ./deploy.sh                          rebuild backend + frontend images, then roll them
#   DRAIN_WAIT_S=20 ./deploy.sh          wait longer for /ready to report draining
#   DRAIN_SETTLE_S=10 ./deploy.sh        hold the 503 longer before the port closes (balancer probe cadence)
#   DEPLOY_SKIP_BUILD=1 ./deploy.sh      roll images built elsewhere (CI, a registry pull)
#   DEPLOY_FORCE_RECREATE=1 ./deploy.sh  roll to the SAME image (pick up .env changes, or drill)
#   READY_WAIT_S=300 ./deploy.sh         allow longer for the new container to answer /ready 200
#
# Sequence for the backend:
#   1. build the new images (the old container keeps serving meanwhile);
#   2. SIGUSR1 → the running backend flips GET /ready to 503 while its port
#      is still open, refuses new runs (503 + Retry-After), and politely
#      closes the streams it cannot serve — a balancer probing /ready stops
#      routing here BEFORE the port closes;
#   3. wait until /ready reports draining (bounded by DRAIN_WAIT_S);
#   4. `docker compose up -d` recreates the container: SIGTERM → uvicorn's
#      5 s connection grace → the lifespan drain (SHUTDOWN_GRACE_S) lets
#      in-flight runs finish, cancels the rest with the shutdown named →
#      the new container boots, migrates, seeds, reaps anything the old one
#      left non-terminal, and answers /ready 200;
#   5. clients that held a stream reconnect with Last-Event-ID and resolve
#      from the run record — no duplicated answer text (docs/api/sse-events.md).
set -euo pipefail
cd "$(dirname "$0")"

DRAIN_WAIT_S="${DRAIN_WAIT_S:-10}"
# once /ready reads 503, give a balancer's probe time to notice before the
# port closes (a probe every 5 s with 2 failures to eject needs ~10 s)
DRAIN_SETTLE_S="${DRAIN_SETTLE_S:-3}"
# hard ceiling on the post-roll readiness wait: migrations, the seed pass and
# the MCP/cache warm-up all happen before /ready answers 200, so this is
# generous — but it is a CEILING. An unbounded `until` loop turned a container
# that crash-looped on a bad migration into a deploy that never returned.
READY_WAIT_S="${READY_WAIT_S:-180}"

# The compose file publishes the backend from BACKEND_PORT_RANGE (M54), so
# BACKEND_PORT is NOT the host port to probe — ask compose what it bound.
# Re-read it after every `up -d`: recreating the container can move it within
# the range.
backend_host_port() {
  docker compose port backend 8000 2>/dev/null \
    | sed -n '1s/.*:\([0-9][0-9]*\)[[:space:]]*$/\1/p'
}

PORT=""
READY_URL=""
resolve_port() {
  local range
  PORT="$(backend_host_port)"
  if [ -z "$PORT" ]; then
    range="${BACKEND_PORT_RANGE:-8000-8010}"
    PORT="${range%%-*}"
    PORT="${PORT:-8000}"
    echo "! could not read the published backend port from compose — using ${PORT}"
  fi
  READY_URL="http://localhost:${PORT}/ready"
}

# one clean status code. `curl -w '%{http_code}'` already prints 000 on a
# connection failure AND exits non-zero, so an `|| echo 000` fallback yields
# the string "000000" — harmless in a comparison, confusing in the timeout
# message this now prints.
ready_code() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$READY_URL" 2>/dev/null || true)"
  printf '%s' "${code:-000}"
}

fail_with_logs() { # $1 = message
  echo "ERROR: $1" >&2
  echo "Last 100 lines of the backend log:" >&2
  docker compose logs --tail=100 backend >&2 2>/dev/null || true
  echo "Full log: docker compose logs backend" >&2
  exit 1
}

RECREATE=()
[ -n "${DEPLOY_FORCE_RECREATE:-}" ] && RECREATE=(--force-recreate)

if [ -z "${DEPLOY_SKIP_BUILD:-}" ]; then
  echo "== build =="
  docker compose build backend frontend
fi

if docker compose ps -q backend 2>/dev/null | grep -q .; then
  resolve_port
  echo "== drain (SIGUSR1: readiness first) =="
  docker compose kill -s USR1 backend
  for _ in $(seq 1 "$DRAIN_WAIT_S"); do
    code="$(ready_code)"
    if [ "$code" = "503" ]; then
      echo "backend reports draining (/ready 503); settling ${DRAIN_SETTLE_S}s for the balancer"
      sleep "$DRAIN_SETTLE_S"
      break
    fi
    sleep 1
  done
fi

echo "== roll =="
docker compose up -d --no-deps "${RECREATE[@]}" backend
# the container was just (re)created — re-resolve, the published port can move
resolve_port
waited=0
until [ "$(ready_code)" = "200" ]; do
  if [ "$waited" -ge "$READY_WAIT_S" ]; then
    fail_with_logs "backend did not answer /ready 200 on port ${PORT} within ${READY_WAIT_S}s (last code: $(ready_code)). The old container is gone; the stack is NOT serving."
  fi
  sleep 1
  waited=$((waited + 1))
done
echo "backend ready (/ready 200 on port ${PORT} after ${waited}s)"
docker compose up -d --no-deps "${RECREATE[@]}" frontend
echo "== deployed =="
curl -s "$READY_URL"; echo
