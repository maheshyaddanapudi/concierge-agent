# Backend image: Python 3.12 + uv (uvx for stdio MCP servers) + Node (npx
# for the seeded filesystem MCP server). Single FastAPI process — runs are
# asyncio tasks, no broker/queue (spec §2).
FROM python:3.12-slim

# The exact @modelcontextprotocol/server-filesystem release this image bakes
# into the npx cache. The seeded MCP server arguments pin the SAME string
# (backend/app/seed/loader.py) — npx keys its cache directory off the full
# package spec, so an unpinned runtime spec would miss this cache entirely and
# go to the network on first spawn. Bump both together, never one alone.
ARG MCP_FILESYSTEM_VERSION=2026.8.31

# Dedicated unprivileged account. The stdio MCP transport spawns child
# processes (uvx, npx) from this process; running that as root would hand any
# tool-driven command execution the whole container. uid/gid 1000 is fixed so
# the /workspace named volume keeps a stable owner across rebuilds.
ENV APP_UID=1000 \
    APP_GID=1000 \
    APP_USER=concierge
RUN groupadd --gid "$APP_GID" "$APP_USER" \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --shell /bin/sh \
       --create-home --home-dir "/home/$APP_USER" "$APP_USER"

# uvx and npx must find writable caches as the non-root user: point HOME and
# every tool cache at the account's home BEFORE the prewarm steps below, so
# the caches are built, by that account, exactly where they are read at
# runtime. Every `/root/.cache/uv` path this file used to hard-code now goes
# through $UV_CACHE_DIR for the same reason.
ENV PYTHONUNBUFFERED=1 \
    HOME=/home/concierge \
    XDG_CACHE_HOME=/home/concierge/.cache \
    UV_CACHE_DIR=/home/concierge/.cache/uv \
    UV_TOOL_DIR=/home/concierge/.local/share/uv/tools \
    NPM_CONFIG_CACHE=/home/concierge/.npm \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# This install runs as ROOT (it writes /usr/local site-packages), so it must
# NOT use $UV_CACHE_DIR: root-owned files inside the runtime account's cache
# would make the uvx prewarm below — which runs as that account — fail to
# write. Give it a throwaway cache and drop it in the same layer; the app's
# wheels are already unpacked into site-packages, nothing needs the cache
# again, and the image is smaller for it.
RUN UV_CACHE_DIR=/tmp/uv-build uv export --frozen --no-dev --no-hashes -o /tmp/requirements.txt \
    && UV_CACHE_DIR=/tmp/uv-build uv pip install --system -r /tmp/requirements.txt \
    && rm -rf /tmp/uv-build /tmp/requirements.txt

COPY . .

# Everything above needed root (apt, /usr/local site-packages). Everything
# below does not — and running the prewarms AS the runtime account is what
# keeps the warmed caches usable without a `chown -R` over hundreds of
# megabytes of uv/npm cache (which would duplicate the whole tree into an
# extra layer). /workspace is created and handed over here, before the switch:
# Docker seeds a FRESH named volume from the image directory and KEEPS its
# ownership, so `workspace:` comes up writable on first run. An EXISTING
# volume from a root-era image is not re-chowned — migrate it once with:
#   docker compose run --rm --user 0 --entrypoint chown backend -R 1000:1000 /workspace
# /app is handed over too: the code is read-only in normal operation, but
# Python writes __pycache__ beside it on first import.
RUN mkdir -p /workspace \
    && chown -R "$APP_UID:$APP_GID" /workspace /app /home/concierge
USER concierge

# seed-document gate (spec §13): every .skill.md / .agent.md must be valid
# BEFORE the image ships. Without this a malformed document only surfaces at
# boot — a skill that never loads, or an agent row stuck at status='error'.
# Pure offline validation: no DB, no API keys, no network.
RUN python -m app.doclint

# prompt golden sets (M49, spec §15): a prompt edit that drops a binding
# sentence or renames a placeholder fails HERE, not at request time. Same
# offline discipline as doclint — no DB, no keys, no network.
RUN python -m app.prompts.check

# pre-warm the seeded MCP servers into local caches so first connect is fast
# and works without registry access at runtime
# This prewarm must SUCCEED, not silently pass. With `|| true` a network
# blip cached a no-op layer, and every later build then failed at the
# verification gate below with a misleading "network?" message — the real
# cause (a poisoned cache layer) was invisible and survived rebuilds until
# someone busted the cache by hand. Fail here, where the cause is.
RUN uvx --with "mcp<2" mcp-server-fetch --help >/dev/null 2>&1 \
    && find "$UV_CACHE_DIR" -type d -path '*readabilipy/javascript' | grep -q . \
    || { echo "BUILD ERROR: mcp-server-fetch prewarm failed — readabilipy is not in the uv cache. Check network/proxy access to PyPI, then rebuild."; exit 1; }

