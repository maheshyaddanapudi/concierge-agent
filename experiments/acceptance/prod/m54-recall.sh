#!/usr/bin/env bash
# M54 §14q-95: memory recall latency at 10k → 100k → 1M embeddings on the
# typed HNSW column, with the vector leg's query plan, through the load
# harness's `recall` scenario (fake 64-dim vectors under fake:scripted@64 —
# boot the backend with FAKE_LLM_ENABLED=1). SIZES overrides the ladder;
# ACC_OUT the output dir. Output: transcript on stdout + JSON/MD.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
OUT=${ACC_OUT:-$ACC_HERE/out}; mkdir -p "$OUT"
SIZES=${SIZES:-10000,100000,1000000}
BASE=${API%/api/v1}
cd "$ACC_ROOT/backend" || exit 1
PY=${ACC_PYTHON:-.venv/bin/python}

echo "# M54 recall drill — $(date -u +%FT%TZ) — base $BASE — sizes $SIZES"
say "psql: the typed column and its HNSW index"
psql_ "select indexname, indexdef from pg_indexes where tablename='memory_embeddings' and indexname like '%hnsw%' order by 1" | head -8
say "PATCH /settings: decay and contradiction sweeps off for the drill — seeded rows are up to 694 days stale, so a tick would expire them under the measurement"
curl -s -X PATCH $API/settings -H "$H" -d '{"memory_decay_enabled":false,"memory_contradiction_enabled":false}' | py 'print({k:d[k] for k in ("memory_decay_enabled","memory_contradiction_enabled")})'
say "harness.py --scenarios recall --recall-sizes $SIZES (seeds loadgen memories + vectors, times /memories/recall at concurrency 1 and 5, EXPLAINs the vector leg)"
T0=$(date +%s)
"$PY" ../experiments/load/harness.py \
  --base-url "$BASE" \
  --database-url "$ACC_DATABASE_URL" \
  --scenarios recall --recall-sizes "$SIZES" --recall-requests 40 \
  --label m54-recall --out "$OUT/recall.json" 2>&1 | tail -40
echo "harness took $(( $(date +%s) - T0 )) s"
say "recall.md (the harness's tables)"
sed -n '/recall/,$p' "$OUT/recall.md" 2>/dev/null | head -60
say "the vector-leg plans the harness captured at each level (recall.json)"
python3 - "$OUT/recall.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
rec = d.get("scenarios", d).get("recall") if isinstance(d.get("scenarios", d), dict) else None
rec = rec or d.get("recall") or {}
for lvl in rec.get("levels", []):
    c1, c5 = lvl.get("concurrency_1", {}), lvl.get("concurrency_5", {})
    print(f"  memories={lvl.get('loadgen_memories')} vectors={lvl.get('fake_vectors')} "
          f"c1 p50={c1.get('p50')} p95={c1.get('p95')} errors={c1.get('errors')} | "
          f"c5 p50={c5.get('p50')} p95={c5.get('p95')} errors={c5.get('errors')} | plan={lvl.get('vector_leg_plan')}")
PY
say "psql: table and index sizes after the drill"
docker exec "$ACC_DB_CONTAINER" psql -U "$ACC_DB_USER" -d "$ACC_DB_NAME" -c "select relname, pg_size_pretty(pg_total_relation_size(oid)) from pg_class where relname in ('memory_embeddings','memories','memory_embeddings_emb_64_hnsw') order by 1"
curl -s -X PATCH $API/settings -H "$H" -d '{"memory_decay_enabled":true,"memory_contradiction_enabled":true}' -o /dev/null
echo "# end — $(date -u +%FT%TZ)"
