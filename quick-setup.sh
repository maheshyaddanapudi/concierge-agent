#!/usr/bin/env bash
# quick-setup.sh — one-time developer setup: env file, API key, and local
# dependencies for backend (uv) and frontend (npm). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
# portable lowercase-compare — macOS ships bash 3.2 (no ${var,,})
is_yes() { case "$1" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

# ── 1. .env ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  say "created .env from .env.example"
else
  say ".env already present"
fi

# ── 2. ANTHROPIC_API_KEY ─────────────────────────────────────────
current_key="$(grep -E '^ANTHROPIC_API_KEY=' .env | head -1 | cut -d= -f2- || true)"

write_key() { # $1 = key value; replaces any existing line (override)
  grep -vE '^ANTHROPIC_API_KEY=' .env > .env.tmp || true
  printf 'ANTHROPIC_API_KEY=%s\n' "$1" >> .env.tmp
  mv .env.tmp .env
  say "ANTHROPIC_API_KEY written to .env (never commit this file)"
}

if [ "${1:-}" = "--key" ] && [ -n "${2:-}" ]; then
  write_key "$2"
elif [ -t 0 ]; then
  if [ -n "$current_key" ]; then
    key_tail="$(printf '%s' "$current_key" | tail -c 4)"
    printf 'An ANTHROPIC_API_KEY is already set (…%s). Replace it? [y/N] ' "$key_tail"
    read -r replace
    if is_yes "$replace"; then
      printf 'Paste the new ANTHROPIC_API_KEY (input hidden): '
      read -rs new_key; echo
      [ -n "$new_key" ] && write_key "$new_key" || warn "empty input — keeping the existing key"
    else
      say "keeping the existing key"
    fi
  else
    printf 'Paste your ANTHROPIC_API_KEY (input hidden, Enter to skip): '
    read -rs new_key; echo
    if [ -n "$new_key" ]; then
      write_key "$new_key"
    else
      warn "no key provided — you can re-run ./quick-setup.sh later, or use the"
      warn "keyless demo mode (FAKE_LLM_ENABLED=1 + the fake:scripted model)."
    fi
  fi
else
  if [ -n "$current_key" ]; then
    say "ANTHROPIC_API_KEY already set — keeping it (non-interactive run)"
  else
    warn "no TTY and no key set — pass one with: ./quick-setup.sh --key sk-ant-..."
  fi
fi

# ── 2b. optional Redis (registry-cache backend, spec §7.3) ───────
# Provisioning is upfront; USAGE stays a runtime decision — the cache mode
# defaults to 'bypass' and is flipped in Settings → Registry cache later.
set_env_line() { # $1 = KEY, $2 = value ('' removes the line)
  grep -vE "^$1=" .env > .env.tmp || true
  [ -n "$2" ] && printf '%s=%s\n' "$1" "$2" >> .env.tmp
  mv .env.tmp .env
}

setup_redis() {
  set_env_line REDIS_URL "redis://redis:6379/0"
  set_env_line COMPOSE_PROFILES "redis"
  say "Redis provisioned: ./start.sh will now include the redis service"
  say "(cache mode stays 'bypass' until you flip it in Settings → Registry cache)"
}

skip_redis() {
  set_env_line REDIS_URL ""
  set_env_line COMPOSE_PROFILES ""
  say "Redis not provisioned — memory/bypass cache modes remain available"
}

if [ "${1:-}" = "--redis" ] || [ "${2:-}" = "--redis" ] || [ "${3:-}" = "--redis" ]; then
  setup_redis
elif [ "${1:-}" = "--no-redis" ] || [ "${2:-}" = "--no-redis" ] || [ "${3:-}" = "--no-redis" ]; then
  skip_redis
elif [ -t 0 ]; then
  printf 'Set up Redis as an optional registry-cache backend? [y/N] '
  read -r want_redis
  if is_yes "$want_redis"; then setup_redis; else skip_redis; fi
else
  say "non-interactive run — Redis unchanged (use --redis / --no-redis)"
fi

# ── 3. backend dependencies (local dev; docker builds are separate) ──
if command -v uv >/dev/null 2>&1; then
  say "installing backend dependencies (uv sync)…"
  (cd backend && uv sync)
else
  warn "uv not found — skipping local backend deps (install: https://docs.astral.sh/uv/)"
  warn "docker builds via ./build.sh do not need local uv."
fi

# ── 4. frontend dependencies ─────────────────────────────────────
if command -v npm >/dev/null 2>&1; then
  say "installing frontend dependencies (npm install)…"
  (cd frontend && npm install)
else
  warn "npm not found — skipping local frontend deps (install Node 22+)"
  warn "docker builds via ./build.sh do not need local npm."
fi

say "setup complete. Next: ./build.sh (build images) then ./start.sh (run the stack)."
