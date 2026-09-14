# Dashboards — Prometheus + Grafana provisioning (M53)

The shipped stack is the three compose services (spec §2); Prometheus and
Grafana are **operator tooling**, not part of it. This directory holds the
provisioning that makes them useful against a running stack in one command,
and the two dashboards the M53 runbooks refer to.

```bash
# from the repo root, with the stack up (docker compose up -d)
docker compose -f docs/observability/docker-compose.observability.yml up -d
# Prometheus: http://localhost:9090   Grafana: http://localhost:3000 (admin / admin)
```

The compose file joins the stack's network (`concierge-agent_default` by
default — override `CONCIERGE_NETWORK` if your project name differs) and
scrapes the backend's `/metrics` every 10 s.

The scrape job uses **DNS service discovery**, not a static target (M54):
`dns_sd_configs` resolves the `backend` A records every 15 s, so under
`docker compose up --scale backend=N` each replica is scraped as its own
target and `instance` identifies it. A static `backend:8000` target would
alternate replicas scrape by scrape and render every counter as a series of
resets.

| File | What |
|---|---|
| `prometheus.yml` | one scrape job, `concierge-backend` — DNS-SD on `backend` (A records, port 8000, 15 s refresh), `service=concierge-agent` relabel, 10 s scrape interval |
| `grafana/provisioning/datasources/prometheus.yml` | the Prometheus datasource, default |
| `grafana/provisioning/dashboards/dashboards.yml` | loads `grafana/dashboards/*.json` |
| `grafana/dashboards/saturation.json` | **Saturation** — pool saturation and connections, in-flight vs slots, backlog depth, loop errors, MCP/listener state, SSE subscribers |
| `grafana/dashboards/llm.json` | **LLM** — calls by provider/model/status, error-class rate, latency p50/p95 by model, spend today, spend-ceiling refusals |

Screenshots of both under load are in `docs/acceptance/prod/M53/`. The
metric catalogue is in [`../observability.md`](../observability.md).
