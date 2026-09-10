# Production-hardening drills — campaign v1 on the dev images

The drills in `experiments/acceptance/prod/` re-run against the `dev`
images (release 1.0.0, M1–M56) on 2026-09-10. Each transcript is the
drill's stdout as it ran; frames are the admin UI screenshotted by the
drill at the moments it names. The stack is the three compose services plus
redis (`--profile redis`), one backend replica, the live model
`openrouter:qwen/qwen3.8-max` unless a drill says it runs the fake provider.

| Folder | Drill | What the transcript shows |
|---|---|---|
| `M34/` | `m34-auth.sh` | the builtin auth provider live: the dark gate with security headers, the bootstrap admin's one-time password, a member user, a real-model run under an identity, tenancy on runs and routines both ways, the fire token as the only auth on the fire path, the 429 boundary moving with `rate_limit_burst`; the UI frames are stage `34-auth-builtin` |
| `M49/` | `m49-baseline.sh` | the load baseline (api reads, runs at 1k/10k, chat at c=5/10/25/50, sse fan-out) on the fake provider, the 40-event ambient burst drained without pool exhaustion, a live-model chat sample |
| `M50/` | `m50-quarantine-and-timezone.sh` | trigger validation 422s, a trigger corrupted past the API quarantined after three failures while the healthy routine keeps firing on the same ticks, IANA timezone validation |
| `M51/` | `m51-admission.sh`, `m51-redis-fail-open.sh` | admission floors (422), the 503 + Retry-After past the queue, a queued run as a first-class row, the wall clock failing a run truthfully; the redis-backed registry cache serving from Postgres with redis stopped and recovering; SIGTERM drain vs SIGKILL orphan reaping |
| `M52/` | `m52-untrusted-and-secrets.sh` | egress refusals at the API and in-process (metadata, private, loopback, file, billion-laughs), MCP headers write-only with the row holding the value, no provider key in any response, the sanitizer, the regex guard, a live fence-escape fire the model treats as data |
| `M53/` | `m53-ops.sh` | readiness vs health with the db paused, drain on USR1 with `event: reconnect`, the §10 label set on `/metrics`, retention gates and a bounded purge, the spend ceiling (429, a held fire, off → priced), MCP reconnect with the breaker, LISTEN sessions terminated and recovering, a chat burst under `run_max_concurrent=3`, `deploy.sh` under an open stream with a Last-Event-ID reconnect, `backup.sh` → `restore.sh` with the RTO and byte-identical conversations |
| `M54/` | `m54-recall.sh` | recall latency and the vector-leg plan at 10k → 100k → 1M embeddings on the typed HNSW column (`recall.md`, `recall.json`); the fleet drills (`cold-boot`, `cross-replica-cancel`, `delivery-fan-out`, `job-clock`, `load-n3-vs-n1`, `rate-limiter`) are kept from the same day's capture on the merged code |
| `M55/` | `m55-seam.sh` | the reference stub auth provider selected by environment: 401 without identity, the builtin login not offered, editor-only writes, a live run under an identity, tenant scoping across runs, streams and memory recall, then the builtin back byte-identical |
| `M56/` | `m56-ceremony.sh`, `m56-addendum.sh`, `perf-record.sh` | the §14 acceptance script steps 1–11 on a fresh `docker compose up` with the UI after each step, the direct-invocation error-edge and agentic-todo addendum, and the performance record |

`tests.md` is the backend suite run once on the same commit with the fake
provider.
