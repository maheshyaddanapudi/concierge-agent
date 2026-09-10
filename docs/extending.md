# Extending — forking the platform and adding your auth layer

This repository ships **no authentication**. It ships the seam one plugs
into (spec §20, milestone M55): an `AuthProvider` port, a registry that
selects the active provider by environment, and a core that asks the port
for every identity, tenancy and authorization decision. Adding your
organisation's auth is one module in your fork. This page is the whole
guide; the reference stub in `backend/tests/auth_stub.py` was written from
it without touching anything else.

## What you implement

One class, registered with the decorator, exposing eight members. `Principal`
and the protocol live in `backend/app/auth/port.py`.

```python
from app.auth.port import Principal
from app.auth.registry import auth_provider

@auth_provider
class MyCorpAuth:
    provider_id = "mycorp"

    def enabled(self) -> bool: ...
    async def identify(self, request) -> Principal | None: ...
    def owner_id(self, principal) -> UUID | None: ...
    def tenancy_filter(self, model, principal): ...
    def may_see(self, row, principal) -> bool: ...
    def memory_visibility(self, principal) -> tuple[str, dict]: ...
    async def authorize(self, principal, *, method, path) -> str | None: ...
    async def on_boot(self) -> None: ...
```

| member | what it decides | contract |
|---|---|---|
| `enabled()` | whether the platform is multi-user at all | `False` means the core behaves as the single-user platform: no identity, no filters, no headers — byte-identical to shipping without you |
| `identify(request)` | who is making this request | return a `Principal` or `None`; `None` on a non-exempt `/api/v1` path is a 401. Read headers, cookies, a session store — anything. The core never inspects credentials |
| `owner_id(principal)` | the value stamped into `user_id` on rows this principal creates | a UUID or `None`; `owner_id(None)` must be `None` |
| `tenancy_filter(model, principal)` | the SQL predicate per-user work queries add (conversations, runs, routines, deliveries, watches, memories lists) | a SQLAlchemy clause over `model.user_id`, or `None` for "no filter". The core applies it through `scope_to_user` |
| `may_see(row, principal)` | the same rule for one already-loaded row | must agree with `tenancy_filter`: a row the filter admits is visible and vice versa — the contract suite checks this |
| `memory_visibility(principal)` | the tenancy clause of the memory visibility predicate (spec §16.3) | a SQL fragment over the alias `m` (for example `m.user_id = ANY(CAST(:ids AS uuid[]))`) plus the parameters it binds; `("", {})` for none. Every memory read — recall's two legs, the pinned profile — carries it |
| `authorize(principal, method=, path=)` | whether this request may proceed past identity | `None` to allow, or a reason string that becomes the 403 body. Called for every non-exempt request after `identify`; must never refuse a `GET` (the suite checks) |
| `on_boot()` | anything you need at startup | idempotent; the builtin creates its bootstrap admin here |

## What the core guarantees

- Every per-user store asks `scope_to_user(stmt, Model)` and `owns_row(row)`;
  both are thin façades over your `tenancy_filter` / `may_see`. A rule you
  express once reaches every list and detail endpoint.
- Every memory read goes through `visibility_sql`, which appends your
  `memory_visibility` fragment and binds its parameters.
- Every new work row is stamped with `owner_id(principal)`; run tasks
  re-bind the principal from the run's owner, so ambient fires, evals and
  memory extraction scope their writes to the owner even off-request.
- The middleware calls `identify` first and `authorize` before the handler
  on every non-exempt `/api/v1` request, keys the rate limiter by
  `owner_id`, and adds the security headers. Exempt: `/health`, `/metrics`,
  `/ready`, the login route, and the routine fire endpoint (which carries
  its own hashed fire token).
- No file outside `backend/app/auth/` reads the auth switch; a test fails
  the build if one appears.

## What the core will never do

- Read your credentials, sessions or directory. It has no opinion on how a
  principal is established.
- Thread a user parameter through call sites; the principal rides a
  contextvar that the middleware and the run executor set.
- Special-case a provider. The builtin is registered like yours and passes
  the same contract suite.
- Change the shape of `user_id`. Rows carry one nullable UUID owner; a
  tenancy richer than "owner" is expressed in your filter (the stub's
  "everyone in the tenant" rule uses `IN`), not in the schema.

## Wiring it up

1. Put the module in your fork — `backend/app/auth/providers/mycorp.py` or
   anywhere importable.
2. Set `AUTH_PROVIDER=mycorp` and `AUTH_PROVIDER_MODULE=app.auth.providers.mycorp`
   in the environment (`.env.example` lists both). The registry imports the
   module before resolving, so the decorator registers your class; an
   unknown id fails at boot naming the registered ones.
3. Run the contract suite: `cd backend && pytest tests/test_m55_seam.py`.
   It parametrises over every registered provider; import your module in
   the test session (or set `AUTH_PROVIDER_MODULE` before pytest) and it
   runs over yours too.
4. Write your own end-to-end test the way `TestStubEndToEnd` does: create a
   row as one principal, read it as another, assert what your rule says.

## The reference stub

`backend/tests/auth_stub.py` is the worked example: identity from headers,
rows shared across a tenant, writes gated on an `editor` role. It imports
only `app.auth.port` and `app.auth.registry`, and the seam test proves its
rule end-to-end through the middleware, the stores and memory recall with
zero changes outside that file. If your provider needs a change in the
core to work, that is a seam defect — open an issue rather than patching
around it.

## What stays with the builtin

`AUTH_ENABLED=true` with the default provider gives the §18.8 behaviour:
scrypt passwords, hashed bearer sessions with a TTL, the bootstrap admin,
the `admin` gate on registry and settings writes, per-user ambient
preferences. Its login and user-management routes answer 404 while another
provider is active — they are the builtin's, not the seam's.
