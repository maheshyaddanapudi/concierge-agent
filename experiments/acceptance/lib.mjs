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

// ── assertions ────────────────────────────────────────────────────────
//
// A stage that only LOGS its outcome proves nothing: the runner exits 0, the
// frames get published, and a run that failed or a gate that never armed
// reads as a pass. Everything below THROWS, which the runner turns into a
// `zz-failure.png` and a non-zero exit — and `publish.mjs` refuses to
// publish a stage that has one.

export class AcceptanceFailure extends Error {
  constructor(message) {
    super(message)
    this.name = 'AcceptanceFailure'
  }
}

/** The base assertion: everything else is sugar over it. */
export function expect(condition, message) {
  if (!condition) {
    log(`ASSERTION FAILED: ${message}`)
    throw new AcceptanceFailure(message)
  }
  log(`ok — ${message}`)
  return true
}

export function expectEq(actual, wanted, what) {
  return expect(actual === wanted, `${what}: ${JSON.stringify(actual)} === ${JSON.stringify(wanted)}`)
}

export function expectOneOf(actual, wanted, what) {
  return expect(wanted.includes(actual), `${what}: ${JSON.stringify(actual)} ∈ ${JSON.stringify(wanted)}`)
}

export function expectMatch(text, pattern, what) {
  const re = pattern instanceof RegExp ? pattern : new RegExp(pattern, 'i')
  return expect(re.test(String(text ?? '')), `${what} matches ${re} (got ${JSON.stringify(String(text ?? '').slice(0, 200))})`)
}

/** A run reached the status the stage exists to demonstrate. */
export function expectStatus(r, wanted = 'completed', what = 'run') {
  const statuses = Array.isArray(wanted) ? wanted : [wanted]
  const got = r?.status
  if (!statuses.includes(got)) {
    const why = (r?.error || r?.final_answer || '').toString().replace(/\s+/g, ' ').slice(0, 200)
    log(`ASSERTION FAILED: ${what} ${r?.id?.slice?.(0, 8) ?? '?'} → ${got}, wanted ${statuses.join('|')}`)
    throw new AcceptanceFailure(`${what} ${r?.id ?? '?'} → ${got} (wanted ${statuses.join('|')})${why ? `: ${why}` : ''}`)
  }
  log(`ok — ${what} ${r?.id?.slice?.(0, 8) ?? ''} → ${got}`)
  return r
}

/** An API call returned the status code the stage is about. */
export function expectHttp(res, wanted, what) {
  const codes = Array.isArray(wanted) ? wanted : [wanted]
  if (!codes.includes(res?.status)) {
    const body = JSON.stringify(res?.json ?? null).slice(0, 300)
    log(`ASSERTION FAILED: ${what} → HTTP ${res?.status}, wanted ${codes.join('|')}`)
    throw new AcceptanceFailure(`${what} → HTTP ${res?.status} (wanted ${codes.join('|')}): ${body}`)
  }
  log(`ok — ${what} → HTTP ${res.status}`)
  return res
}

/** A locator the stage claims the UI shows. */
export async function expectVisible(page, locator, what, timeout = 30000) {
  const target = typeof locator === 'string' ? page.locator(locator) : locator
  try {
    await target.first().waitFor({ state: 'visible', timeout })
  } catch {
    log(`ASSERTION FAILED: ${what} never appeared within ${timeout}ms`)
    throw new AcceptanceFailure(`${what} never appeared within ${timeout}ms`)
  }
  log(`ok — ${what} is on screen`)
  return true
}

/** Some step of the run is of this type (the trace the stage screenshots). */
export function expectStep(r, pattern, what = 'step') {
  const re = pattern instanceof RegExp ? pattern : new RegExp(pattern, 'i')
  const found = (r?.steps || []).some((s) => re.test(`${s.step_type}:${s.node_id || ''}`))
  return expect(found, `${what} — a step matching ${re} is in the trace (${steps(r)})`)
}

