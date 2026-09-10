// Stage 11 — HITL deny and the approval queue (spec §14 steps 6/9): one run
// paused at its gate is approved from the Settings HITL queue in a second
// tab; a second run is denied from the chat card with a typed note — the
// rail shows the denial, the trace's hitl step carries `denied` + the note.
import { TRIAL_MESSAGE } from './_trial.mjs'

export default async function ({ page, context, nav, shot, settings, get, log, sendChat, waitRun, run, steps, closeDrawer }) {
  await settings({ orchestrator_mode: 'graph' })
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(2000)
  const r1 = (await get('/runs?limit=1')).json[0]
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await page.waitForTimeout(500)
  await shot(page, '00-gate-armed')

  // the queue in a second tab: pending, then approved from there
  const tab = await context.newPage()
  await tab.setViewportSize({ width: 1440, height: 900 })
  await tab.goto(`${page.url().split('#')[0]}#/settings`)
  await tab.waitForTimeout(1500)
  await tab.getByText('HITL queue').first().scrollIntoViewIfNeeded()
  await tab.waitForTimeout(400)
  const queueShot = (name) => tab.screenshot({ path: `${process.env.ACC_SHOTS}/11-hitl-deny-and-queue/${name}.png` }).then(() => log(`shot ${name}.png (second tab)`))
  await queueShot('03-queue-pending')
  await tab.getByRole('button', { name: /^Approve$/ }).first().click()
  log('approved from the Settings HITL queue (second tab)')
  const done1 = await waitRun(r1.id, ['completed', 'failed', 'cancelled'], 300)
  await tab.waitForTimeout(1200)
  await tab.getByText('HITL queue').first().scrollIntoViewIfNeeded()
  await queueShot('04-queue-approved-run-completed')
  await tab.close()
  log(`run 1 → ${done1.status} after the queue approval`)

  // a second run, denied from the chat card with a note
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(2000)
  const r2 = (await get('/runs?limit=1')).json[0]
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await page.getByPlaceholder('optional note for the worker…').first().fill('Do not publish — the source is a demo page, not a real site.')
  await page.waitForTimeout(300)
  await shot(page, '05-deny-note-typed')
  await page.getByRole('button', { name: /✕ Deny/ }).first().click()
  log('denied from the chat card with a note')
  const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '06-denied-rail-state')
  const hitl = (done2.steps || []).find((s) => s.step_type === 'hitl')
  log(`run 2 → ${done2.status}; hitl step: ${JSON.stringify(hitl?.output || {}).slice(0, 160)}; steps: ${steps(done2)}`)

  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await page.getByText(/hitl/i).first().scrollIntoViewIfNeeded().catch(() => {})
  await shot(page, '07-trace-hitl-decision-deny')
  await closeDrawer(page)
}
