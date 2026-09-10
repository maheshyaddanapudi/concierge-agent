// The four trials (spec §14 step 6, and step 11 for agentic): the same
// multi-turn conversation driven through the Chat page under
// {graph, agentic} × {effort high, effort default}. Message 1 invokes the
// custom sub agent built in stage 05 (`site-analyst`), which pauses at its
// HITL gate; the gate is approved in the chat card; message 2 is a follow-up
// that must be answered from message 1's result. Then the run's trace on
// the Runs page.
export const TRIAL_MESSAGE =
  'Ask the site-analyst sub agent to summarize this: the demo site says 21 and 21 make the answer; publish the summary.'
export const FOLLOW_UP = 'What number did the summary you just produced mention? Answer with the number only.'

export function trial({ mode, effort }) {
  return async function ({ page, nav, shot, settings, get, log, sendChat, waitRun, run, steps, closeDrawer, MODEL }) {
    // settings: orchestrator mode and the default model's effort
    await settings({ orchestrator_mode: mode, default_model: MODEL, default_model_params: effort ? { effort } : null })
    await nav(page, 'settings')
    await shot(page, '00-settings-mode-and-effort')

    // message 1 from the composer
    await nav(page, '')
    await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
    await page.waitForTimeout(400)
    await sendChat(page, TRIAL_MESSAGE)
    await page.waitForTimeout(2500)
    const runs = (await get('/runs?limit=1')).json
    const r1 = Array.isArray(runs) ? runs[0] : runs.items?.[0]
    log(`run 1: ${r1?.id} (${mode}, effort ${effort || 'default'})`)

    // the plan card while the run is live (graph: waves; agentic: todos)
    const planCard = page.locator('text=/PLAN · |live plan · agentic todos/i').first()
    const sawPlan = await planCard.waitFor({ timeout: 45000 }).then(() => true).catch(() => false)
    if (sawPlan) await shot(page, '01-plan-card-live')
    else log('no plan card appeared before the gate (fallback or a very fast route) — documented, not faked')
    // the rails mid-run: taken while the worker is still busy, before the gate
    // arms (a gate already armed is frame 03, not this one)
    await page.getByText(/SUB_AGENT|TOOL_CALL|SKILL/).first().waitFor({ timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(800)
    await shot(page, '02-rails-and-ticker-midrun')

    // the HITL gate armed in the chat card
    await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
    await page.waitForTimeout(600)
    await shot(page, '03-gate-armed')
    await page.getByRole('button', { name: /✓ Approve/ }).first().click()
    log('gate approved from the chat card')
    await page.waitForTimeout(1500)
    await shot(page, '04-gate-resolved-resumed')
    const done1 = await waitRun(r1.id, ['completed', 'failed', 'cancelled'], 300)
    await page.waitForTimeout(1500)
    await shot(page, '05-answer-a2ui-primary')
    const rawToggle = page.getByRole('button', { name: /view raw response/ }).first()
    if (await rawToggle.count()) {
      await rawToggle.click()
      await page.waitForTimeout(600)
      await shot(page, '06-raw-expanded')
      await page.getByRole('button', { name: /hide raw response/ }).first().click().catch(() => {})
    } else {
      log('no structured artifact on this answer — no raw toggle to show')
    }
    log(`run 1 → ${done1.status}; steps: ${steps(done1)}`)
    log(`answer 1: ${(done1.final_answer || '').slice(0, 160)}`)

    // message 2 — the follow-up in the same conversation
    await sendChat(page, FOLLOW_UP)
    await page.waitForTimeout(2500)
    const runs2 = (await get('/runs?limit=1')).json
    const r2 = Array.isArray(runs2) ? runs2[0] : runs2.items?.[0]
    const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
    await page.waitForTimeout(1200)
    await shot(page, '07-followup-second-turn')
    log(`run 2 → ${done2.status}; answer 2: ${(done2.final_answer || '').slice(0, 120)}`)

    // the trace on the Runs page
    // the trace of message 1's run (the newest row carrying its text — the
    // follow-up is the first row and would show a one-step trace)
    await nav(page, 'runs')
    await page.locator('table tbody tr').filter({ hasText: TRIAL_MESSAGE.slice(0, 40) }).first().click()
    await page.waitForTimeout(1200)
    await shot(page, '08-trace-top')
    const drawer = page.locator('.fixed.inset-0').last()
    await drawer.locator('text=/steps|timeline|plan/i').first().scrollIntoViewIfNeeded().catch(() => {})
    await page.mouse.wheel(0, 900)
    await page.waitForTimeout(600)
    await shot(page, '09-trace-steps')
    await closeDrawer(page)
    return { r1: done1, r2: done2 }
  }
}
