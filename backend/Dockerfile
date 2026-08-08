# Backend image: Python 3.12 + uv (uvx for stdio MCP servers) + Node (npx
# for the seeded filesystem MCP server). Single FastAPI process — runs are
# asyncio tasks, no broker/queue (spec §2).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system -r /tmp/requirements.txt

COPY . .

# pre-warm the seeded MCP servers into local caches so first connect is fast
# and works without registry access at runtime
RUN uvx --with "mcp<2" mcp-server-fetch --help >/dev/null 2>&1 || true
RUN npx -y @modelcontextprotocol/server-filesystem --help >/dev/null 2>&1 || true

# readabilipy (inside mcp-server-fetch's uv env) shells out to node and runs
# `npm install` in its javascript dir on first use — over the stdio transport
# that leaks npm/node output into the JSON-RPC channel at request time, and
# npm-latest undici/whatwg-url require node >=22 while this image ships 20
# (EBADENGINE warns but installs anyway, then crashes at require-time).
# Install at build time with undici pinned to 6.x; jsdom's nested copy must
# go so resolution falls back to the hoisted 6.x. Every step fails the build
# loudly — a silent skip here ships a broken fetch tool.
RUN dir=$(find /root/.cache/uv -type d -path '*readabilipy/javascript' | head -1); \
    test -n "$dir" || { echo "BUILD ERROR: readabilipy not found — the uvx mcp-server-fetch prewarm above must have failed (network?)"; exit 1; }; \
    cd "$dir" \
    && npm install \
    && npm install undici@6.21.3 --no-save \
    && rm -rf node_modules/jsdom/node_modules/undici
# build-time proof: the resolved undici is 6.x and the extraction pipeline runs
RUN dir=$(find /root/.cache/uv -type d -path '*readabilipy/javascript' | head -1); \
    cd "$dir" \
    && node -e "const v=require('undici/package.json').version; if(!v.startsWith('6.')) {console.error('BUILD ERROR: undici '+v+' resolved, need 6.x for node 20'); process.exit(1)}" \
    && printf '<html><body><article><h1>t</h1><p>x</p></article></body></html>' > /tmp/rt.html \
    && node ExtractArticle.js -i /tmp/rt.html >/dev/null \
    && rm /tmp/rt.html

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
