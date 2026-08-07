#!/usr/bin/env bash
# quick-setup.sh — one-time developer setup: env file, API key, and local
# dependencies for backend (uv) and frontend (npm). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
# portable lowercase-compare — macOS ships bash 3.2 (no ${var,,})
is_yes() { case "$1" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

# ── flags ────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
quick-setup.sh — one-time developer setup: .env, provider API keys
(verified before saving), optional Redis, and local dev dependencies.
Safe to re-run any time; run with no flags for the interactive walkthrough.

USAGE
  ./quick-setup.sh [options]

INTERACTIVE (no flags)
  1. Creates .env from .env.example if missing.
  2. Asks which model provider(s) to configure:
       1) Anthropic            2) Google              3) OpenAI
       4) Anthropic + Google   5) Anthropic + OpenAI  6) Google + OpenAI
       7) All three            8) None - keyless demo mode (fake provider)
  3. Prompts for each selected provider's API key (hidden input; offers
     to replace an existing key), then VERIFIES it with a free
     list-models API call. A rejected or unreachable key warns and asks
     "Save it anyway? [y/N]".
  4. Asks whether to provision the optional Redis cache backend
     (usage stays a runtime decision in Settings -> Registry cache).
  5. Installs backend (uv sync) and frontend (npm install) dev deps.

NON-INTERACTIVE OPTIONS
  --providers LIST      Comma list (no spaces): anthropic,google,openai
                        or the shorthands  all | none
                        'none' enables keyless demo mode (FAKE_LLM_ENABLED=1)
  --anthropic-key KEY   Set the Anthropic key (implies its provider)
  --google-key KEY      Set the Google key (implies its provider)
  --openai-key KEY      Set the OpenAI key (implies its provider)
  --key KEY             Legacy alias for --anthropic-key
  --redis               Provision the Redis cache backend without asking
  --no-redis            Skip Redis without asking
  -h, --help            Show this help and exit

  Keys passed via flags are still verified; on failure they are saved
  anyway (you passed them explicitly) with a clear warning.

EXAMPLES
  ./quick-setup.sh
  ./quick-setup.sh --providers all --no-redis
  ./quick-setup.sh --anthropic-key sk-ant-... --google-key AIza... --redis
  ./quick-setup.sh --providers none        # keyless demo mode
  CI: ./quick-setup.sh --providers openai --openai-key "$OPENAI_API_KEY" --no-redis

WHAT HAPPENS NEXT
  Only providers with a key appear in the UI's model selects; first boot
  picks default_model from whatever is configured (anthropic sonnet ->
  gemini flash -> gpt-5.6 luna -> fake). Then: ./build.sh && ./start.sh
EOF
}

# --providers anthropic,google,openai|all|none   (comma list, no spaces)
# --anthropic-key K   --google-key K   --openai-key K   (imply their provider)
# --key K             (back-compat alias for --anthropic-key)
# --redis / --no-redis     -h/--help
PROVIDERS=""
KEY_anthropic=""; KEY_google=""; KEY_openai=""
REDIS_CHOICE=""

add_provider() { # $1 = provider id; append if not already listed
  case ",$PROVIDERS," in *",$1,"*) ;; *) PROVIDERS="${PROVIDERS:+$PROVIDERS,}$1" ;; esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)       usage; exit 0 ;;
    --providers)     PROVIDERS="${2:-}"; shift 2 ;;
    --anthropic-key) KEY_anthropic="${2:-}"; add_provider anthropic; shift 2 ;;
    --google-key)    KEY_google="${2:-}";    add_provider google;    shift 2 ;;
    --openai-key)    KEY_openai="${2:-}";    add_provider openai;    shift 2 ;;
    --key)           KEY_anthropic="${2:-}"; add_provider anthropic; shift 2 ;;
    --redis)         REDIS_CHOICE="yes"; shift ;;
    --no-redis)      REDIS_CHOICE="no";  shift ;;
    *) warn "unknown option: $1 (see ./quick-setup.sh --help)"; shift ;;
  esac
done
[ "$PROVIDERS" = "all" ] && PROVIDERS="anthropic,google,openai"

# ── 1. .env ──────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  say "created .env from .env.example"
else
  say ".env already present"
fi

set_env_line() { # $1 = KEY, $2 = value ('' removes the line)
  grep -vE "^$1=" .env > .env.tmp || true
  [ -n "$2" ] && printf '%s=%s\n' "$1" "$2" >> .env.tmp
  mv .env.tmp .env
}

# ── 2. model providers ───────────────────────────────────────────
# Any combination works; only providers with a key show up in the UI's
# model selects. First boot picks the default model from whatever is
# configured (anthropic → gemini flash → gpt-5.6 luna → fake).

