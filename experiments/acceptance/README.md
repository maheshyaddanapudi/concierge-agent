# Acceptance drivers (spec §14)

Click-driven Playwright stages that produce the evidence under `docs/acceptance/`.
Each stage is one module in `stages/`, exporting `default async (ctx)`; the
runner opens one browser, runs the stages you name in order, and writes
numbered frames plus a `transcript.md` per stage under `ACC_SHOTS/<stage>/`.

```bash
cd experiments/acceptance && npm install          # Playwright (its Chromium: npx playwright install chromium)
export ACC_BASE=http://localhost:5173             # the frontend; the API is ${ACC_BASE}/api/v1 unless ACC_API is set
export ACC_SHOTS=../../docs/acceptance/out        # where frames land
export ACC_MODEL=openrouter:qwen/qwen3.8-max      # the live model every stage uses (keys stay in the stack's env)
node run.mjs stages/00-fresh-slate.mjs stages/01-settings-models.mjs
```

Stages assume a **fresh** stack (`docker compose down -v && docker compose up -d`)
for `00-fresh-slate` and carry state forward in order, the way the spec's script
does. `ACC_CHROMIUM` points at a system Chromium when Playwright's download is
not wanted. Nothing here reads a key or knows about a deployment; the stack's
own environment does.
