#!/usr/bin/env bash
# quick-setup.sh — one-time developer setup: env file, API key, and local
# dependencies for backend (uv) and frontend (npm). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
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
    printf 'An ANTHROPIC_API_KEY is already set (…%s). Replace it? [y/N] ' "${current_key: -4}"
    read -r replace
    if [ "${replace,,}" = "y" ]; then
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
