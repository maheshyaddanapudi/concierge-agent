#!/usr/bin/env bash
# Restore (M53, docs/operations/backup-restore.md) — the drill, scripted:
#
#   ./restore.sh backups/concierge-<stamp>.dump [backups/concierge-<stamp>.workspace.tar]
#   ./restore.sh --yes backups/concierge-<stamp>.dump      (no prompt; for automation)
#
# 0. VERIFY the archives and CONFIRM the target — this is the only script in
#    the set that destroys data it cannot get back (pg_restore --clean drops
#    every object in the live database before it loads the dump). Nothing
#    below runs until the dump is proven readable and the operator has said
#    yes (or passed --yes);
# 1. stop the backend (readiness first: SIGUSR1, then the container);
# 2. pg_restore --clean --if-exists into the running db (every application
#    table, every index — pgvector's included — is rebuilt from the dump;
#    the index build is inside the timed window, it IS part of the RTO);
# 3. restore the workspace tarball when given;
# 4. start the backend and wait for /ready 200 — migrations run to head,
#    the seed reconciles, the MCP manager and the cache warm up against the
#    restored registries. Bounded by READY_WAIT_S.
# Prints the elapsed time: that number is the measured RTO for this data set.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  cat <<'EOF'
usage: restore.sh [--yes] <dump> [workspace.tar]

  <dump>            a pg_dump custom-format archive (backup.sh writes -Fc)
  [workspace.tar]   optional tarball of the /workspace volume

  --yes, -y, --force   skip the interactive confirmation (automation).
                       Without a TTY and without this flag the script refuses
                       rather than destroying a database unattended.

  READY_WAIT_S=300 ./restore.sh ...   allow longer for /ready 200 after start
EOF
}

# plain scalars, no arrays: these scripts are expected to run on macOS's
# bash 3.2 too, where an empty array under `set -u` is a trap
ASSUME_YES=""
DUMP=""
WS=""
NPOS=0
END_OPTS=""
while [ $# -gt 0 ]; do
  if [ -z "$END_OPTS" ]; then
    case "$1" in
      -y|--yes|--force) ASSUME_YES=1; shift; continue ;;
      -h|--help)        usage; exit 0 ;;
      --)               END_OPTS=1; shift; continue ;;
      -*)               echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
  fi
  NPOS=$((NPOS + 1))
  case "$NPOS" in
    1) DUMP="$1" ;;
    2) WS="$1" ;;
    *) echo "too many arguments" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
[ -n "$DUMP" ] || { usage >&2; exit 2; }

USER_NAME="${POSTGRES_USER:-concierge}"
DB_NAME="${POSTGRES_DB:-concierge}"
# hard ceiling on the readiness wait after the restored stack is started.
# This used to be an unbounded `until` loop: a dump that restored into a
# schema the code could not migrate left the drill hanging with no output
# and no exit code, which is the worst possible state for a recovery script.
READY_WAIT_S="${READY_WAIT_S:-300}"

die() { echo "ERROR: $*" >&2; exit 1; }

# ── 0a. verify the archives BEFORE anything destructive ──────────────
echo "== verify archives =="

[ -e "$DUMP" ] || die "dump not found: $DUMP"
[ -f "$DUMP" ] || die "not a regular file: $DUMP"
[ -r "$DUMP" ] || die "dump is not readable: $DUMP"
[ -s "$DUMP" ] || die "dump is empty (0 bytes): $DUMP — a truncated backup.sh run leaves exactly this"

# pg_dump custom format (-Fc, what backup.sh writes) starts with the literal
# magic "PGDMP". A plain-SQL or gzipped file here would make pg_restore drop
# the schema and then fail to load anything back.
magic="$(head -c 5 "$DUMP" 2>/dev/null || true)"
[ "$magic" = "PGDMP" ] || die "$DUMP is not a pg_dump custom-format archive (magic '$magic', expected 'PGDMP'). backup.sh writes -Fc; a plain SQL dump must be replayed with psql, not this script."

docker compose ps -q db 2>/dev/null | grep -q . \
  || die "the 'db' service is not running — start it first (./start.sh or docker compose up -d db)"

