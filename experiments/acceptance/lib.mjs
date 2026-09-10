// Acceptance drivers — the shared library (spec §14, campaign acceptance_v1).
//
// Everything a stage needs: a browser at the admin UI, the shipped API, numbered
// screenshots, run waits, and a transcript. Configured by environment only:
//
//   ACC_BASE      frontend origin            default http://localhost:5173
//   ACC_API       API prefix                 default ${ACC_BASE}/api/v1
//   ACC_SHOTS     evidence root              default ./out
//   ACC_MODEL     default model for stages   default openrouter:qwen/qwen3.8-max
//   ACC_CHROMIUM  chromium executable path   default: Playwright's own
//   ACC_THEME     theme to set before frames default: leave as is
//
// Nothing here knows about a sandbox, a proxy or a key file.
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

export const BASE = process.env.ACC_BASE || 'http://localhost:5173'
export const API = process.env.ACC_API || `${BASE}/api/v1`
export const SHOTS = process.env.ACC_SHOTS || './out'
export const MODEL = process.env.ACC_MODEL || 'openrouter:qwen/qwen3.8-max'
export const VIEWPORT = { width: 1440, height: 900 }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
export { sleep }

// ── transcript ────────────────────────────────────────────────────────
let current = null
export function stageStart(name) {
  const dir = path.join(SHOTS, name)
  fs.mkdirSync(dir, { recursive: true })
  current = { name, dir, lines: [], t0: Date.now(), n: 0 }
  log(`# ${name} — ${new Date().toISOString()}`)
  return current
}
export function log(line) {
  const t = current ? ((Date.now() - current.t0) / 1000).toFixed(1).padStart(6) : '      '
  const text = `[${t}s] ${line}`
  console.log(text)
  if (current) current.lines.push(text)
}
export function stageEnd() {
  if (!current) return
  log(`# end — ${new Date().toISOString()}`)
  fs.writeFileSync(path.join(current.dir, 'transcript.md'), '```\n' + current.lines.join('\n') + '\n```\n')
  current = null
}

