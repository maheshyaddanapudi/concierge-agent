#!/usr/bin/env bash
# Restore (M53, docs/operations/backup-restore.md) — the drill, scripted:
#
#   ./restore.sh backups/concierge-<stamp>.dump [backups/concierge-<stamp>.workspace.tar]
#
# 1. stop the backend (readiness first: SIGUSR1, then the container);
# 2. pg_restore --clean --if-exists into the running db (every application
#    table, every index — pgvector's included — is rebuilt from the dump;
#    the index build is inside the timed window, it IS part of the RTO);
# 3. restore the workspace tarball when given;
# 4. start the backend and wait for /ready 200 — migrations run to head,
#    the seed reconciles, the MCP manager and the cache warm up against the
#    restored registries.
# Prints the elapsed time: that number is the measured RTO for this data set.
set -euo pipefail
cd "$(dirname "$0")"

DUMP="${1:?usage: restore.sh <dump> [workspace.tar]}"
WS="${2:-}"
PORT="${BACKEND_PORT:-8000}"
USER_NAME="${POSTGRES_USER:-concierge}"
DB_NAME="${POSTGRES_DB:-concierge}"

ready_code() { curl -s -o /dev/null -w '%{http_code}' "http://localhost:${PORT}/ready" 2>/dev/null || echo 000; }

start=$(date +%s)
echo "== stop backend (readiness first) =="
docker compose kill -s USR1 backend 2>/dev/null || true
sleep 2
docker compose stop backend

echo "== restore database =="
t0=$(date +%s)
docker compose exec -T db pg_restore -U "$USER_NAME" -d "$DB_NAME" --clean --if-exists --no-owner < "$DUMP"
t1=$(date +%s)
echo "pg_restore took $((t1 - t0)) s (schema, data and every index, pgvector included)"

if [ -n "$WS" ] && [ -s "$WS" ]; then
  echo "== restore workspace =="
  docker compose run --rm --no-deps -T --entrypoint sh backend -c 'rm -rf /workspace/* && tar -C /workspace -xf -' < "$WS"
fi

echo "== start backend =="
docker compose up -d --no-deps backend
until [ "$(ready_code)" = "200" ]; do
  sleep 1
done
end=$(date +%s)
echo "== restored: RTO $((end - start)) s (stop → restore → ready) =="
