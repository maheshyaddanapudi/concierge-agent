#!/usr/bin/env bash
# Readiness-first deploy on one host (M53, PLAN scale-H1).
#
#   ./deploy.sh                          rebuild backend + frontend images, then roll them
#   DRAIN_WAIT_S=20 ./deploy.sh          wait longer for /ready to report draining
#   DRAIN_SETTLE_S=10 ./deploy.sh        hold the 503 longer before the port closes (balancer probe cadence)
#   DEPLOY_SKIP_BUILD=1 ./deploy.sh      roll images built elsewhere (CI, a registry pull)
#   DEPLOY_FORCE_RECREATE=1 ./deploy.sh  roll to the SAME image (pick up .env changes, or drill)
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

PORT="${BACKEND_PORT:-8000}"
DRAIN_WAIT_S="${DRAIN_WAIT_S:-10}"
# once /ready reads 503, give a balancer's probe time to notice before the
# port closes (a probe every 5 s with 2 failures to eject needs ~10 s)
DRAIN_SETTLE_S="${DRAIN_SETTLE_S:-3}"
READY_URL="http://localhost:${PORT}/ready"

ready_code() { curl -s -o /dev/null -w '%{http_code}' "$READY_URL" 2>/dev/null || echo 000; }

RECREATE=()
[ -n "${DEPLOY_FORCE_RECREATE:-}" ] && RECREATE=(--force-recreate)

if [ -z "${DEPLOY_SKIP_BUILD:-}" ]; then
  echo "== build =="
  docker compose build backend frontend
fi

if docker compose ps -q backend 2>/dev/null | grep -q .; then
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
until [ "$(ready_code)" = "200" ]; do
  sleep 1
done
echo "backend ready (/ready 200)"
docker compose up -d --no-deps "${RECREATE[@]}" frontend
echo "== deployed =="
curl -s "$READY_URL"; echo
