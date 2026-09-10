---
name: Bug report
about: Something behaves differently from the spec or the docs
labels: bug
---

**Spec section** (`spec.md §…`) or doc page the behaviour contradicts:

**What happened** (the request, the response or trace, the log line):

**What the spec says should happen**:

**How to reproduce** on a fresh `docker compose up` (or `FAKE_LLM_ENABLED=1` if a model is not needed):

1.
2.

**Version**: commit / tag, provider and model, `AUTH_PROVIDER` if not `builtin`.

**Evidence**: transcript, screenshot, or the failing test (`cd backend && pytest -k …`).