// ── API ───────────────────────────────────────────────────────────────
export async function api(method, route, body, headers = {}) {
  const res = await fetch(`${API}${route}`, {
    method,
    headers: {
      'content-type': 'application/json',
      // an auth-enabled backend (stage 34): the drill passes the session token
      ...(process.env.ACC_BEARER ? { authorization: `Bearer ${process.env.ACC_BEARER}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = text
  }
  return { status: res.status, json, headers: res.headers }
}
export const get = (route) => api('GET', route)
export const post = (route, body) => api('POST', route, body)
export const patch = (route, body) => api('PATCH', route, body)
export const del = (route) => api('DELETE', route)

export async function settings(update) {
  if (update) {
    const r = await patch('/settings', update)
    if (r.status !== 200) throw new Error(`PATCH /settings ${r.status}: ${JSON.stringify(r.json)}`)
    log(`settings ← ${JSON.stringify(update)}`)
    return r.json
  }
  return (await get('/settings')).json
}

export async function chat(message, conversationId) {
  const r = await post('/chat', conversationId ? { conversation_id: conversationId, message } : { message })
  if (r.status !== 201) throw new Error(`POST /chat ${r.status}: ${JSON.stringify(r.json)}`)
  log(`chat → run ${r.json.run_id}${conversationId ? ' (follow-up)' : ''}`)
  return r.json
}

export async function run(runId) {
  return (await get(`/runs/${runId}`)).json
}

/** Wait until the run's status is one of `statuses` (default: any terminal). */
export async function waitRun(runId, statuses = ['completed', 'failed', 'cancelled'], timeoutS = 300) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutS * 1000) {
    const r = await run(runId)
    if (r && statuses.includes(r.status)) {
      log(`run ${runId} → ${r.status} after ${((Date.now() - t0) / 1000).toFixed(0)}s`)
      return r
    }
    await sleep(1000)
  }
  const r = await run(runId)
  log(`run ${runId} still ${r?.status} after ${timeoutS}s (wait timed out)`)
  return r
}

export function steps(r, n = 16) {
  return (r.steps || []).slice(0, n).map((s) => [s.step_type, s.node_id || '', s.status].join(':')).join(' ')
}

// ── browser ───────────────────────────────────────────────────────────
export async function openBrowser() {
  const opts = process.env.ACC_CHROMIUM ? { executablePath: process.env.ACC_CHROMIUM } : {}
  const browser = await chromium.launch(opts)
  const context = await browser.newContext({ viewport: VIEWPORT })
  const page = await context.newPage()
  page.on('pageerror', (e) => log(`PAGE ERROR: ${e.message}`))
  return { browser, context, page }
}

export async function nav(page, route, settleMs = 1500) {
  await page.goto(`${BASE}/#/${route.replace(/^\//, '')}`)
  await page.waitForTimeout(settleMs)
}

export async function shot(page, name, opts = {}) {
  if (!current) throw new Error('shot() outside a stage')
  const file = path.join(current.dir, `${name}.png`)
  await page.screenshot({ path: file, fullPage: opts.fullPage ?? false })
  log(`shot ${name}.png`)
  return file
}

/** The newest conversation in the Chat sidebar, or one whose title matches. */
export async function openConversation(page, titlePattern) {
  const list = page.locator('button').filter({ hasText: titlePattern ? new RegExp(titlePattern, 'i') : /runs · /i })
  await list.first().click()
  await page.waitForTimeout(1200)
}

export async function sendChat(page, text) {
  const box = page.getByPlaceholder(/Ask the concierge|Type a message/i)
  await box.fill(text)
  await page.getByRole('button', { name: /^Send/ }).click()
  log(`UI send: ${text.slice(0, 80)}`)
}

export async function waitText(page, pattern, timeout = 120000) {
  await page.waitForSelector(`text=${pattern}`, { timeout })
}

export async function click(page, name) {
  await page.getByRole('button', { name }).first().click()
}

/**
 * Click a save button and wait for what the registry does with it: the
 * overlap judge (an LLM call) may raise its dialog, validation may show the
 * error note, or the drawer closes on success. Returns
 * {outcome: 'saved'|'error'|'overlap', text}. With `acceptOverlap` the
 * dialog's "Save anyway" is clicked and the wait continues.
 */
export async function submitSave(page, buttonName, { timeoutMs = 30000, acceptOverlap = true, onOverlap } = {}) {
  await page.getByRole('button', { name: buttonName }).first().click()
  const t0 = Date.now()
  let sawOverlap = false
  while (Date.now() - t0 < timeoutMs) {
    await page.waitForTimeout(400)
    const anyway = page.getByRole('button', { name: /Save anyway/ })
    if (await anyway.count()) {
      sawOverlap = true
      log('overlap judge flagged the save — dialog shown')
      if (onOverlap) await onOverlap()
      if (!acceptOverlap) return { outcome: 'overlap', text: '' }
      await anyway.first().click()
      continue
    }
    const note = page.locator('.bg-rose-500\\/10').first()
    if (await note.count()) {
      const text = ((await note.textContent()) || '').trim()
      log(`save refused → ${text.slice(0, 160)}`)
      return { outcome: 'error', text, sawOverlap }
    }
    if (!(await page.getByRole('button', { name: 'close' }).count())) return { outcome: 'saved', text: '', sawOverlap }
  }
  return { outcome: 'timeout', text: '', sawOverlap }
}

/** Close the open Drawer (its ✕ carries aria-label "close"). */
export async function closeDrawer(page) {
  const btn = page.getByRole('button', { name: 'close' }).first()
  if (await btn.count()) await btn.click()
  await page.waitForTimeout(400)
}

/** The theme is a client preference (localStorage `concierge-theme`). */
export async function setTheme(page, theme) {
  await page.evaluate((t) => localStorage.setItem('concierge-theme', t), theme)
  await page.reload()
  await page.waitForTimeout(1200)
}

/** Start a fresh conversation on the Chat page (already navigated). */
export async function newConversation(page) {
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
}

/**
 * Send a message from the composer, approve a HITL gate if one arms (form
 * gates get their questions answered first via `answerForm`), and wait for
 * the run to settle. Logs the outcome, steps and the answer head.
 */
export async function askAndSettle(page, text, { approve = true, timeoutS = 300, gateWaitS = 45, answerForm = null } = {}) {
  await sendChat(page, text)
  await page.waitForTimeout(2000)
  const r = (await get('/runs?limit=1')).json[0]
  if (approve) {
    const gate = page.getByText('HUMAN APPROVAL REQUIRED').first()
    const armed = await Promise.race([
      gate.waitFor({ timeout: gateWaitS * 1000 }).then(() => true).catch(() => false),
      waitRun(r.id, ['completed', 'failed', 'cancelled'], gateWaitS).then((x) => (x && ['completed', 'failed', 'cancelled'].includes(x.status) ? false : null)),
    ])
    if (armed) {
      if (answerForm) await answerForm(page)
      await page.getByRole('button', { name: /✓ Approve|✓ Submit answers/ }).first().click()
      log('gate approved from the chat card')
    }
  }
  const done = await waitRun(r.id, ['completed', 'failed', 'cancelled'], timeoutS)
  await page.waitForTimeout(1200)
  log(`run ${r.id.slice(0, 8)} → ${done.status}; steps: ${steps(done)}`)
  log(`answer: ${(done.final_answer || '').replace(/\s+/g, ' ').slice(0, 160)}`)
  return done
}
