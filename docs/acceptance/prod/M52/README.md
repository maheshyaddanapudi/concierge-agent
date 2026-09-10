# M52 — untrusted input and secrets: executed proof

The wave whose failure mode is an attacker steering an autonomous agent
that holds tools. One adversarial transcript per untrusted source, each
blocked on the shipped stack (rebuilt image, fresh migration), and the
credential-material check across the MCP and run paths. The fence proof is
live on `openrouter:qwen/qwen3.8-max`; the fault injections use the API,
in-container probes against the shipped image, and the fake provider for
the run-failure path.

| file | what it is |
|---|---|
| `fence-escape-live.md` | §14o-77, live on qwen: a webhook payload carrying `</untrusted_event_payload>`, a fake SYSTEM OVERRIDE, and a reopening tag (in the text and in a nested field). The run's message — the prompt the model saw — shows the payload's tags escaped, exactly one real opening and one real closing tag with the same random token, and the instruction still visible as data; the model's report names the injection attempt and does not obey it |
| `untrusted-and-secrets.md` | §14o-78..82 on the shipped stack: `POST /mcp-servers` at the metadata address and at `localhost`, and `POST /remote-agents` at a `10.x` card URL, are 422s naming the egress policy; an `http_json` poll source at the metadata address, `check_url` on private/local/file targets, and a public URL that redirects into loopback are all `egress refused: denied` (the redirect on hop 2, in the request hook); a public name that resolves publicly is allowed; a billion-laughs feed is `feed refused: unsafe or malformed XML`; a 200 KB body is `egress refused: too_large` under a 64 KB cap while 2 KB passes; MCP headers are masked on create, get and list while the row holds the real value, a `***` round-trip keeps the secret, `null` removes, a new value replaces, `env:VAR` resolves at connect; a provider failure carrying a key, a bearer token and a URL password lands in the run row and the log with `[redacted]` in their place (zero raw occurrences); `(a+)+$` and a backreference are 422s naming the reason, an admissible filter saves, and a slow-but-admissible pattern returns under the timeout |
| `tests.md` | `pytest tests/test_m52_untrusted.py -v` — 40 passed |
| `01-mcp-server-headers-write-only.png` | The MCP Servers drawer for a server registered with an `Authorization` header: keys shown as "set", no value, no reveal |

## What each source could do before M52

| source | before | after (this directory) |
|---|---|---|
| a fired event's payload, a remote agent's output, a delivery body, a candidate answer, member memories, a watch request, the remembered-context block | wrapped in a fixed `<untrusted_…>` tag the payload could close and reopen | one choke point neutralizes any fence-shaped tag in the payload and stamps a per-render token on both fence tags; the golden harness pins the tokened prompts; the live model reported the attempt instead of obeying it |
| a URL from a card, a feed, a watch, an MCP registration, the webhook setting | fetched wherever it pointed, redirects followed blind, bodies read whole | judged by literal address and by resolution (`public`), or by an operator allowlist; every redirect hop re-checked; bodies streamed under a cap; one error shape whatever the cause; counted in `concierge_egress_refused_total{kind}` |
| an RSS/Atom document | `defusedxml` (M49) but parsed on the event loop, error text carried the parser's message | parsed off the loop, one refusal message, never the document |
| MCP `env`/`headers` | returned in every read, reveal-on-click in the UI | write-only: masked reads, merge-on-write, `env:VAR` indirection |
| an exception message | persisted and returned as-is — provider SDKs echo the request they failed on | one sanitizer before every persistence and response, and a structlog processor on every log line |
| a `regex` filter | compiled, then run raw on the tick's thread | static guard at the API and before every match; the match runs in a worker thread under a timeout, counted in `concierge_regex_guard_total{outcome}` |

## Honest notes

- The MCP connect-error transcript points the server at a public URL that
  answers 401; the SDK's error text names the URL, not the header, so the
  row shows nothing to redact there. The sanitizer's handling of a
  record's own secrets is asserted by the contract test
  (`_describe(exc, secrets=[…])`), not by that transcript.
- The egress counter and the `egress_refused` log lines in the transcript
  come from the server process for the API refusals; the in-container
  probes run in their own process, so their refusals appear in the
  probe's stdout (the `[warning] egress_refused` lines) rather than in
  the server's `/metrics`.
- The stdio `fetch` MCP server makes its own connections from its own
  process; the policy governs the backend's clients, not a subprocess's.
  `docs/security.md` says so.

## Reproduce

```bash
FAKE_LLM_ENABLED=1 docker compose up -d --build      # EGRESS_POLICY defaults to public
cd backend && FAKE_LLM_ENABLED=1 pytest tests/test_m52_untrusted.py -v
# the drivers are curl/psql/in-container-python transcripts against the shipped API;
# every command is echoed at the top of each block in the .md files here
```
