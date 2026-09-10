# §14q-95 — recall latency from 10k to 1M embeddings

The M49 load harness's `recall` scenario on the shipped stack (one replica,
`shm_size: 1gb`, the fake provider's 64-dimension embeddings under
`fake:scripted@64`): it seeds `loadgen` memories and vectors to each size,
times `GET /memories/recall?k=6` at concurrency 1 and 5 (40 requests each),
and `EXPLAIN`s both legs of the ranking query. The decay and contradiction
sweeps were gated off for the run because the seeded rows are up to 694 days
stale and a tick would have expired them under the measurement.

## The numbers (from `recall.json`)

| active memories | c=1 p50 | c=1 p95 | c=5 p50 | c=5 p95 | errors | lexical leg (one query, `EXPLAIN ANALYZE`) | vector leg (plan cost) |
|---|---|---|---|---|---|---|---|
| 10,000 | 49 ms | 107 ms | 101 ms | 207 ms | 0 | 33 ms | 274 |
| 100,000 | 209 ms | 406 ms | 1,009 ms | 1,383 ms | 0 | 184 ms over 37,500 matching rows | 249 |
| 1,000,000 | 1,221 ms | 3,953 ms | 6,670 ms | 19,616 ms | 0 | 1,292 ms over 375,000 matching rows | 277 |

The **vector leg is flat**: its plan is `Index Scan on memory_embeddings`
(the `emb_64` HNSW index) with a cost that does not move between 10k and 1M
(274 / 249 / 277). The **endpoint is not**: recall's other leg ranks every
row that matches any query term with `ts_rank_cd`, and on this synthetic
corpus (eight topic words, three of them in every query) that is 37.5% of the
table — 375,000 rows at a million. At 1M the lexical leg alone is 1.29 s and
the endpoint's p50 is 1.22 s: the endpoint's latency at scale *is* the
lexical leg's. At concurrency 5 the ranking scans contend for the four
shared cores (p95 19.6 s). Real corpora match far fewer rows per query;
the shape is the same.

Seeding: the bulk HNSW build for the last 900k vectors took **3,591 s** (two
parallel workers on four shared cores, `maintenance_work_mem = 2GB`); the
database container peaked at ~860 MiB during it. Table sizes at 1M:
`memories` 575 MB, `memory_embeddings` 997 MB, the `emb_64` index 543 MB.
Cleanup of a million memories with the new self-reference indexes: 36 s.

## Transcript

