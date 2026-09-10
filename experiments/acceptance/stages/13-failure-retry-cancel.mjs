// Stage 13 — failure, retry, cancel (spec §14 steps 8/10): a run that must
// admit it cannot do the ask (a file the registered tools cannot read), a
// live run cancelled from the Runs drawer, both fallbacks switched off in
// Settings so an uncovered ask fails for real, the fallbacks restored, the
// failed run retried (re-planned) from its drawer, and the failed row
// deleted.
import { TRIAL_MESSAGE } from './_trial.mjs'

// an ask no registered capability covers and that needs no network to
// answer once the full catalog is offered (the first pass used a hashing
// ask, which sent the fallback worker to the web-fetch tool — unreachable
// from a sandboxed container — so the retry failed on the environment
// rather than on the product)
const UNCOVERED = 'Use the unit-converter capability to convert 37 degrees Celsius to Kelvin and report the value.'

export default async function ({ page, nav, shot, settings, get, log, sendChat, waitRun, steps, closeDrawer, click }) {
  await settings({
    orchestrator_mode: 'graph',
    default_model_params: null,
    orchestrator_full_fallback_enabled: true,
    dynamic_worker_fallback_enabled: true,
  })

  // 1. an honest outcome: the file does not exist and no bound tool can read files
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, 'Summarize the site file does-not-exist.txt from the workspace.')
  await page.waitForTimeout(2000)
  const r0 = (await get('/runs?limit=1')).json[0]
  const gate = page.getByText('HUMAN APPROVAL REQUIRED').first()
  // the site-analyst route may arm its gate — approve so the run settles
  const armed = await gate.waitFor({ timeout: 60000 }).then(() => true).catch(() => false)
  if (armed) {
    await page.getByRole('button', { name: /✓ Approve/ }).first().click()
    log('gate armed on the missing-file ask — approved to let it settle')
  }
  const done0 = await waitRun(r0.id, ['completed', 'failed', 'cancelled'], 300)
  log(`missing-file run → ${done0.status}; steps: ${steps(done0)}`)
  log(`answer: ${(done0.final_answer || '').slice(0, 200)}`)
  await nav(page, 'runs')
  await page.getByPlaceholder('Search…').fill('does-not-exist')
  await page.waitForTimeout(800)
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await shot(page, '00-missing-file-outcome')
  await closeDrawer(page)
  await page.getByPlaceholder('Search…').fill('')

  // 2. a live run cancelled from the Runs drawer
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(1500)
  const r1 = (await get('/runs?limit=1')).json[0]
  await nav(page, 'runs', 800)
  await page.locator('table tbody tr').first().click()
  await page.getByRole('button', { name: 'Cancel run' }).waitFor({ timeout: 20000 })
  await click(page, 'Cancel run')
  log('Cancel run clicked in the Runs drawer')
  const done1 = await waitRun(r1.id, ['cancelled', 'completed', 'failed'], 120)
  await page.waitForTimeout(1500)
  await shot(page, '01-cancelled-from-runs')
  log(`cancelled run → ${done1.status}; steps: ${steps(done1)}`)
  await closeDrawer(page)

  // 3. both fallbacks off, from the Settings switches
  await nav(page, 'settings')
  for (const name of ['Full-catalog fallback', 'Dynamic worker fallback']) {
    const sw = page.getByRole('switch', { name }).first()
    await sw.scrollIntoViewIfNeeded()
    if ((await sw.getAttribute('aria-checked')) === 'true') await sw.click()
    await page.waitForTimeout(600)
  }
  const s = (await get('/settings')).json
  log(`settings: full_fallback=${s.orchestrator_full_fallback_enabled} dynamic_worker_fallback=${s.dynamic_worker_fallback_enabled}`)
  await page.getByRole('switch', { name: 'Full-catalog fallback' }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '03-fallbacks-disabled')

  // 4. the uncovered ask now fails for real
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, UNCOVERED)
  await page.waitForTimeout(2000)
  const r2 = (await get('/runs?limit=1')).json[0]
  const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '04-failed-run-in-chat')
  log(`uncovered ask with fallbacks off → ${done2.status}; error: ${String(done2.error || '').slice(0, 200)}; steps: ${steps(done2)}`)

  // 5. fallbacks back on, then Retry (re-plan) from the failed run's drawer
  await nav(page, 'settings')
  for (const name of ['Full-catalog fallback', 'Dynamic worker fallback']) {
    const sw = page.getByRole('switch', { name }).first()
    await sw.scrollIntoViewIfNeeded()
    if ((await sw.getAttribute('aria-checked')) !== 'true') await sw.click()
    await page.waitForTimeout(600)
  }
  const s2 = (await get('/settings')).json
  log(`settings restored: full_fallback=${s2.orchestrator_full_fallback_enabled} dynamic_worker_fallback=${s2.dynamic_worker_fallback_enabled}`)

  if (done2.status !== 'failed') {
    log('the uncovered ask did not fail — no Retry leg to show (recorded as-is)')
    return
  }
  await nav(page, 'runs')
  const failedRow = page.locator('table tbody tr').filter({ hasText: /failed/i }).first()
  await failedRow.click()
  await page.getByRole('button', { name: 'Retry (re-plan)' }).waitFor({ timeout: 10000 })
  await page.waitForTimeout(600)
  await shot(page, '05-failed-drawer-retry')
  await click(page, 'Retry (re-plan)')
  await page.waitForTimeout(2000)
  const r3 = (await get('/runs?limit=1')).json[0]
  log(`retry launched: ${r3.id} (${r3.status})`)
  await shot(page, '06-retry-launched')
  await closeDrawer(page)
  const done3 = await waitRun(r3.id, ['completed', 'failed', 'cancelled'], 300)
  log(`retried run → ${done3.status}; steps: ${steps(done3)}`)
  log(`retry answer: ${(done3.final_answer || '').slice(0, 160)}`)
  await nav(page, 'runs')
  await page.getByPlaceholder('Search…').fill('unit-converter')
  await page.waitForTimeout(800)
  await shot(page, '07-failed-and-retried-rows')

  // the failed row deleted from its drawer
  await page.locator('table tbody tr').filter({ hasText: /failed/i }).first().click()
  await page.getByRole('button', { name: 'Delete' }).waitFor({ timeout: 10000 })
  await click(page, 'Delete')
  await page.waitForTimeout(1500)
  const gone = (await get(`/runs/${r2.id}`)).status
  log(`GET deleted run → HTTP ${gone}`)
  await shot(page, '08-after-delete')
  await page.getByPlaceholder('Search…').fill('')
}
