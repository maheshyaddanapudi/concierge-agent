#!/usr/bin/env node
// Publish captured stage evidence into the repo's evidence tree:
//   node publish.mjs [stage …]        (default: every stage dir under ACC_SHOTS)
// For each stage, docs/acceptance/<stage>/ is replaced wholesale by the
// captured frames plus transcript.md — old frames never linger next to new
// ones. Failure frames (zz-failure.png) are never published.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const SHOTS = process.env.ACC_SHOTS || path.join(here, 'shots')
const DEST = process.env.ACC_DEST || path.resolve(here, '../../docs/acceptance')
const stages = process.argv.slice(2).length
  ? process.argv.slice(2)
  : fs.readdirSync(SHOTS).filter((d) => fs.statSync(path.join(SHOTS, d)).isDirectory()).sort()

for (const stage of stages) {
  const src = path.join(SHOTS, stage)
  if (!fs.existsSync(src)) {
    console.error(`skip ${stage}: no captured dir at ${src}`)
    continue
  }
  const files = fs.readdirSync(src).filter((f) => (f.endsWith('.png') && f !== 'zz-failure.png') || f === 'transcript.md')
  if (fs.existsSync(path.join(src, 'zz-failure.png'))) {
    console.error(`skip ${stage}: it has a zz-failure.png — the stage did not pass`)
    continue
  }
  const dst = path.join(DEST, stage)
  fs.rmSync(dst, { recursive: true, force: true })
  fs.mkdirSync(dst, { recursive: true })
  for (const f of files) fs.copyFileSync(path.join(src, f), path.join(dst, f))
  const frames = files.filter((f) => f.endsWith('.png')).length
  console.log(`${stage}: ${frames} frames${files.includes('transcript.md') ? ' + transcript' : ''} → ${path.relative(process.cwd(), dst)}`)
}