if [ -z "$PROVIDERS" ] && [ -t 0 ]; then
  say "Which model provider(s) do you want to configure?"
  printf '  1) Anthropic            2) Google              3) OpenAI\n'
  printf '  4) Anthropic + Google   5) Anthropic + OpenAI  6) Google + OpenAI\n'
  printf '  7) All three            8) None - keyless demo mode (fake provider)\n'
  printf 'Choice [1]: '
  read -r choice
  case "${choice:-1}" in
    1) PROVIDERS="anthropic" ;;
    2) PROVIDERS="google" ;;
    3) PROVIDERS="openai" ;;
    4) PROVIDERS="anthropic,google" ;;
    5) PROVIDERS="anthropic,openai" ;;
    6) PROVIDERS="google,openai" ;;
    7) PROVIDERS="anthropic,google,openai" ;;
    8) PROVIDERS="none" ;;
    *) warn "unrecognized choice '$choice' — defaulting to Anthropic"; PROVIDERS="anthropic" ;;
  esac
elif [ -z "$PROVIDERS" ]; then
  say "non-interactive run with no --providers — leaving provider keys unchanged"
  PROVIDERS="skip"
fi

env_key_name() { # provider id → .env variable name
  case "$1" in
    anthropic) printf 'ANTHROPIC_API_KEY' ;;
    google)    printf 'GOOGLE_API_KEY' ;;
    openai)    printf 'OPENAI_API_KEY' ;;
  esac
}

verify_key() { # $1 = provider, $2 = key → 0 if the key works (cheap list-models call)
  command -v curl >/dev/null 2>&1 || { warn "curl not found — skipping key verification"; return 0; }
  code=""
  case "$1" in
    anthropic)
      code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
        -H "x-api-key: $2" -H "anthropic-version: 2023-06-01" \
        https://api.anthropic.com/v1/models 2>/dev/null || printf '000')" ;;
    google)
      code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
        "https://generativelanguage.googleapis.com/v1beta/models?key=$2" 2>/dev/null || printf '000')" ;;
    openai)
      code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
        -H "Authorization: Bearer $2" \
        https://api.openai.com/v1/models 2>/dev/null || printf '000')" ;;
  esac
  if [ "$code" = "200" ]; then
    say "$1 key verified (list-models call succeeded)"
    return 0
  fi
  case "$code" in
    000) warn "$1 key could not be verified — network unreachable or timeout" ;;
    400|401|403) warn "$1 key REJECTED by the API (HTTP $code) — it looks invalid" ;;
    *) warn "$1 key verification returned HTTP $code" ;;
  esac
  return 1
}

save_key() { # $1 = provider, $2 = key
  set_env_line "$(env_key_name "$1")" "$2"
  say "$(env_key_name "$1") written to .env (never commit this file)"
}

configure_provider() { # $1 = provider id, $2 = key from flags ('' = prompt)
  var="$(env_key_name "$1")"
  current="$(grep -E "^$var=" .env | head -1 | cut -d= -f2- || true)"
  new_key="$2"

  if [ -z "$new_key" ] && [ -t 0 ]; then
    if [ -n "$current" ]; then
      key_tail="$(printf '%s' "$current" | tail -c 4)"
      printf 'A %s is already set (…%s). Replace it? [y/N] ' "$var" "$key_tail"
      read -r replace
      is_yes "$replace" || { say "keeping the existing $1 key"; return 0; }
    fi
    printf 'Paste your %s (input hidden, Enter to skip): ' "$var"
    read -rs new_key; echo
    [ -n "$new_key" ] || { warn "no $1 key provided — re-run ./quick-setup.sh to add it later"; return 0; }
  elif [ -z "$new_key" ]; then
    if [ -n "$current" ]; then say "$var already set — keeping it (non-interactive run)"
    else warn "no TTY and no $1 key — pass one with --$1-key"; fi
    return 0
  fi

  if verify_key "$1" "$new_key"; then
    save_key "$1" "$new_key"
  elif [ -t 0 ]; then
    printf 'Save the unverified %s key anyway? [y/N] ' "$1"
    read -r anyway
    if is_yes "$anyway"; then save_key "$1" "$new_key"; else warn "$1 key NOT saved"; fi
  else
    warn "saving the $1 key anyway (non-interactive run — it was passed explicitly)"
    save_key "$1" "$new_key"
  fi
}

contains_provider() { case ",$PROVIDERS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

if [ "$PROVIDERS" = "none" ]; then
  set_env_line FAKE_LLM_ENABLED "1"
  say "keyless demo mode: FAKE_LLM_ENABLED=1 — first boot will select the"
  say "fake:scripted model; add real keys later by re-running ./quick-setup.sh"
elif [ "$PROVIDERS" != "skip" ]; then
  contains_provider anthropic && configure_provider anthropic "$KEY_anthropic"
  contains_provider google    && configure_provider google    "$KEY_google"
  contains_provider openai    && configure_provider openai    "$KEY_openai"
  set_env_line FAKE_LLM_ENABLED ""
fi

# ── 2b. optional Redis (registry-cache backend, spec §7.3) ───────
# Provisioning is upfront; USAGE stays a runtime decision — the cache mode
# defaults to 'bypass' and is flipped in Settings → Registry cache later.

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

if [ "$REDIS_CHOICE" = "yes" ]; then
  setup_redis
elif [ "$REDIS_CHOICE" = "no" ]; then
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
