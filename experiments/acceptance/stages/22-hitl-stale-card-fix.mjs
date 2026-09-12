// Stage 22 — the HITL card across surfaces (regression, spec §14 step 6): a
// gate resolved from the Settings queue in a second tab collapses the chat
// card instead of leaving it armed-but-dead; and a gate approved from the
// chat card shows as resolved in the queue tab.
import { TRIAL_MESSAGE } from './_trial.mjs'

export default async function ({ page, context, nav, shot, settings, get, log, sendChat, waitRun, steps, newConversation }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null })
  const queueShot = async (tab, name) => {
    await tab.reload()
    await tab.waitForTimeout(1500)
    await tab.getByText('HITL queue').first().scrollIntoViewIfNeeded()
    await tab.waitForTimeout(400)
    await tab.screenshot({ path: `${process.env.ACC_SHOTS}/22-hitl-stale-card-fix/${name}.png` })
    log(`shot ${name}.png (second tab)`)
  }
  const tab = await context.newPage()
  await tab.setViewportSize({ width: 1440, height: 900 })
  await tab.goto(`${page.url().split('#')[0] || 'http://localhost/'}#/settings`).catch(() => {})

  // leg A — resolved from the queue; the chat card collapses
  await nav(page, '')
  await newConversation(page)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(2000)
  const r1 = (await get('/runs?limit=1')).json[0]
  await tab.goto(`${page.url().split('#')[0]}#/settings`)
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await page.waitForTimeout(500)
  await shot(page, '00-gate-armed-in-chat')
  await queueShot(tab, '03-queue-pending-second-tab')
  await tab.getByRole('button', { name: /^Approve$/ }).first().click()
  log('approved from the queue tab')
  await page.waitForTimeout(2500)
  const cardStillArmed = await page.getByRole('button', { name: /✓ Approve/ }).count()
  log(`chat card after the cross-surface approval: ${cardStillArmed ? 'STILL ARMED' : 'collapsed'}`)
  await shot(page, '01-card-collapsed-cross-surface')
  const done1 = await waitRun(r1.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '02-run-completed')
  log(`leg A run → ${done1.status}; steps: ${steps(done1)}`)

  // leg B — approved from the chat card; the queue shows it resolved
  await newConversation(page)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(2000)
  const r2 = (await get('/runs?limit=1')).json[0]
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await tab.reload()
  await tab.waitForTimeout(1500)
  const pendingBefore = (await get('/hitl/pending')).json.length
  await page.getByRole('button', { name: /✓ Approve/ }).first().click()
  await page.waitForTimeout(1500)
  await shot(page, '04-direct-approve-collapsed')
  const pendingAfter = (await get('/hitl/pending')).json.length
  log(`hitl pending: ${pendingBefore} → ${pendingAfter} after the direct approve`)
  await queueShot(tab, '05-queue-resolved-second-tab')
  const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
  log(`leg B run → ${done2.status}`)
  await tab.close()
}