# the real proof: the pg_restore that will do the work can read this archive's
# table of contents. Catches a corrupt or half-written dump whose header is
# intact, and a dump from a newer server version this pg_restore refuses.
entries="$(docker compose exec -T db pg_restore --list < "$DUMP" 2>/dev/null | grep -c ';' || true)"
[ "${entries:-0}" -gt 0 ] \
  || die "pg_restore could not read a table of contents from $DUMP — the archive is corrupt, truncated, or from an incompatible server version. Nothing has been changed."
echo "  dump       $DUMP ($(du -h "$DUMP" | cut -f1), $entries TOC entries, custom format)"

if [ -n "$WS" ]; then
  [ -f "$WS" ] || die "workspace tarball not found or not a regular file: $WS"
  [ -s "$WS" ] || die "workspace tarball is empty (0 bytes): $WS"
  tar -tf "$WS" >/dev/null 2>&1 || die "$WS is not a readable tar archive"
  echo "  workspace  $WS ($(du -h "$WS" | cut -f1))"
else
  echo "  workspace  (none given — /workspace is left untouched)"
fi

# ── 0b. confirm the target ───────────────────────────────────────────
if [ -z "$ASSUME_YES" ]; then
  [ -t 0 ] || die "refusing to restore unattended: no TTY to confirm on. Pass --yes if this is automation."
  ws_line="(workspace untouched — no tarball given)"
  [ -n "$WS" ] && ws_line="${WS}  → REPLACES all of /workspace"
  cat <<EOF

This OVERWRITES the live database '${DB_NAME}' (user '${USER_NAME}') on the
running compose service 'db', from:
    dump       ${DUMP}
    workspace  ${ws_line}

pg_restore --clean --if-exists DROPS every existing object first. Current
data — runs, conversations, registries, memories, settings — is GONE and
cannot be recovered unless you have another backup. This is the only
irreversible script in the set.
EOF
  printf "Type the database name (%s) to proceed, anything else to abort: " "$DB_NAME"
  read -r answer
  [ "$answer" = "$DB_NAME" ] || { echo "aborted — nothing was changed."; exit 0; }
fi

# ── the published host port, not the BACKEND_PORT variable ───────────
# The compose file publishes the backend from BACKEND_PORT_RANGE (M54), so
# BACKEND_PORT is not the port to probe — with a custom range or a scaled
# stack the readiness poll below would otherwise never see a healthy backend.
backend_host_port() {
  docker compose port backend 8000 2>/dev/null \
    | sed -n '1s/.*:\([0-9][0-9]*\)[[:space:]]*$/\1/p'
}

PORT=""
resolve_port() {
  local range
  PORT="$(backend_host_port)"
  if [ -z "$PORT" ]; then
    range="${BACKEND_PORT_RANGE:-8000-8010}"
    PORT="${range%%-*}"
    PORT="${PORT:-8000}"
    echo "! could not read the published backend port from compose — using ${PORT}"
  fi
}

# one clean status code. `curl -w '%{http_code}'` already prints 000 on a
# connection failure AND exits non-zero, so an `|| echo 000` fallback yields
# the string "000000" — harmless in a comparison, confusing in the timeout
# message this now prints.
ready_code() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${PORT}/ready" 2>/dev/null || true)"
  printf '%s' "${code:-000}"
}

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
resolve_port
waited=0
until [ "$(ready_code)" = "200" ]; do
  if [ "$waited" -ge "$READY_WAIT_S" ]; then
    echo "ERROR: the restored backend did not answer /ready 200 on port ${PORT} within ${READY_WAIT_S}s (last code: $(ready_code))." >&2
    echo "The database HAS been overwritten — do not re-run the restore blindly; read the log first." >&2
    echo "Last 100 lines of the backend log:" >&2
    docker compose logs --tail=100 backend >&2 2>/dev/null || true
    echo "Full log: docker compose logs backend" >&2
    exit 1
  fi
  sleep 1
  waited=$((waited + 1))
done
end=$(date +%s)
echo "== restored: RTO $((end - start)) s (stop → restore → ready on port ${PORT}) =="
