# Runbook — an MCP server's circuit is open

**What it is.** A server that fails to connect, or fails a health ping, is
retried automatically with exponential backoff — 5 s doubling to a 5-minute
cap (`mcp_auto_reconnect_enabled`, on by default). After
`mcp_reconnect_max_attempts` consecutive failures (8 by default) the
**circuit opens**: the automatic retry stops, the row goes `status='error'`
with `last_error` saying so, and nothing will try again until an operator
does. That is deliberate — a server that has failed eight times with
growing backoff is not coming back on its own, and a retry loop against a
dead stdio launcher or a 401'ing endpoint costs more than it buys.

An open circuit is **not** an outage of the platform. The server's tools go
out of the catalog, a skill bound to one shows the tool as unavailable with
the reason, and a tool call that does reach the lazy proxy fails as a tool
error — which routes a workflow node's error edge, exactly as designed.

## The metric that reveals it

| Signal | Healthy | Circuit open |
|---|---|---|
| `concierge_mcp_servers{state="connected"}` | equals your active server count | short by one or more |
| `concierge_mcp_servers{state="circuit_open"}` | 0 | ≥ 1 |
| `concierge_mcp_servers{state="reconnecting"}` | 0, or briefly 1 during a blip | 0 **while** `circuit_open` ≥ 1 — that is the tell: nothing is retrying |
| `concierge_mcp_reconnects_total{outcome}` | `ok` increments after a blip | `failed` climbs, then one `circuit_open` |
| log `mcp_circuit_open` | absent | one WARNING naming `server_id` and `attempts` |
| log `mcp_reconnect_scheduled` | present during a retry ladder, with `attempt` and `delay_s` | **stops** once the circuit opens |
| `GET /api/v1/mcp-servers` | `status: "active"` | `status: "error"`, `last_error` = `"circuit open after N failed reconnect attempts (mcp_reconnect_max_attempts) — reconnect manually"` |
| `concierge_skill_tool_unavailable_total` | flat | climbing as skills bound to the server's tools are built |

Two things look like this and are not: **the operator deactivated the
server** (`status: "inactive"`, no `mcp_circuit_open` line — a deliberate
state the reconnect machinery leaves alone), and **`mcp_auto_reconnect_enabled`
is off**, in which case a failure leaves the row `error` with the underlying
error, never the circuit message, and no retry ladder ever ran.

## First checks

```bash
PORT=$(docker compose port backend 8000 | head -1 | sed 's/.*://')
curl -s "http://localhost:${PORT}/metrics" | grep -E 'concierge_mcp_'
curl -s "http://localhost:${PORT}/api/v1/mcp-servers" \
  | python3 -c 'import json,sys;[print(s["id"], s["status"], s["transport"], s["tool_count"], repr(s["last_error"])[:120]) for s in json.load(sys.stdin)]'
docker compose logs --since 1h backend \
  | grep -E 'mcp_(circuit_open|reconnect_scheduled|reconnected|connect_failed|server_config_changed)'
```

Then read `last_error` on the row — it is the *underlying* failure that the
ladder kept hitting, sanitized, and it is what tells the causes apart:

1. **stdio: the launcher is not allowed or not installed** — the error names
   the launcher and the allowlist (`add more with MCP_STDIO_ALLOW`), or the
   command simply is not on `PATH` in the backend image. Nothing about the
   server is wrong; the container cannot start it.
2. **stdio: the process starts and dies** — a missing package, a bad arg, a
   sandbox path the process cannot read. `docker compose exec backend <command> <args>`
   reproduces it directly.
3. **http: the endpoint refuses or is unreachable** — a 401/403 (credentials
   rotated; remember `env`/`headers` are write-only, and `env:VAR`
   indirection resolves at connect time, so an unset variable looks exactly
   like a wrong secret), a DNS failure, or **`egress refused: <kind>`** — the
   §M52 policy declining a private or loopback target. `concierge_egress_refused_total`
   moves in that last case.
4. **The server is genuinely down.** Everything above is fine; the peer is not.

## The action that resolves it

- **Any cause, once fixed**: `POST /api/v1/mcp-servers/{id}/reconnect`, or
  **Reconnect** in the server drawer. An explicit connect resets the attempt
  budget **and closes the circuit** — that is the only thing that does. A
  settings change does not; neither does a health tick.
- Cause 1: add the launcher to `MCP_STDIO_ALLOW` (comma-separated) in the
  backend environment and recreate the container, or switch the server to a
  launcher already on the list.
- Cause 2: fix the command/args on the row (`PATCH /mcp-servers/{id}`). An
  `args` or `command` edit is logged as `mcp_server_config_changed` and
  reconnects at once — a masked-secret round-trip (`***` unchanged) is
  deliberately *not* an edit and does not reconnect.
- Cause 3: rotate the credential (write-only fields: send the new value, or
  `env:VAR` and set the variable), or name the host in `EGRESS_ALLOW_HOSTS`
  if it is an internal server the `public` policy is right to refuse.
- Cause 4: leave it. Deactivating the server (`status: "inactive"`) stops
  the noise and keeps the operator's intent — a later re-ingest will not
  re-enable it.
- If a whole class of servers is flapping, raise `mcp_reconnect_max_attempts`
  (Settings → MCP) so the ladder is longer before the circuit opens; if you
  want no automatic retry at all, turn `mcp_auto_reconnect_enabled` off and
  reconnect by hand.

**Do not** delete and re-register the server to clear the circuit: that
creates a new registry id, orphans the skills bound to its tools, and loses
the operator decisions (`ingest_state`, descriptions, exposure) the re-ingest
rules exist to preserve.

## Recovery looks like

`concierge_mcp_servers{state="circuit_open"}` back to 0 and
`{state="connected"}` back to its full count, one `mcp_reconnected` log line,
the row `status: "active"` with a fresh `last_connected_at` and a null
`last_error`, and its tools back in the catalog on the next model call (the
registry cache is invalidated by the ingest).
