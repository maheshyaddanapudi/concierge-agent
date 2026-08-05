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

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
