#!/usr/bin/env node
// Screenshot one admin page:  node shot.mjs <name> <route> [conversation-title-pattern]
// Environment: ACC_BASE (frontend), ACC_SHOTS (output dir), ACC_CHROMIUM (browser binary).
// For the chat route the newest conversation (or the one matching the
// pattern) is opened first so the transcript is in frame.
import fs from 'node:fs'
import { chromium } from 'playwright'

const [name, route = '', pick] = process.argv.slice(2)
if (!name) {
  console.error('usage: node shot.mjs <name> <route> [pattern]')
  process.exit(2)
}
const BASE = process.env.ACC_BASE || 'http://localhost:5174'
const SHOTS = process.env.ACC_SHOTS || '.'
fs.mkdirSync(SHOTS, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.ACC_CHROMIUM || undefined })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto(`${BASE}/#/${route === 'chat' ? '' : route}`)
await page.waitForTimeout(2500)
if (route === 'chat') {
  const first = page.locator('button').filter({ hasText: pick ? new RegExp(pick, 'i') : /runs · /i }).first()
  if (await first.count()) {
    await first.click()
    await page.waitForTimeout(2500)
  }
}
await page.screenshot({ path: `${SHOTS}/${name}.png` })
await browser.close()
console.log(`shot ${name}.png`)
