// Stage 18 — registry cache and retrieval (spec §7.3 / §8.7): the cache
// status in bypass and memory modes, runs in both orchestrator modes under
// each cache mode, the generation bumping on a registry write and on a
// Tools-page exposure toggle, the operator refresh, and top-K retrieval
// switched on with threshold 1 / top-K 1 so the planner's catalog is
// actually truncated for a run (corroborated from the backend log when the
// container is reachable).
import { execSync } from 'node:child_process'

const ASK = 'Add 40 and 2 with the sitefiles add tool and answer with the number only.'
const CONTAINER = process.env.ACC_BACKEND_CONTAINER || 'concierge-agent-backend-1'

async function setInt(page, label, value, key, { settings, get, log }) {
  const input = page.getByLabel(label).first()
  await input.scrollIntoViewIfNeeded()
  await input.fill(String(value))
  await input.press('Enter')
  await input.blur()
  await page.waitForTimeout(900)
  const now = (await get('/settings')).json[key]
  if (now !== value) {
    log(`${label}: the field did not commit (${now}) — set through the API`)
    await settings({ [key]: value })
  }
}

async function quickRun(page, ctx, mode) {
  const { settings, get, sendChat, waitRun, steps, log, nav } = ctx
  await settings({ orchestrator_mode: mode })
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, ASK)
  await page.waitForTimeout(2000)
  const r = (await get('/runs?limit=1')).json[0]
  const gate = page.getByText('HUMAN APPROVAL REQUIRED').first()
  const armed = await Promise.race([
    gate.waitFor({ timeout: 40000 }).then(() => true).catch(() => false),
    waitRun(r.id, ['completed', 'failed', 'cancelled'], 40).then(() => false).catch(() => false),
  ])
  if (armed) await page.getByRole('button', { name: /✓ Approve/ }).first().click()
  const done = await waitRun(r.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1200)
  log(`${mode} run → ${done.status}; answer: ${(done.final_answer || '').slice(0, 80)}; steps: ${steps(done)}`)
  return done
}

