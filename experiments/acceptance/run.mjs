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
for (const file of files) {
  const name = path.basename(file, '.mjs')
  const mod = await import(pathToFileURL(path.resolve(file)).href)
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
await browser.close()
process.exit(failed ? 1 : 0)
