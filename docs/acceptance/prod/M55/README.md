# M55 — the fork seam: executed proof

**No authentication was built.** What was built is the socket an
organisation's own auth plugs into (spec §20): the `AuthProvider` port and
registry in `backend/app/auth/`, the builtin provider carrying the §18.8
behaviour behind it, a contract suite over every registered provider, and
a reference stub that enforces a rule the builtin does not — rows shared by
tenant, writes gated on an `editor` role — from one module. The §14r items
(97–99) are proven two ways: the suite in `tests.md`, and the stub selected
by environment alone on the shipped stack with a run on the live model
(`seam-drill.md`).

| file | what it is |
|---|---|
| `seam-drill.md` | §14r-97 on the shipped image with `AUTH_PROVIDER=stub AUTH_PROVIDER_MODULE=tests.auth_stub` and nothing else changed: no identity → 401 while `/health` stays open; the builtin's login route answers 404 under another provider; `bob@acme` (member) `PATCH /settings` → 403 with the **stub's** reason, `alice@acme` (editor) → 200; a chat run on `openrouter:qwen/qwen3.8-max` created by alice is owned by her stub id, readable by bob (same tenant, 200) and a 404 to `carol@globex`, whose `/runs` and `/conversations` are empty; the run stream is bob's to read and a 404 to carol; a memory alice stores is recalled by bob and not by carol. Then `AUTH_PROVIDER` unset: the same image is the single-user platform — no identity needed, no security headers, login 409 while dark. **The first pass found a hole** (below) and is kept as `seam-drill-first-pass.md` |
| `tests.md` | §14r-98/99: the contract suite over `builtin` and `stub`, the registry, the stub end-to-end, the structural guard (no file outside `app/auth/` reads the switch), byte-identity with the default provider; the full suites |

## What the drill found and what changed because of it

- **The run stream never asked the port.** `GET /chat/stream/{run}` checked
  that the run existed and streamed the whole record — `carol@globex` read
  alice's answer token by token while every REST surface said 404. The
  route now asks `owns_row` before it opens, and the ambient delivery
  stream checks `may_see` on every event against the subscriber's principal
  (the delivery's owner now rides the event), so a toast for one tenant
  never reaches another's browser. Two tests in the seam suite hold both.
  This was an M34 gap, invisible until a provider with a rule the builtin
  lacks was pushed through every surface — which is what the seam is for.
- **The stub's own rows.** The first stub made a principal's visibility
  "everyone recorded in my tenant", so a principal that had not been seen
  before could not see its own row; the contract suite's "filter and row
  check are one rule" case caught it and the stub now includes the
  principal's own id. Recorded here because it is exactly the class of
  mistake the suite exists to catch in a fork.
- **The run executor judged visibility for the wrong principal.** Routing
  the conversation check through `owns_row` compared against the request
  principal; a routine fires as its owner off-request, so the M34 test for
  it failed. `visible_to(row, owner_id)` judges the same rule for a given
  owner and the executor uses it.
- **Numbering.** The plan named the seam "§21"; the spec ends at §19, so
  the section is §20 and the plan row says so.