export default async function (ctx) {
  const { page, nav, shot, settings, get, post, log } = ctx
  const initial = (await get('/settings')).json
  const status = async () => (await get('/cache/status')).json
  const gens = (s) => Object.entries(s.registries).map(([k, v]) => `${k}:g${v.generation}${v.records != null ? '/' + v.records : ''}`).join(' ')
  const cacheSection = async () => {
    await nav(page, 'settings')
    await page.getByText('Registry cache', { exact: true }).first().scrollIntoViewIfNeeded()
    await page.waitForTimeout(600)
  }

  // bypass, then memory
  await settings({ registry_cache_mode: 'bypass', default_model_params: null })
  await cacheSection()
  log(`bypass: ${(await status()).mode} ${gens(await status())}`)
  await shot(page, '00-cache-bypass-status')
  await page.getByRole('button', { name: 'memory', exact: true }).first().click()
  await page.waitForTimeout(1500)
  const mem = await status()
  log(`memory: ${mem.mode} ${gens(mem)}`)
  await shot(page, '01-cache-memory-live')

  await quickRun(page, ctx, 'graph')
  await shot(page, '02-graph-run-memory-mode')
  await quickRun(page, ctx, 'agentic')
  await shot(page, '03-agentic-run-memory-mode')

  // a registry write bumps the skills generation
  const skills = (await get('/skills')).json
  const notes = skills.find((s) => s.name === 'notes-formatter')
  const g0 = (await status()).registries.skills.generation
  await ctx.patch(`/skills/${notes.id}`, { description: notes.description + ' (cache drill)' })
  await page.waitForTimeout(800)
  const g1 = (await status()).registries.skills.generation
  log(`skills generation after a write: ${g0} → ${g1}`)
  await cacheSection()
  await shot(page, '04-generation-bumped')
  await page.getByRole('button', { name: /Refresh all caches/ }).first().click()
  await page.waitForTimeout(1500)
  log(`after refresh-all: ${gens(await status())}`)
  await shot(page, '05-refresh-all')

  // retrieval on with threshold 1 / top-K 1
  const sw = page.getByRole('switch', { name: 'Top-K retrieval' }).first()
  await sw.scrollIntoViewIfNeeded()
  if ((await sw.getAttribute('aria-checked')) !== 'true') await sw.click()
  await page.waitForTimeout(600)
  await setInt(page, 'Threshold', 1, 'retrieval_threshold', ctx)
  await setInt(page, 'Top K', 1, 'retrieval_top_k', ctx)
  const rs = (await get('/settings')).json
  log(`retrieval: enabled=${rs.retrieval_enabled} threshold=${rs.retrieval_threshold} top_k=${rs.retrieval_top_k} embedding_model=${rs.embedding_model}`)
  await page.getByText('Retrieval (progressive disclosure)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '06-retrieval-enabled')
  await quickRun(page, ctx, 'graph')
  await shot(page, '07-run-with-retrieval-active')
  try {
    const line = execSync(`docker logs --since 3m ${CONTAINER} 2>&1 | grep -a retrieval_truncated_catalog | tail -n 2`, { encoding: 'utf8' }).trim()
    log(line ? `backend log: ${line.slice(0, 400)}` : 'backend log: no retrieval_truncated_catalog line in the last 3 minutes')
  } catch {
    log('backend log not reachable from this host — retrieval truncation not corroborated here')
  }
  await settings({ retrieval_enabled: initial.retrieval_enabled, retrieval_threshold: initial.retrieval_threshold, retrieval_top_k: initial.retrieval_top_k })

  // back to bypass, then memory again for the Tools-page header and a toggle bump
  await cacheSection()
  await page.getByRole('button', { name: 'bypass', exact: true }).first().click()
  await page.waitForTimeout(1200)
  await shot(page, '08-back-to-bypass')
  await page.getByRole('button', { name: 'memory', exact: true }).first().click()
  await page.waitForTimeout(1200)
  await nav(page, 'tools')
  const header = page.getByText(/cache: memory/i).first()
  await header.waitFor({ timeout: 10000 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForTimeout(300)
  log(`tools header: ${(await header.textContent()).trim()}`)
  await shot(page, '09-tools-cache-header-memory')
  const gt0 = (await status()).registries.tools.generation
  await page.getByPlaceholder('Search…').fill('sitefiles.add')
  await page.waitForTimeout(600)
  // the exposure toggle lives in the tool's drawer
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(800)
  const drawer = page.locator('.fixed.inset-0').last()
  const exposeSwitch = drawer.getByRole('switch').first()
  await exposeSwitch.click()
  await page.waitForTimeout(1200)
  await ctx.closeDrawer(page)
  const gt1 = (await status()).registries.tools.generation
  // the header polls; reload so the bumped generation is the one in frame
  await nav(page, 'tools')
  await page.getByPlaceholder('Search…').fill('sitefiles.add')
  await page.waitForTimeout(600)
  await page.evaluate(() => window.scrollTo(0, 0))
  log(`tools generation after the exposure toggle: ${gt0} → ${gt1}; header: ${(await page.getByText(/cache: memory/i).first().textContent()).trim()}`)
  await shot(page, '10-generation-bumped-after-toggle')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(800)
  await page.locator('.fixed.inset-0').last().getByRole('switch').first().click()
  await page.waitForTimeout(800)
  await ctx.closeDrawer(page)
  await page.getByPlaceholder('Search…').fill('')

  // runs under bypass
  await settings({ registry_cache_mode: 'bypass' })
  await quickRun(page, ctx, 'graph')
  await shot(page, '11-bypass-graph-run')
  await quickRun(page, ctx, 'agentic')
  await shot(page, '12-bypass-agentic-run')

  // redis (shared backend) when the stack runs one
  await cacheSection()
  await page.getByRole('button', { name: 'redis', exact: true }).first().click()
  await page.waitForTimeout(1500)
  const rd = await status()
  const err = await page.locator('.bg-rose-500\\/10').first().textContent({ timeout: 1500 }).catch(() => '')
  log(`redis: mode=${rd.mode} ${gens(rd)}${err ? ' — ' + String(err).trim().slice(0, 120) : ''}`)
  await shot(page, '13-cache-redis-status')

  await settings({ registry_cache_mode: initial.registry_cache_mode, orchestrator_mode: 'graph' })
  log(`restored registry_cache_mode=${initial.registry_cache_mode}`)
}
