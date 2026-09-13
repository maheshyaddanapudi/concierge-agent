# ADR-0004: RegistryCache facade with bypass as the shipped default

Status: **Accepted, default amended** (see *Amendment, 2026-09-13*)

Date: 2026-08-06

> The facade, the three backends, the invalidation contract and the rollback
> lever all stand exactly as decided here. **One thing changed: the shipped
> default is now `memory`, not `bypass`.** The record below is left as it was
> written in M7 — the reasoning that produced the original choice is the
> point of keeping it — and the amendment at the end says what changed and
> why. The file keeps its name so existing links resolve.

## Context

After M6, every run-path read (the three registry middlewares, the graph-mode
planner catalog, the resolution ladder, the worker factory's id lookups, the
settings store) executed direct Postgres queries per model call. Correct, but
not production-shaped: a busy orchestrator re-reads small, rarely-changing
catalogs on every loop iteration. M7 had to add a cache without violating the
system's freshness contract ("visible at the next model call") and without
risking a regression in behavior the acceptance campaign had already proven.

## Decision

All run-path registry and settings reads go through one `RegistryCache`
facade (`backend/app/registry_cache.py`) exposing typed reads
(`tools(exposed|full)`, `tools_by_ids`, `skill_by_id`, `sub_agent_cards`,
`sub_agent_snapshot`, `setting`, …). Its storage backend is selected by the
live `registry_cache_mode` setting and flippable at runtime (spec §7.3):

- **`bypass`** *(the default as decided here; see the amendment)* — stateless; every read executes the same Postgres
  queries as before the layer existed. Byte-identical semantics. This is the
  shipped default and the no-degradation rollback lever: flipping back to
  `bypass` is an instant escape hatch from any cache bug.
- **`memory`** — per-process store, per-registry generation counters,
  reload-on-dirty: an invalidation marks the registry stale and the next
  read reloads it wholesale. Registries are small, and full reload can never
  leave a stale embedded relationship (skills embed tool rows, agent records
  embed skill names — dirtying a parent dirties dependents).
- **`redis`** — the same contract over Redis blobs (read-through,
  delete-on-invalidate) for future multi-replica deployments. `REDIS_URL`
  env-only; selecting the mode pings Redis and rejects the save if
  unreachable; optional compose profile.

**Invalidation is event-driven and exhaustive.** Every write path — registry
CRUD, status/exposure toggles, MCP ingest and `listChanged` re-ingest,
cascades, seed reload, settings PATCH — calls `invalidate(registry)` before
returning. **TTLs are forbidden**: an entry is either current or explicitly
invalidated, so the "next model call" freshness contract survives caching.
`GET /cache/status` and `POST /cache/refresh/*` exist as operator
visibility/override (§8.7), never as a correctness mechanism.

## Consequences

Positive:

- Zero-risk rollout: the default changes nothing, and the whole orchestrator
  test suite runs parametrized over cache modes to prove it.
- Mode flips are a live Settings toggle, not a deploy.
- One facade means the retrieval layer (ADR-0005) scores over a cache
  snapshot instead of issuing per-call queries.

Negative:

- The performance win is opt-in; a deployment that never flips to `memory`
  pays the facade indirection for nothing.
- Exhaustive invalidation is a discipline: any *new* write path must
  remember to call `invalidate()` — there is no TTL safety net by design.
- Three backends triple the storage-contract test surface; the redis backend
  is env-gated out of the default test run.

## Amendment — 2026-09-13: the shipped default becomes `memory`

**What changed.** `DEFAULTS["registry_cache_mode"]` in
`backend/app/settings_store.py` is now `"memory"`. Nothing else about this
decision moves: `bypass` remains a valid mode, remains live-flippable from
Settings with no restart, and remains the rollback lever this ADR made it.

**Why.** The original decision optimised for *rollout* risk and read as
though `bypass` bought extra freshness. It does not, and that is the whole
argument:

- Invalidation is event-driven and exhaustive — every write path calls
  `invalidate(registry)` **before returning** — so a cached read is never
  staler than a bypassed one. The freshness contract is "visible at the next
  model call", and `memory` mode satisfies it by construction.
- Therefore `bypass` was paying a full Postgres round-trip on every
  registry and settings read, per model call, for a guarantee the cache
  already gave. The M49 load baseline and the M50 code review both landed on
  the same observation from the other end: `RegistryCache.setting(key)` is
  called ~15 times per ambient tick and several times per run, each a
  round-trip on its own pooled connection in `bypass`.
- **`bypass` is a live read, not a faster cache.** That is the sentence to
  carry: it exists so an operator can take the cache out of the picture while
  diagnosing, not because it is the safe default.

**What did not change, and was verified before the flip.** The cache-mode
contract suite (`tests/test_registry_cache.py`) runs identically over
`bypass` and `memory`, the orchestrator suite is parametrized over both, and
the invalidation-heavy modules (MCP manager, A2A substrate and execution,
seed, orchestrator, M53 operate, switchability) were re-run under the new
default. The flip changes **where a read comes from**, not what it returns.

**One correction to the text above.** This ADR states "**TTLs are
forbidden**: an entry is either current or explicitly invalidated". That was
true when written and is no longer literally true: M54 added
`REGISTRY_CACHE_TTL_S` (300 s), on which every `memory`-mode entry and every
redis blob expires. The *rule* is unchanged — invalidate on every write —
but the TTL now bounds the damage of a **lost cross-replica NOTIFY**, which
exhaustive invalidation alone cannot detect. Reloads are additionally
generation-guarded, and `GET /cache/status` reports `dirty` per registry so a
bumped generation whose data has not been reloaded is visible rather than
hidden. Read that sentence as "no TTL is the freshness mechanism", not as
"no TTL exists".

**Consequence for the "Negative" list above.** The first bullet — "the
performance win is opt-in; a deployment that never flips to `memory` pays
the facade indirection for nothing" — is what this amendment resolves. The
second bullet stands and is now more load-bearing, not less: a new write
path that forgets `invalidate()` is wrong, and the TTL is a backstop, not an
excuse.

## References

- spec.md §7.3 (registry cache layer), §8.7 (cache controls in Settings)
- /home/user/concierge-agent/backend/app/registry_cache.py
- /home/user/concierge-agent/docs/acceptance/18-registry-cache-and-retrieval/
- Related: ADR-0003 (the middlewares that read through it), ADR-0008
  (cross-replica invalidation), ADR-0005 (retrieval over the snapshot)
