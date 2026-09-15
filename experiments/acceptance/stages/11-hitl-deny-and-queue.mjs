// Stage 11 — HITL deny and the approval queue (spec §14 steps 6/9): one run
// paused at its gate is approved from the Settings HITL queue in a second
// tab; a second run is denied from the chat card with a typed note — the
// rail shows the denial, the trace's hitl step carries `denied` + the note.
import { TRIAL_MESSAGE } from './_trial.mjs'

export default async function ({ page, context, nav, shot, settings, get, log, sendChat, waitRun, run, steps, closeDrawer, newConversation, expect, expectMatch, expectStatus }) {
  await settings({ orchestrator_mode: 'graph' })
  // retried for the reason _trial.mjs explains: the sub agent's branch is
  // natural language the model evaluates, so reaching the gate is a model
  // decision. This stage is about the QUEUE and the DENIAL, not about which
  // edge the planner's workflow took.
  let r1 = null
  for (let attempt = 1; attempt <= 3; attempt++) {
    await nav(page, '')
    await newConversation(page)
    await sendChat(page, TRIAL_MESSAGE)
    await page.waitForTimeout(2000)
    r1 = (await get('/runs?limit=1')).json[0]
    const armed = await page
      .getByText('HUMAN APPROVAL REQUIRED')
      .first()
      .waitFor({ timeout: 120000 })
      .then(() => true)
      .catch(() => false)
    if (armed) break
    const settled = await run(r1.id)
    log(`attempt ${attempt}: no gate — ${settled?.status}, steps ${steps(settled)}`)
    expect(attempt < 3, 'the sub agent reached its HITL gate within three attempts')
  }
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
  // the queue's whole claim: the paused run is IN it, from a different surface
  const queued = (await get('/hitl/pending')).json
  expect(
    (Array.isArray(queued) ? queued : queued.items || []).some((q) => q.run_id === r1.id),
    'the paused run is in the Settings HITL queue',
  )
  await tab.getByRole('button', { name: /^Approve$/ }).first().click()
  log('approved from the Settings HITL queue (second tab)')
  const done1 = await waitRun(r1.id, ['completed', 'failed', 'cancelled'], 300)
  await tab.waitForTimeout(1200)
  await tab.getByText('HITL queue').first().scrollIntoViewIfNeeded()
  await queueShot('04-queue-approved-run-completed')
  await tab.close()
  log(`run 1 → ${done1.status} after the queue approval`)
  expectStatus(done1, 'completed', 'the run approved from the Settings queue')

  // a second run, denied from the chat card with a note
  await newConversation(page)
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
  // a denial must be RECORDED as one — with the operator's note — not
  // quietly turn into an approval
  expect(!!hitl, 'the denied run has a hitl step in its trace')
  expectMatch(JSON.stringify(hitl?.output || {}), /den/i, 'the hitl step carries the denial')
  expectMatch(JSON.stringify(hitl?.output || {}), /demo page/i, "…and the operator's note")

  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  // framing only
  await page.getByText(/hitl/i).first().scrollIntoViewIfNeeded().catch(() => {})
  await shot(page, '07-trace-hitl-decision-deny')
  await closeDrawer(page)
}