```
# M54 recall drill — 2026-09-09T23:42:44Z — base http://localhost:8000 — sizes 10000,100000,1000000
$ psql: the typed column and its HNSW index
memory_embeddings_emb_1024_hnsw|CREATE INDEX memory_embeddings_emb_1024_hnsw ON public.memory_embeddings USING hnsw (emb_1024 vector_cosine_ops)
memory_embeddings_emb_1536_hnsw|CREATE INDEX memory_embeddings_emb_1536_hnsw ON public.memory_embeddings USING hnsw (emb_1536 vector_cosine_ops)
memory_embeddings_emb_256_hnsw|CREATE INDEX memory_embeddings_emb_256_hnsw ON public.memory_embeddings USING hnsw (emb_256 vector_cosine_ops)
memory_embeddings_emb_3072_hnsw|CREATE INDEX memory_embeddings_emb_3072_hnsw ON public.memory_embeddings USING hnsw (emb_3072 halfvec_cosine_ops)
memory_embeddings_emb_384_hnsw|CREATE INDEX memory_embeddings_emb_384_hnsw ON public.memory_embeddings USING hnsw (emb_384 vector_cosine_ops)
memory_embeddings_emb_512_hnsw|CREATE INDEX memory_embeddings_emb_512_hnsw ON public.memory_embeddings USING hnsw (emb_512 vector_cosine_ops)
memory_embeddings_emb_64_hnsw|CREATE INDEX memory_embeddings_emb_64_hnsw ON public.memory_embeddings USING hnsw (emb_64 vector_cosine_ops)
memory_embeddings_emb_768_hnsw|CREATE INDEX memory_embeddings_emb_768_hnsw ON public.memory_embeddings USING hnsw (emb_768 vector_cosine_ops)
$ PATCH /settings: decay and contradiction sweeps off for the drill — the seeded rows are up to 694 days stale, so a tick would expire them under the measurement
{'memory_decay_enabled': False, 'memory_contradiction_enabled': False}
$ harness.py --scenarios recall --recall-sizes 10000,100000,1000000 (seeds loadgen memories + vectors, times /memories/recall at concurrency 1 and 5, EXPLAINs the vector leg)
[23:42:45] at rest: {'connections': {'total': 7, 'idle': 7}, 'max_connections': 100}
[23:42:45] ── scenario recall ──
[23:43:02] recall 10000 active memories: lexical leg {'execution_ms': 32.5, 'index_matches': 0, 'wall_ms': 36.2}
[23:43:02] recall 10000 active memories: c1 p50 48.56 ms, c5 p95 207.16 ms, plan {'node': 'Limit', 'total_cost': 273.58, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
[23:43:09] recall seed: 90000 vectors to add — dropping the emb_64 HNSW index for a bulk build
[23:44:01] recall seed: emb_64 HNSW index rebuilt in 51.3 s
[23:44:19] recall 100000 active memories: lexical leg {'execution_ms': 184.0, 'index_matches': 37500, 'wall_ms': 186.3}
[23:44:19] recall 100000 active memories: c1 p50 208.74 ms, c5 p95 1382.61 ms, plan {'node': 'Limit', 'total_cost': 249.37, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
[23:45:13] recall seed: 900000 vectors to add — dropping the emb_64 HNSW index for a bulk build
[00:45:19] recall seed: emb_64 HNSW index rebuilt in 3590.7 s
[00:47:51] recall 1000000 active memories: lexical leg {'execution_ms': 1292.1, 'index_matches': 375000, 'wall_ms': 1295.9}
[00:47:51] recall 1000000 active memories: c1 p50 1221.26 ms, c5 p95 19615.85 ms, plan {'node': 'Limit', 'total_cost': 277.33, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
[00:48:27] cleanup: {'memory_embeddings': 'DELETE 1000000', 'memories': 'DELETE 1000000', 'run_steps': 'DELETE 0', 'runs': 'DELETE 0', 'conversations': 'DELETE 0'}
[00:48:27] restoring settings: ['embedding_model', 'memory_enabled']
[00:48:27] wrote /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/recall.json and /tmp/claude-0/-home-user-concierge-agent/42b28fd8-c8ea-5ded-b71d-aa8262ee5dbc/scratchpad/m54-out/recall.md
harness took 3943 s
$ recall.md (the harness's tables)
# Load baseline — m54-recall
Captured 2026-09-09T23:42:45+00:00 at commit `34c38ba` against `http://localhost:8000`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 7.
## Memory recall by corpus size
| active memories | c=1 p50 ms | c=1 p95 ms | c=5 p95 ms | vector leg plan |
|---|---|---|---|---|
| 10000 | 48.56 | 107.15 | 207.16 | ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |
| 100000 | 208.74 | 405.86 | 1382.61 | ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |
| 1000000 | 1221.26 | 3952.5 | 19615.85 | ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings'] |
$ the vector-leg plans the harness captured at each level (recall.json)
  memories=10000 vectors=10000 c1 see the table above errors=0 | c5 see the table above errors=0 | plan={'node': 'Limit', 'total_cost': 273.58, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
  memories=100000 vectors=100000 c1 see the table above errors=0 | c5 see the table above errors=0 | plan={'node': 'Limit', 'total_cost': 249.37, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
  memories=1000000 vectors=1000000 c1 see the table above errors=0 | c5 see the table above errors=0 | plan={'node': 'Limit', 'total_cost': 277.33, 'scans': ['Index Scan on memories', 'Index Scan on memory_embeddings', 'Seq Scan on memory_embeddings']}
$ psql: table and index sizes after the drill
            relname            | pg_size_pretty 
-------------------------------+----------------
 memories                      | 575 MB
 memory_embeddings             | 997 MB
 memory_embeddings_emb_64_hnsw | 543 MB
(3 rows)
# end — 2026-09-10T00:48:27Z
recall exit 0
```
