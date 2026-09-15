#!/usr/bin/env node
// Run acceptance stages in order:  node run.mjs stages/00-fresh-slate.mjs stages/01-settings-models.mjs …
// Each stage module exports `default async function (ctx)`; ctx carries the page and the lib.
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import * as lib from './lib.mjs'

const files = process.argv.slice(2)
if (!files.length) {
  console.error('usage: node run.mjs <stage.mjs> [more stages…]')
  process.exit(2)
}
const { browser, context, page } = await lib.openBrowser()
let failed = 0
let skipped = 0
for (const file of files) {
  const name = path.basename(file, '.mjs')
  const mod = await import(pathToFileURL(path.resolve(file)).href)
  // Some stages are only meaningful under a prod/*.sh wrapper that builds
  // their world first — A2A counterparty stubs, AUTH_ENABLED=1 and its
  // bootstrap passwords, a `demo-stub` MCP server. Run bare from
  // `node run.mjs stages/*.mjs` they fail on a missing precondition and read
  // like product defects; a whole campaign was once triaged before anyone
  // noticed four of its red stages had never been runnable that way. A stage
  // that needs a wrapper says so by exporting `requires`, and a bare run
  // skips it by name instead of failing it.
  if (Array.isArray(mod.requires) && mod.requires.length) {
    const missing = mod.requires.filter((r) => !process.env[r.env])
    if (missing.length) {
      skipped += 1
      lib.stageStart(name)
      lib.log(
        `SKIPPED — needs ${missing.map((m) => `${m.env} (${m.why})`).join('; ')}. ` +
          `Run it through ${mod.driver || 'its prod/ driver'}.`,
      )
      lib.stageEnd()
      continue
    }
  }
  lib.stageStart(name)
  try {
    await mod.default({ page, context, browser, ...lib })
  } catch (err) {
    failed += 1
    lib.log(`STAGE FAILED: ${err?.stack || err}`)
    try {
      await lib.shot(page, 'zz-failure')
    } catch {}
  } finally {
    lib.stageEnd()
  }
}
if (skipped) lib.log(`${skipped} stage(s) skipped for missing preconditions — see the SKIPPED lines above`)
await browser.close()
process.exit(failed ? 1 : 0)
