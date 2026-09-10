// Stage 26 — ambient (spec §17 / §18 / §8.9): the Ambient section in
// Settings switched on (the nav item appears), the Inbox landing, a routine
// built in the typed trigger builder with a webhook trigger and a filter, a
// fire token issued and revealed in the drawer, a REAL external fire over
// HTTP with the bearer token, the routine's run history, the ledger's
// fire/hold audit with the correlation chain and the precision panel, both
// watch-authoring paths (natural-language compile, typed filters), the
// digest flushed into the Inbox and feedback recorded, then the Evals page.
function hhmm(offsetMin) {
  const d = new Date(Date.now() + offsetMin * 60000)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

export default async function ({ page, nav, shot, settings, get, post, api, log, closeDrawer, waitRun, steps, MODEL }) {
  const initial = (await get('/settings')).json
  await settings({ orchestrator_mode: 'graph', default_model_params: null })

  // Settings: the master switch, then the knobs appear and the nav item shows
  await nav(page, 'settings')
  const master = page.getByRole('switch', { name: 'Ambient mode' }).first()
  await master.scrollIntoViewIfNeeded()
  if ((await master.getAttribute('aria-checked')) !== 'true') await master.click()
  await page.waitForTimeout(1000)
  await page.getByLabel('Tick interval (s)').fill('15')
  await page.getByLabel('Tick interval (s)').blur()
  await page.waitForTimeout(800)
  // quiet hours moved off "now" and a digest time two minutes out, so the
  // digest actually flushes during this stage (the default 22:00–07:00 quiet
  // window otherwise holds even catch-up flushes — a real operational trap)
  await settings({
    ambient_quiet_hours: [hhmm(120), hhmm(150)],
    ambient_digest_times: [hhmm(3)],
    ambient_timezone: 'UTC',
    ambient_salience_mode: 'off',
    ambient_pursuit: 'off',
  })
  await nav(page, 'settings')
  const s = (await get('/settings')).json
  log(`ambient_enabled=${s.ambient_enabled} tick=${s.ambient_tick_interval_s}s quiet=${JSON.stringify(s.ambient_quiet_hours)} digest_times=${JSON.stringify(s.ambient_digest_times)} channels=${JSON.stringify(s.ambient_channels)}`)
  await page.getByText('Ambient (§17)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-settings-ambient-section')
  log(`nav shows Ambient: ${await page.getByRole('link', { name: /Ambient/ }).count()}`)

  await nav(page, 'ambient')
  await shot(page, '01-ambient-inbox-landing')

  // the routine: webhook trigger + a filter on the fire's payload
  for (const r of (await get('/routines')).json) if (r.name === 'ops-alert-triage') await api('DELETE', `/routines/${r.id}`)
  await page.getByRole('tab', { name: 'Routines' }).click()
  await page.getByRole('button', { name: 'New routine' }).click()
  await page.waitForTimeout(600)
  await page.getByLabel('name').fill('ops-alert-triage')
  await page.getByLabel('prompt (trusted instruction)').fill(
    'An ops alert arrived (the untrusted text and payload are attached). Summarize what happened in two lines and propose one safe, reversible first remediation step. Do not run tools.',
  )
  await page.getByLabel('autonomy').selectOption('propose')
  const builder = page.getByTestId('trigger-builder')
  await builder.locator('select').first().selectOption('webhook')
  await page.waitForTimeout(300)
  await page.getByRole('button', { name: '+ filter' }).click()
  const filters = page.getByTestId('filter-rows')
  await filters.getByPlaceholder('field (e.g. sev or payload.repo)').fill('sev')
  await filters.locator('select').first().selectOption('equals')
  await filters.getByPlaceholder('value').fill('high')
  await page.waitForTimeout(300)
  await shot(page, '02-routine-builder-webhook-trigger')
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.waitForTimeout(1200)
  const routine = (await get('/routines')).json.find((r) => r.name === 'ops-alert-triage')
  log(`routine ${routine?.id} status=${routine?.status} triggers=${JSON.stringify(routine?.triggers).slice(0, 200)}`)
  if (!routine) throw new Error('routine not created')
  await closeDrawer(page)

  // the fire token, issued and revealed in the drawer
  await page.getByRole('button', { name: `open routine ${routine.name}` }).click()
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: /Issue token|Rotate token/ }).click()
  await page.waitForTimeout(1000)
  const masked = page.getByTitle('click to reveal').first()
  await masked.click()
  await page.waitForTimeout(300)
  const token = (await page.getByTitle('click to mask').first().textContent()).trim()
  log(`fire token issued in the UI: ${token.slice(0, 8)}… (${token.length} chars, shown once)`)
  await shot(page, '03-routine-fire-token-issued')
  await closeDrawer(page)

  // a REAL external fire with the bearer token: one held by the filter, one fired
  const fire = (body) => api('POST', `/routines/${routine.id}/fire`, body, { authorization: `Bearer ${token}` })
  const held = await fire({ text: 'cache warm completed on web-03 in 41s', payload: { sev: 'low', host: 'web-03' } })
  log(`fire (sev=low, filter says hold) → HTTP ${held.status} ${JSON.stringify(held.json)}`)
  const fired = await fire({ text: 'db-01 replication lag 45s and rising; primary CPU 92%', payload: { sev: 'high', host: 'db-01', service: 'postgres' } })
  log(`fire (sev=high) → HTTP ${fired.status} ${JSON.stringify(fired.json)}`)
  const unauth = await api('POST', `/routines/${routine.id}/fire`, { text: 'x', payload: {} }, { authorization: 'Bearer amb_wrong' })
  log(`fire with a wrong token → HTTP ${unauth.status}`)
  let run = null
  for (let i = 0; i < 90; i++) {
    const runs = (await get(`/runs?routine_id=${routine.id}`)).json
    run = Array.isArray(runs) ? runs[0] : null
    if (run) break
    await page.waitForTimeout(2000)
  }
  if (run) {
    const done = await waitRun(run.id, ['completed', 'failed', 'cancelled'], 300)
    log(`routine run ${run.id} → ${done.status}; trigger=${done.trigger}; steps: ${steps(done)}`)
    log(`proposal: ${(done.final_answer || '').replace(/\s+/g, ' ').slice(0, 200)}`)
  } else {
    log('no run appeared for the fire within 3 minutes (recorded as-is)')
  }
  await page.getByRole('button', { name: `open routine ${routine.name}` }).click()
  await page.waitForTimeout(1500)
  await page.getByTestId('routine-run-history').scrollIntoViewIfNeeded()
  await shot(page, '04-routine-run-history-live-fire')
  await closeDrawer(page)

  // the ledger: fired + held rows, the chain, the precision panel
  await page.getByRole('tab', { name: 'Ledger' }).click()
  await page.waitForTimeout(1200)
  const ledger = (await get('/ambient/ledger')).json
  const items = Array.isArray(ledger) ? ledger : ledger.items || []
  log(`ledger: ${items.slice(0, 6).map((e) => `${e.kind}/${e.verdict}: ${String(e.reason || '').slice(0, 50)}`).join(' | ')}`)
  const expand = page.getByRole('button', { name: /expand .* event/ }).first()
  if (await expand.count()) {
    await expand.click()
    await page.waitForTimeout(1000)
  }
  await shot(page, '05-ledger-audit-and-chain')
  await page.getByText(/intervention precision per category/).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await shot(page, '06-ledger-precision-panel')

  // watches: describe → compile → confirm; typed filters → proposed → discard
  await page.getByRole('tab', { name: 'Watches' }).click()
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: 'describe it' }).click()
  await page.getByTestId('watch-authoring').locator('textarea').fill('tell me when a high-severity alert appears in the ops feed')
  await page.getByRole('button', { name: 'Compile' }).click()
  await page.getByTestId('watch-proposal').waitFor({ timeout: 90000 })
  await page.waitForTimeout(500)
  await shot(page, '07-watch-describe-compiled')
  await page.getByTestId('watch-proposal').getByRole('button', { name: 'Confirm' }).click()
  await page.waitForTimeout(1200)
  const watches = (await get('/watches')).json.items || []
  log(`watches: ${watches.map((w) => `${w.status}/${w.condition_type}: ${String(w.text || '').slice(0, 50)}`).join(' | ')}`)
  await shot(page, '08-watch-confirmed-active')
  await page.getByRole('button', { name: 'typed filters' }).click()
  await page.getByPlaceholder('what this watch is about (shown in the list)').fill('deploys of the payments repo')
  await page.getByRole('button', { name: '+ filter' }).click()
  const wf = page.getByTestId('watch-authoring').getByTestId('filter-rows')
  await wf.getByPlaceholder('field (e.g. sev or payload.repo)').fill('payload.repo')
  await wf.locator('select').first().selectOption('equals')
  await wf.getByPlaceholder('value').fill('payments')
  await page.getByPlaceholder('optional semantic predicate — a yes/no question judged per event').fill('Is this a production deploy?')
  await page.getByRole('button', { name: 'Create proposed watch' }).click()
  await page.getByTestId('watch-proposal').waitFor({ timeout: 30000 })
  await page.waitForTimeout(500)
  await shot(page, '09-watch-typed-filters-proposed')
  await page.getByTestId('watch-proposal').getByRole('button', { name: 'Discard' }).click()
  await page.waitForTimeout(800)

  // the digest flushes at the time set above; then feedback on a delivered item
  await page.getByRole('tab', { name: 'Inbox' }).click()
  let delivered = []
  for (let i = 0; i < 120; i++) {
    const d = (await get('/deliveries?limit=100')).json
    delivered = (Array.isArray(d) ? d : d.items || []).filter((x) => x.delivered_at && x.channel !== 'silent')
    if (delivered.length) break
    await page.waitForTimeout(3000)
  }
  log(`deliveries: ${delivered.length} delivered — ${delivered.slice(0, 3).map((x) => `${x.tier}/${x.category}/${x.channel}: ${String(x.title || '').slice(0, 50)}`).join(' | ') || 'none within 6 minutes'}`)
  await page.waitForTimeout(1500)
  await shot(page, '10-inbox-digest-and-delivered')
  const card = page.getByTestId(/delivery-(unseen|seen)/).first()
  if (await card.count()) {
    await card.hover()
    await page.waitForTimeout(800)
    await card.getByRole('button', { name: 'mark accepted' }).click()
    await page.waitForTimeout(1200)
    const fb = (await get('/deliveries?limit=100')).json
    const first = (Array.isArray(fb) ? fb : fb.items || []).find((x) => x.feedback)
    log(`feedback recorded: ${first?.feedback} reward=${first?.reward}`)
  }
  await shot(page, '11-inbox-feedback-recorded')

  await nav(page, 'evals')
  await shot(page, '12-evals-page')

  await settings({ ambient_quiet_hours: initial.ambient_quiet_hours, ambient_digest_times: initial.ambient_digest_times, ambient_tick_interval_s: initial.ambient_tick_interval_s })
  log('quiet hours, digest times and the tick restored')
}
