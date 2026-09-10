# Security policy

## Reporting a vulnerability

Open a **private security advisory** on the repository (GitHub → Security →
Report a vulnerability). Do not open a public issue for anything that could
be exploited before it is fixed. Include the version or commit, the
component (backend, frontend, an MCP server, the load harness), steps to
reproduce, and what an attacker gains. You will get an acknowledgement, a
severity assessment, and a fix or a stated reason it will not be fixed; the
advisory is published when the fix ships.

## What is in scope

- The backend API and its middleware, the orchestrator, the MCP manager,
  the memory and ambient planes, the auth seam (`backend/app/auth/`).
- The frontend and its rendering of model output (spec §8; `docs/security.md`
  describes the markdown, A2UI and chart paths).
- The compose deployment as shipped, the deploy/backup/restore scripts.
- The egress policy (`EGRESS_POLICY`), the fence tokens around untrusted
  content, the error sanitiser, the regex guards — the M52 controls.

## What is out of scope, and why

- **Authentication and authorisation.** This repository ships **no
  authentication**. It ships the seam an organisation's auth plugs into
  (spec §20, `docs/extending.md`) and a builtin provider that is *dark by
  default*. Reports of "the API is open" against a default deployment are
  correct and by design: run it on localhost or a private network, or fork
  it and add your provider. Reports that the **seam** lets a provider's rule
  be bypassed — a surface that does not ask the port — are in scope and
  taken seriously; that class of defect is exactly what the M55 drill found
  and fixed.
- **Multi-tenancy beyond the seam.** Rows carry one nullable owner; richer
  tenancy is a provider's filter.
- **MCP servers and remote agents you register.** A stdio server is a
  subprocess of the backend; an HTTP server or an A2A agent is an endpoint
  you chose to trust. Their behaviour is theirs.
- **Provider platforms** (OpenRouter, Anthropic, Google, OpenAI) and the
  models themselves, including prompt-injection through model output that
  the fence and sanitiser controls do not claim to prevent.

## Secrets

Provider keys, session tokens and passwords are environment-only — never in
the database, never in the UI, never in logs (`docs/security.md`, the M52
sanitiser). If you find one anywhere else, that is a vulnerability.

## Supported versions

The `v1.0.0` line on the default branch. Fixes land on the default branch;
there are no backports.