// ── transcript ────────────────────────────────────────────────────────
let current = null
export function stageStart(name) {
  const dir = path.join(SHOTS, name)
  // clear before capturing: the directory used to be created and never
  // emptied, so a stage whose frame names carry run-dependent values (35
  // puts the schema version in each filename) accumulated frames across
  // re-runs and publish copied all of them — that is where the eight stale
  // PNGs in the published stage-35 tree came from. A stage owns its capture
  // directory; the previous run's frames are not evidence for this one.
  fs.rmSync(dir, { recursive: true, force: true })
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

/** The stub MCP server a stage needs, registered if it is not already there.
 *
 * Several stages and prod drills open with "the SEEDED `demo-stub` server" —
 * but nothing in this repository has ever seeded one. `git log -S demo-stub --
 * backend/` is empty at every commit: the name lives only in
 * experiments/acceptance and docs. Those stages could not pass on a stack
 * built from this tree, and their published frames came from a fixture the
 * tree cannot reproduce. Rather than assert a precondition nobody creates,
 * a stage now makes its own, from the stub the repo DOES ship
 * (backend/tests/stub_mcp_server.py — echo, add, mutate_toolset,
 * mutate_schema, die), at the container path the compose stack uses.
 */
export async function ensureStubServer(name = 'demo-stub') {
  const existing = (await get('/mcp-servers')).json.find((s) => s.name === name)
  if (existing) return existing
  const r = await post('/mcp-servers', {
    name,
    description: `the acceptance stub server: echo, add, mutate_toolset, mutate_schema, die — registered by the ${name} stage`,
    transport: 'stdio',
    command: 'python',
    args: ['/app/tests/stub_mcp_server.py'],
  })
  if (r.status >= 300) throw new Error(`could not register ${name}: ${r.status} ${JSON.stringify(r.json)}`)
  log(`registered the ${name} stub server (nothing seeds it — see ensureStubServer)`)
  await new Promise((res) => setTimeout(res, 3000))
  return (await get('/mcp-servers')).json.find((s) => s.name === name)
}

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
  // a timeout is a FAILED wait, not a result: resolving here is what let a
  // stage log "still running" and carry on asserting nothing
  log(`ASSERTION FAILED: run ${runId} still ${r?.status} after ${timeoutS}s`)
  throw new AcceptanceFailure(
    `run ${runId} did not reach ${statuses.join('|')} within ${timeoutS}s (still ${r?.status})`,
  )
}

/**
 * The same wait, for a stage that is deliberately checking a run does NOT
 * settle inside a window (it is parked on a gate, or stopped). Returns the
 * run either way, never throws on the timeout.
 */
export async function pollRun(runId, statuses = ['completed', 'failed', 'cancelled'], timeoutS = 30) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeoutS * 1000) {
    const r = await run(runId)
    if (r && statuses.includes(r.status)) return r
    await sleep(1000)
  }
  return await run(runId)
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
  // a hash change is an in-app navigation — the query cache would keep
  // settings written through the API stale; reload so every frame shows
  // the server's current state
  await page.reload()
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
 *
 * The budget covers a chain, not one request: the overlap judge's live call,
 * the operator's "Save anyway", then the actual POST and its rendered result.
 * The former 30s was cut to Qwen's latency and is not a property of the
 * system under test — on a slower default model the judge alone spent ~8s,
 * the chain overran, and stages reported `timeout` for saves the backend had
 * in fact refused correctly (422, naming the offending mention). A harness
 * that reports the model's speed as the product's verdict is measuring the
 * wrong thing, so the budget is now generous enough to outlast the slowest
 * model we point this at. Stages that mean to assert latency time it
 * themselves rather than reading it off this timeout.
 */
export async function submitSave(page, buttonName, { timeoutMs = 120000, acceptOverlap = true, onOverlap } = {}) {
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
  const btn = page.getByRole('button', { name: '+ New conversation' })
  // an explicit branch, not a swallowed click: on the chat home with no
  // conversations yet the composer IS a fresh conversation and the button
  // is not rendered
  if (await btn.count()) await btn.first().click()
  else log('no "+ New conversation" button — the empty chat home is already a fresh conversation')
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
  if (!r?.id) throw new AcceptanceFailure(`no run appeared after sending: ${text.slice(0, 80)}`)
  if (approve) {
    const gate = page.getByText('HUMAN APPROVAL REQUIRED').first()
    const armed = await Promise.race([
      // both halves are deliberate PROBES — "did a gate arm before the run
      // settled?" — so neither may throw. pollRun, not waitRun: a run that
      // is still going after gateWaitS is the answer, not a failure.
      gate.waitFor({ timeout: gateWaitS * 1000 }).then(() => true).catch(() => false),
      pollRun(r.id, ['completed', 'failed', 'cancelled'], gateWaitS).then((x) => (x && ['completed', 'failed', 'cancelled'].includes(x.status) ? false : null)),
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
