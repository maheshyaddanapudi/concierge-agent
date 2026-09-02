# §14o-78..82 — SSRF, XML and body caps, write-only MCP secrets, the sanitizer, the regex guard

Against the shipped stack (`EGRESS_POLICY` unset → `public`, no allowlist, 5 MiB cap): refusals at the API (`POST /mcp-servers`, `POST /remote-agents`), in the poll-source fetch path, on a hostname's resolution, and on a redirect hop — with the server's counter and log lines; a billion-laughs document and an oversized body refused; MCP headers masked on every read while the row keeps the real value, the masked round-trip, null-removes, `env:VAR` indirection; a provider failure carrying a key, a bearer token and a URL password persisted and logged with `[redacted]`; catastrophic regexes refused at the API, an admissible one saved, the match bounded. The in-container blocks (`m52_probe.py`) run inside the shipped image with `PYTHONPATH=/app`. Captured by `m52-evidence.sh`.

```text

$ backend env: EGRESS_POLICY / EGRESS_ALLOW_HOSTS / EGRESS_MAX_BYTES
EGRESS_POLICY=<unset → public> EGRESS_ALLOW_HOSTS=<unset> EGRESS_MAX_BYTES=<unset → 5 MiB>

$ GET /metrics egress_refused (before)
(none yet)

$ POST /mcp-servers http url=http://169.254.169.254/mcp
{"detail":"url refused by the egress policy (denied)"}
HTTP 422

$ POST /mcp-servers http url=http://localhost:8080/mcp
{"detail":"url refused by the egress policy (denied)"}
HTTP 422

$ PATCH /settings a2a_enabled=true; POST /remote-agents card_url=http://10.0.0.7/.well-known/agent.json
{"detail":"card_url refused by the egress policy (denied)"}
HTTP 422

$ in-container probes (the shipped image, PYTHONPATH=/app)

$ http_json_source(url=http://169.254.169.254/latest/meta-data/)  [the metadata address]
2026-09-02 01:22:28 [warning  ] egress_refused                 detail='address 169.254.169.254 is in a refused range' host=169.254.169.254 kind=denied
EgressError: egress refused: denied   (kind=denied; detail stays in the log)

$ egress.check_url(http://10.0.0.5/)
2026-09-02 01:22:28 [warning  ] egress_refused                 detail='address 10.0.0.5 is in a refused range' host=10.0.0.5 kind=denied
EgressError: egress refused: denied

$ egress.check_url(http://localhost:8000/health)
2026-09-02 01:22:28 [warning  ] egress_refused                 detail="host 'localhost' is local" host=localhost kind=denied
EgressError: egress refused: denied

$ egress.check_url(file:///etc/passwd)
2026-09-02 01:22:28 [warning  ] egress_refused                 detail="scheme 'file' is not http(s)" host= kind=denied
EgressError: egress refused: denied

$ a public name that resolves — egress.check_url(https://openrouter.ai/)
allowed (resolved to a public address)

$ redirect into loopback: fetch https://httpbin.org/redirect-to?url=http://127.0.0.1/admin
2026-09-02 01:22:28 [warning  ] egress_refused                 detail='address 127.0.0.1 is in a refused range' host=127.0.0.1 kind=denied
EgressError: egress refused: denied   ← hop 2 refused in the request hook

$ GET /metrics egress_refused (after)
concierge_egress_refused_total{kind="denied"} 3.0

$ backend log: egress_refused lines (kind + host only — the detail is truncated and the URL never returned)
{"kind": "denied", "host": "169.254.169.254", "detail": "address 169.254.169.254 is in a refused range", "event": "egress_refused", "level": "warning", "timestamp": "2026-09-02T01:22:27.614875Z"}
{"kind": "denied", "host": "localhost", "detail": "host 'localhost' is local", "event": "egress_refused", "level": "warning", "timestamp": "2026-09-02T01:22:27.623746Z"}
{"kind": "denied", "host": "10.0.0.7", "detail": "address 10.0.0.7 is in a refused range", "event": "egress_refused", "level": "warning", "timestamp": "2026-09-02T01:22:27.658524Z"}

$ _parse_feed(<billion-laughs document, 3 entity levels>)
ValueError: feed refused: unsafe or malformed XML

$ fetch_bytes(https://httpbin.org/bytes/200000, max_bytes=64000)
2026-09-02 01:22:30 [warning  ] egress_refused                 detail='https://httpbin.org/bytes/200000: content-length 102400 > 64000' host=httpbin.org kind=too_large
EgressError: egress refused: too_large

$ fetch_bytes(https://httpbin.org/bytes/2000, max_bytes=64000)
fetched 2000 bytes under the cap

$ POST /mcp-servers http (a public host that answers 401) with an Authorization header
{'id': 'c8969a34-e96e-4ddf-8aa2-d8b11dc430bf', 'status': 'error', 'headers': {'X-Team': '***', 'Authorization': '***'}}

$ GET /mcp-servers/c8969a34-e96e-4ddf-8aa2-d8b11dc430bf → headers masked
{'X-Team': '***', 'Authorization': '***'}

$ psql: the row holds the real value
{"X-Team": "ops", "Authorization": "Bearer m52-top-secret-token-9f8e7d6c"}

$ PATCH /mcp-servers/c8969a34-e96e-4ddf-8aa2-d8b11dc430bf headers={Authorization: '***', X-Team: null, X-New: 'v2'}  (a masked round-trip)
{'X-New': '***', 'Authorization': '***'}
{"X-New": "v2", "Authorization": "Bearer m52-top-secret-token-9f8e7d6c"}

$ the secret string never appears in any response: grep across list/get
0

$ mask_map({"Authorization": "Bearer abc", "X-Team": "ops"})
{'Authorization': '***', 'X-Team': '***'}

$ merge_secret_map(stored={"Authorization": "Bearer abc"}, patch={"Authorization": "***", "X-New": "v2", "X-Team": None})
{'Authorization': 'Bearer abc', 'X-New': 'v2'}

$ resolve_secret_map({"Authorization": "env:M52_DEMO_TOKEN", "X-Team": "ops"})  with M52_DEMO_TOKEN in the process env
{'Authorization': 'resolved-from-env', 'X-Team': 'ops'}

$ GET /mcp-servers/c8969a34-e96e-4ddf-8aa2-d8b11dc430bf → last_error after the 401 connect attempt (the header value is the server's own secret)
{'status': 'error', 'last_error': "HTTPStatusError: Client error '401 Unauthorized' for url 'https://httpbin.org/status/401'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401"}

$ PATCH /settings default_model=fake:scripted; POST /_fake/script with an error carrying a key and a bearer token
{"queued":1,"pending":1}

$ GET /runs/9624a7e9-9c71-4110-bde3-01287b11d61c → error and step errors
{'status': 'failed', 'error': 'RuntimeError: upstream 401: invalid api key [redacted] (Authorization: [redacted] [redacted]) for redis://[redacted]@redis:6379/0'}
steps: [('plan', None)]

$ psql: the persisted row
RuntimeError: upstream 401: invalid api key [redacted] (Authorization: [redacted] [redacted]) for redis://[redacted]@redis:6379/0

$ backend log: the same failure as logged (structlog processor)
{"run_id": "9624a7e9-9c71-4110-bde3-01287b11d61c", "event": "run_failed", "level": "error", "timestamp": "2026-09-02T01:22:38.854839Z", "exception": "Traceback (most recent call last):\n  File \"/app/app/orchestrator/runner.py\", line 311, in _execute\n    outcome = await _run_graph(ctx, task_text, 
occurrences of the raw key in the last 2 minutes of logs: 0

$ sanitize_error(<provider error carrying five credential shapes>)
in : openai 401: invalid api key sk-live-0123456789abcdefABCDEF (Authorization: Bearer sk-live-0123456789abcdefABCDEF); redis://:hunter2@redis:6379/0; x-api-key: ZZZ-42; AKIAABCDEFGHIJKLMNOP
out: openai 401: invalid api key [redacted] (Authorization: [redacted] [redacted]); redis://[redacted]@redis:6379/0; x-api-key: [redacted]; [redacted]

$ PATCH /settings ambient_enabled=true; POST /routines with a webhook regex filter (a+)+$
{"detail":[{"type":"value_error","loc":["body","triggers",0,"webhook","filters",0,"value"],"msg":"Value error, regex filter refused: regex nests a repetition inside a repeated group (catastrophic backtracking)","input":"(a+)+$","ctx":{"error":{}}}]}
HTTP 422

$ POST /routines with a backreference filter
{"detail":[{"type":"value_error","loc":["body","triggers",0,"webhook","filters",0,"value"],"msg":"Value error, regex filter refused: regex uses a backreference, which is not allowed","input":"(a)\\\\1","ctx":{"error":{}}}]}
HTTP 422

$ POST /routines with an admissible filter
{'name': 'm52-regex-ok', 'status': 'active'}

$ check_pattern('(a+)+$')
regex nests a repetition inside a repeated group (catastrophic backtracking)

$ check_pattern('^(\\w+\\s?)*$')
regex nests a repetition inside a repeated group (catastrophic backtracking)

$ check_pattern('(a)\\1')
regex uses a backreference, which is not allowed

$ check_pattern('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'…)
regex is longer than 200 characters

$ check_pattern('^ERROR: .*disk')
admissible

$ check_pattern('disk \\d+%')
admissible

$ safe_search("(a|aa)+$", "a"*24 + "b")  — passes the static guard, runs under the timeout
False in 0.057s

$ safe_search("(a+)+$", "aaaa")  — refused before it runs
False in 0.0001s

$ GET /metrics regex_guard
(no refusals counted at match time yet — the API refused them first)
```
