#!/usr/bin/env bash
# The performance record: the M49 load scenarios (api, runs-scale, chat,
# sse) re-run through the load harness against the stack that is up. The
# chat scenario needs a live model on the backend. ACC_OUT sets the output
# dir; ACC_LABEL the record's label. Output: transcript on stdout + JSON/MD.
. "$(dirname "${BASH_SOURCE[0]}")/common.sh"
OUT=${ACC_OUT:-$ACC_HERE/out}; mkdir -p "$OUT"
LABEL=${ACC_LABEL:-acceptance-v1}
cd "$ACC_ROOT/backend" || exit 1
PY=${ACC_PYTHON:-.venv/bin/python}
echo "# performance record — $(date -u +%FT%TZ) — base $ACC_BASE (through the frontend proxy) — label $LABEL"
"$PY" ../experiments/load/harness.py --base-url "$ACC_BASE" --database-url "$ACC_DATABASE_URL" \
  --scenarios api,runs-scale,chat,sse --api-requests 100 --api-concurrency 10 \
  --chat-concurrency 5,10,25 --chat-deadline 180 --label "$LABEL" --out "$OUT/perf-$LABEL.json" 2>&1 | tail -40
echo; cat "$OUT/perf-$LABEL.md"
echo "# end — $(date -u +%FT%TZ)"
