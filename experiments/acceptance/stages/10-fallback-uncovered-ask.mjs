// Stage 10 — the uncovered ask (spec §14 step 7): a request naming a
// capability that does not exist. The planner reports no confident match,
// the chat shows the full-catalog fallback banner while the run is live,
// the answer settles, and the trace carries `rung: fallback`.
export default async function ({ page, nav, shot, settings, get, log, sendChat, waitRun, steps, closeDrawer }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null })
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, "Use the invoice-reconciler capability to reconcile last month's supplier invoices against the ledger and list the mismatches.")
  await page.waitForTimeout(2000)
  const r = (await get('/runs?limit=1')).json[0]
  const banner = page.getByText(/full-catalog fallback engaged/i).first()
  const saw = await banner.waitFor({ timeout: 90000 }).then(() => true).catch(() => false)
  log(saw ? 'fallback banner live' : 'no fallback banner seen live (the run may have settled first)')
  await shot(page, '00-fallback-banner-live')
  const done = await waitRun(r.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '01-fallback-answer')
  const route = (done.steps || []).find((s) => s.step_type === 'route')
  const plan = (done.steps || []).find((s) => s.step_type === 'plan')
  log(`plan.no_confident_match=${plan?.output?.no_confident_match} route.rung=${route?.output?.rung}; steps: ${steps(done)}`)
  log(`answer: ${(done.final_answer || '').slice(0, 160)}`)
  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await page.getByText(/fallback/i).first().scrollIntoViewIfNeeded().catch(() => {})
  await shot(page, '02-trace-rung-fallback')
  await closeDrawer(page)
}
