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
scrapes `backend:8000/metrics` every 10 s.

| File | What |
|---|---|
| `prometheus.yml` | one scrape job, `backend:8000` |
| `grafana/provisioning/datasources/prometheus.yml` | the Prometheus datasource, default |
| `grafana/provisioning/dashboards/dashboards.yml` | loads `grafana/dashboards/*.json` |
| `grafana/dashboards/saturation.json` | **Saturation** — pool saturation and connections, in-flight vs slots, backlog depth, loop errors, MCP/listener state, SSE subscribers |
| `grafana/dashboards/llm.json` | **LLM** — calls by provider/model/status, error-class rate, latency p50/p95 by model, spend today, spend-ceiling refusals |

Screenshots of both under load are in `docs/acceptance/prod/M53/`. The
metric catalogue is in [`../observability.md`](../observability.md).