# The filesystem MCP server, pinned and gated exactly like the fetch server
# above. It used to be `npx -y @modelcontextprotocol/server-filesystem --help
# || true`: unpinned (whatever the registry served that minute became the
# sandbox guarding /workspace) and best-effort (a failed prewarm shipped an
# image whose first tool call reaches the network over the stdio transport).
# Note the server has no --help: an unreadable directory argument makes it
# exit 1, so the prewarm passes a real one and lets stdin EOF end the process.
RUN npx -y "@modelcontextprotocol/server-filesystem@${MCP_FILESYSTEM_VERSION}" /tmp </dev/null >/dev/null 2>&1 \
    && pkg="$(find "$NPM_CONFIG_CACHE/_npx" -type f -path '*@modelcontextprotocol/server-filesystem/package.json' | head -1)" \
    && test -n "$pkg" \
    && node -e "const want='${MCP_FILESYSTEM_VERSION}', got=require('$pkg').version; if (got !== want) { console.error('BUILD ERROR: npx cached server-filesystem '+got+', expected '+want); process.exit(1); }" \
    || { echo "BUILD ERROR: @modelcontextprotocol/server-filesystem@${MCP_FILESYSTEM_VERSION} prewarm failed — the pinned version is not in the npx cache. Check network/proxy access to the npm registry, then rebuild."; exit 1; }

# readabilipy (inside mcp-server-fetch's uv env) shells out to node and runs
# `npm install` in its javascript dir on first use — over the stdio transport
# that leaks npm/node output into the JSON-RPC channel at request time, and
# npm-latest undici/whatwg-url require node >=22 while this image ships 20
# (EBADENGINE warns but installs anyway, then crashes at require-time).
# Install at build time with undici pinned to 6.x; jsdom's nested copy must
# go so resolution falls back to the hoisted 6.x. Every step fails the build
# loudly — a silent skip here ships a broken fetch tool.
# Fix EVERY cached copy — tool envs under archive-v0 AND the wheel cache
# (wheels-v6). uvx rebuilds tool environments by copying packages from the
# wheel cache, so a fix baked only into the current env is lost the next
# time uvx constructs a fresh env (seen after a long container suspension):
# the new copy has no node_modules and readabilipy re-runs `npm install` at
# request time, pulling node>=22-only undici 8 again.
RUN dirs=$(find "$UV_CACHE_DIR" -type d -path '*readabilipy/javascript'); \
    test -n "$dirs" || { echo "BUILD ERROR: readabilipy not found — the uvx mcp-server-fetch prewarm above must have failed (network?)"; exit 1; }; \
    for dir in $dirs; do \
      cd "$dir" \
      && npm install \
      && npm install undici@6.21.3 --no-save \
      && rm -rf node_modules/jsdom/node_modules/undici || exit 1; \
    done
# build-time proof: EVERY cached copy resolves undici 6.x and extracts
RUN for dir in $(find "$UV_CACHE_DIR" -type d -path '*readabilipy/javascript'); do \
      cd "$dir" \
      && node -e "const v=require('undici/package.json').version; if(!v.startsWith('6.')) {console.error('BUILD ERROR: undici '+v+' resolved in $dir, need 6.x for node 20'); process.exit(1)}" \
      && printf '<html><body><article><h1>t</h1><p>x</p></article></body></html>' > /tmp/rt.html \
      && node ExtractArticle.js -i /tmp/rt.html >/dev/null \
      && rm /tmp/rt.html || exit 1; \
    done

# Last build gate: prove the image really does run unprivileged and that the
# caches the prewarms just built are owned by — and writable to — the account
# the entrypoint uses. A regression here (a stray root-run RUN above, a cache
# path that escaped $HOME) would otherwise only show up as a tool that fails
# at request time, over the stdio transport, in production.
RUN test "$(id -u)" = "$APP_UID" || { echo "BUILD ERROR: expected uid $APP_UID, running as $(id -u)"; exit 1; } \
    && test -w "$UV_CACHE_DIR" \
    && test -w "$NPM_CONFIG_CACHE" \
    && test -w /workspace \
    || { echo "BUILD ERROR: the runtime account cannot write its caches or /workspace"; exit 1; }

EXPOSE 8000
# M53 deploy lifecycle: uvicorn closes the listener at SIGTERM, waits for open
# connections up to --timeout-graceful-shutdown (open SSE streams are ended at
# once by sse-starlette; this bounds any straggler), THEN runs the lifespan
# drain (SHUTDOWN_GRACE_S, default 25 s). 5 + 25 < the compose
# stop_grace_period of 40 s, so the drain always gets its window before the
# kill. Send SIGUSR1 first (deploy.sh does) to flip readiness while the port
# is still open. Port 8000 is above 1024, so binding it needs no privilege.
# --proxy-headers + --forwarded-allow-ips: honour X-Forwarded-For/-Proto from
# the frontend's nginx (which now sets them), so `request.client.host` is the
# CALLER's address rather than the proxy's. The inbound rate limiter keys on
# that, and without this every browser shared one bucket. The allow-list is
# the compose network's private ranges — trusting the header from an
# arbitrary source would let a caller forge its own identity and evade the
# limit entirely, which is worse than one shared bucket.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "5", \
     "--proxy-headers", "--forwarded-allow-ips", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"]
