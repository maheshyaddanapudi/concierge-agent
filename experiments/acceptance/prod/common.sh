#!/usr/bin/env bash
# Shared helpers for the production-hardening drills (source this file).
# Everything is environment-parametrised — nothing here knows about any one
# machine, and no provider key ever passes through these scripts (the
# backend reads its keys from its own environment).
#
#   ACC_API               backend API root (default: discovered from the
#                         concierge-agent-backend container's published port)
#   ACC_BASE              frontend URL for screenshots (default http://localhost:5174)
#   ACC_MODEL             live model for the drills (default openrouter:qwen/qwen3.8-max)
#   ACC_SHOTS             screenshot output dir (default ./shots/<drill>)
#   ACC_BACKEND_CONTAINER backend container name (default concierge-agent-backend-1)
#   ACC_DB_CONTAINER      db container name (default concierge-agent-db-1)
#   ACC_DB_USER / ACC_DB_NAME   psql identity inside the db container (default concierge/concierge)
#   ACC_DATABASE_URL      psql URL for the load harness (default postgresql://concierge:concierge@localhost:5555/concierge)
#   ACC_CHROMIUM          browser binary for shot.mjs (default: Playwright's own)
set -u
ACC_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACC_ROOT="$(cd "$ACC_HERE/../../.." && pwd)"
ACC_BASE=${ACC_BASE:-http://localhost:5174}
ACC_MODEL=${ACC_MODEL:-openrouter:qwen/qwen3.8-max}
ACC_BACKEND_CONTAINER=${ACC_BACKEND_CONTAINER:-concierge-agent-backend-1}
ACC_DB_CONTAINER=${ACC_DB_CONTAINER:-concierge-agent-db-1}
ACC_DB_USER=${ACC_DB_USER:-concierge}
ACC_DB_NAME=${ACC_DB_NAME:-concierge}
ACC_DATABASE_URL=${ACC_DATABASE_URL:-postgresql://concierge:concierge@localhost:5555/concierge}
H='content-type: application/json'

say() { printf '\n$ %s\n' "$*"; }
py() { python3 -c "import sys,json; d=json.load(sys.stdin); $1"; }
psql_() { docker exec "$ACC_DB_CONTAINER" psql -U "$ACC_DB_USER" -d "$ACC_DB_NAME" -Atc "$1"; }
bport() { docker ps --filter "name=concierge-agent-backend" --format '{{.Ports}}' | head -1 | sed 's/.*:\([0-9]*\)->8000.*/\1/'; }
api_root() { if [ -n "${ACC_API:-}" ]; then echo "$ACC_API"; else echo "http://localhost:$(bport)/api/v1"; fi; }
wait_ready() {
  local root; root=$(api_root); root=${root%/api/v1}
  for i in $(seq 1 180); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$root/ready")" = "200" ] && { echo "backend /ready 200 after ${i}s at $root"; return 0; }
    sleep 1
  done
  echo "backend NOT READY at $root"; return 1
}
# wait_run <run-id> [seconds] — polls the API, prints the terminal status
wait_run() {
  [ -z "${1:-}" ] && { echo "no run"; return; }
  local n=${2:-300}
  for i in $(seq 1 "$n"); do
    st=$(curl -s "$API/runs/$1" | py 'print(d.get("status",""))' 2>/dev/null)
    case "$st" in completed|failed|cancelled) echo "$st"; return;; esac
    sleep 1
  done
  echo "timeout"
}
# approve_when_paused <run-id> [seconds] — approves the gate as soon as it arms, then waits for the end
approve_when_paused() {
  local n=${2:-300}
  for i in $(seq 1 "$n"); do
    st=$(curl -s "$API/runs/$1" | py 'print(d.get("status",""))' 2>/dev/null)
    [ "$st" = "paused_hitl" ] && curl -s -X POST "$API/runs/$1/hitl" -H "$H" -d '{"decision":"approve"}' -o /dev/null
    case "$st" in completed|failed|cancelled) echo "$st"; return;; esac
    sleep 1
  done
  echo "timeout"
}
steps() { curl -s "$API/runs/$1" | py 'print([(s["step_type"], s.get("node_id") or "", s["status"], ((s.get("output") or {}).get("reason","") if isinstance(s.get("output"),dict) else "")) for s in d["steps"]][:14])'; }
shot() { ACC_BASE="$ACC_BASE" ACC_SHOTS="${ACC_SHOTS:-$ACC_HERE/shots}" ACC_CHROMIUM="${ACC_CHROMIUM:-}" node "$ACC_HERE/../shot.mjs" "$@" 2>&1 | tail -1; }
kill_stub() {
  docker exec "$ACC_BACKEND_CONTAINER" python -c "import os,signal; pids=[int(p) for p in os.listdir('/proc') if p.isdigit() and b'stub_mcp_server' in open(f'/proc/{p}/cmdline','rb').read()]; [os.kill(p, signal.SIGKILL) for p in pids]; print('stub process killed:', pids)"
}
API=$(api_root)
