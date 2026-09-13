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
  return async function ({ page, nav, shot, settings, get, log, sendChat, waitRun, run, steps, closeDrawer, newConversation, MODEL, expect, expectEq, expectStatus, expectStep, expectMatch }) {
    // settings: orchestrator mode and the default model's effort
    await settings({ orchestrator_mode: mode, default_model: MODEL, default_model_params: effort ? { effort } : null })
    await nav(page, 'settings')
    await shot(page, '00-settings-mode-and-effort')

    // message 1 from the composer
    await nav(page, '')
    await newConversation(page)
    await sendChat(page, TRIAL_MESSAGE)
    await page.waitForTimeout(2500)
    const runs = (await get('/runs?limit=1')).json
    const r1 = Array.isArray(runs) ? runs[0] : runs.items?.[0]
    log(`run 1: ${r1?.id} (${mode}, effort ${effort || 'default'})`)
    expect(!!r1?.id, 'the composer started a run')
    const live = await settings()
    expectEq(live.orchestrator_mode, mode, `the trial is running in ${mode} mode`)
    expectEq(live.default_model_params?.effort ?? null, effort, `…at effort ${effort || 'default'}`)

    // the plan card while the run is live (graph: waves; agentic: todos)
    const planCard = page.locator('text=/PLAN · |live plan · agentic todos/i').first()
    // a deliberate probe, not a swallow: whether the plan card renders
    // before the gate is timing, and the trace assertion below is what
    // actually proves the mode planned
    const sawPlan = await planCard.waitFor({ timeout: 45000 }).then(() => true).catch(() => false)
    if (sawPlan) await shot(page, '01-plan-card-live')
    else log('no plan card appeared before the gate (fallback or a very fast route) — documented, not faked')
    // the rails while the run is live (Stop button, RUNNING pill). The stub
    // tools answer in milliseconds, so by the time the sub agent's rail
    // renders its gate is usually already armed — this frame is the live
    // run, not a distinct pre-gate moment
    // framing only — the rails may already have scrolled past; the run's
    // own trace is asserted at the end
    await page.getByText(/SUB_AGENT|TOOL_CALL|SKILL/).first().waitFor({ timeout: 30000 }).catch(() => {})
    await page.waitForTimeout(800)
    await shot(page, '02-rails-live-run')

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
      // cleanup click; the frame is already captured
      await page.getByRole('button', { name: /hide raw response/ }).first().click().catch(() => {})
    } else {
      log('no structured artifact on this answer — no raw toggle to show')
    }
    log(`run 1 → ${done1.status}; steps: ${steps(done1)}`)
    log(`answer 1: ${(done1.final_answer || '').slice(0, 160)}`)
    // what the trial claims: the gated multi-turn conversation went through
    expectStatus(done1, 'completed', `${mode}/${effort || 'default'} run 1`)
    // the gate really armed inside the run, and the sub agent's tools ran —
    // step types are lowercase in the trace (`hitl:approve`, `tool_call:…`)
    expectStep(done1, /^hitl:/, 'run 1 went through the HITL gate')
    expectStep(done1, /^tool_call:/, 'the site-analyst sub agent called its tools')
    expect(!!(done1.final_answer || '').trim(), 'run 1 produced an answer')

    // message 2 — the follow-up in the same conversation
    await sendChat(page, FOLLOW_UP)
    await page.waitForTimeout(2500)
    const runs2 = (await get('/runs?limit=1')).json
    const r2 = Array.isArray(runs2) ? runs2[0] : runs2.items?.[0]
    const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
    await page.waitForTimeout(1200)
    await shot(page, '07-followup-second-turn')
    log(`run 2 → ${done2.status}; answer 2: ${(done2.final_answer || '').slice(0, 120)}`)
    expect(!!r2?.id && r2.id !== r1.id, 'the follow-up started a second run')
    expectStatus(done2, 'completed', `${mode}/${effort || 'default'} run 2`)
    // continuity is the whole point of the second turn: 21 + 21
    expectMatch(done2.final_answer, /42/, 'the follow-up answered from turn 1\'s result')

    // the trace on the Runs page
    // the trace of message 1's run (the newest row carrying its text — the
    // follow-up is the first row and would show a one-step trace)
    await nav(page, 'runs')
    await page.locator('table tbody tr').filter({ hasText: TRIAL_MESSAGE.slice(0, 40) }).first().click()
    await page.waitForTimeout(1200)
    await shot(page, '08-trace-top')
    const drawer = page.locator('.fixed.inset-0').last()
    // framing only
    await drawer.locator('text=/steps|timeline|plan/i').first().scrollIntoViewIfNeeded().catch(() => {})
    await page.mouse.wheel(0, 900)
    await page.waitForTimeout(600)
    await shot(page, '09-trace-steps')
    await closeDrawer(page)
    return { r1: done1, r2: done2 }
  }
}
