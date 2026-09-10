// Stage 28 — configuration hardening (spec §14e steps 41–44): the composer's
// per-conversation target pin (a pin in one conversation does not leak into
// another, and survives switching back, with the history-summary option),
// the Settings sections for Ambient / A2A / API guardrails / Orchestrator
// with live nav toggling, a read-back after an edit and an inline 422 for
// an out-of-range value, the tick-bounded poll-interval throttle for parked
// A2A tasks, the overlap-guard threshold moving the overlap dialog, the
// rate-limit burst moving the 429 boundary (transcript), and the ambient
// toast for a tier-0 delivery.
const CP_BEARER = process.env.ACC_A2A_BEARER || 'http://172.18.0.1:8027'
const LOCAL = (url) => (process.env.ACC_A2A_LOCAL_HOST || 'http://localhost') + ':' + url.split(':').pop()
async function setMode(url, mode) {
  const res = await fetch(`${LOCAL(url)}/_control/set-mode`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(mode) })
  return res.json().catch(() => ({}))
}

export default async function (ctx) {
  const { page, nav, shot, settings, get, post, api, log, closeDrawer, submitSave, click, newConversation, askAndSettle, sendChat, waitRun, openConversation } = ctx
  const initial = (await get('/settings')).json
  await settings({ orchestrator_mode: 'graph', default_model_params: null, ambient_enabled: true, a2a_enabled: true })

  // ── the composer pin is per conversation ──
  const agents = (await get('/sub-agents')).json
  const analyst = agents.find((a) => a.name === 'site-analyst')
  if (analyst && !analyst.direct_exposure) await api('PATCH', `/sub-agents/${analyst.id}`, { direct_exposure: true })
  await nav(page, '')
  await newConversation(page)
  const target = () => page.locator('select').filter({ hasText: 'Orchestrator (auto)' }).first()
  await target().selectOption({ label: 'site-analyst' })
  await page.waitForTimeout(400)
  await shot(page, '00-conv-a-pinned')
  const a1 = await askAndSettle(page, 'Summarize this: 8 and 9 make seventeen; publish the summary.')
  log(`conversation A run: target=${a1.target_sub_agent_id ? 'site-analyst (direct)' : 'orchestrator'} status=${a1.status}`)
  await shot(page, '01-conv-a-direct-run')
  const convA = a1.conversation_id
  await newConversation(page)
  await page.waitForTimeout(400)
  log(`conversation B picker: ${await target().inputValue()} (empty = Orchestrator (auto))`)
  await shot(page, '02-conv-b-picker-auto')
  const b1 = await askAndSettle(page, 'Use the sitefiles add tool to add 3 and 4. Number only.')
  log(`conversation B run: target=${b1.target_sub_agent_id || 'orchestrator'} status=${b1.status}`)
  await shot(page, '03-conv-b-planner-run')
  await openConversation(page, 'Summarize this: 8 and 9')
  await page.waitForTimeout(800)
  const restored = await target().inputValue()
  log(`back in A: pin restored=${restored === analyst?.id}`)
  const summary = page.locator('label').filter({ hasText: /summary/i }).locator('input[type=checkbox]').first()
  if (await summary.count()) {
    await summary.check()
    log('history-summary option shown for the pinned conversation and checked')
  } else log('history-summary option not rendered (needs a completed run in the pinned conversation)')
  await shot(page, '04-conv-a-pin-restored-summary-checked')
  await openConversation(page, 'Use the sitefiles add tool to add 3 and 4')
  await page.waitForTimeout(600)
  log(`back in B: picker=${(await target().inputValue()) || 'auto'}`)
  await shot(page, '05-conv-b-still-auto')
  await openConversation(page, 'Summarize this: 8 and 9')
  await page.waitForTimeout(600)
  const a2 = await askAndSettle(page, 'Now summarize this too: 20 and 22 make forty-two; publish it.')
  log(`conversation A second run: target=${a2.target_sub_agent_id ? 'direct' : 'orchestrator'} include_history_summary=${a2.include_history_summary}`)
  await shot(page, '06-conv-a-second-direct-plus-ctx')
  await target().selectOption({ label: 'Orchestrator (auto)' })

  // ── Settings sections with live nav toggling, read-back, inline 422 ──
  await nav(page, 'settings')
  const ambient = page.getByRole('switch', { name: 'Ambient mode' }).first()
  await ambient.scrollIntoViewIfNeeded()
  if ((await ambient.getAttribute('aria-checked')) === 'true') await ambient.click()
  await page.waitForTimeout(1000)
  log(`ambient off → nav Ambient links: ${await page.getByRole('link', { name: /Ambient/ }).count()}`)
  await shot(page, '07-settings-ambient-master-off')
  await ambient.click()
  await page.waitForTimeout(1000)
  log(`ambient on → nav Ambient links: ${await page.getByRole('link', { name: /Ambient/ }).count()}`)
  await shot(page, '08-settings-ambient-on-nav-live')
  await page.getByLabel('Max routines').scrollIntoViewIfNeeded()
  await shot(page, '09-settings-ambient-knobs')
  const tick = page.getByLabel('Tick interval (s)')
  await tick.fill('45')
  await tick.blur()
  await page.waitForTimeout(1000)
  log(`tick read-back: settings.ambient_tick_interval_s=${(await get('/settings')).json.ambient_tick_interval_s}; field shows ${await tick.inputValue()}`)
  await shot(page, '10-settings-tick-45-readback')
  await tick.fill('5')
  await tick.blur()
  await page.waitForTimeout(1200)
  const note = await page.locator('.bg-rose-500\\/10').first().textContent().catch(() => '')
  log(`tick=5 → inline: ${String(note).trim().slice(0, 140)}; setting still ${(await get('/settings')).json.ambient_tick_interval_s}`)
  await shot(page, '11-settings-422-inline')
  await tick.fill(String(initial.ambient_tick_interval_s))
  await tick.blur()
  await page.waitForTimeout(800)
  await page.getByText('A2A — remote agents (§19)', { exact: true }).scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await shot(page, '12-settings-a2a-on-knobs')
  await page.getByText('API guardrails', { exact: true }).scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await shot(page, '13-settings-api-guardrails')
  await page.getByLabel('Overlap-guard threshold (%)').scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  await shot(page, '14-settings-orchestrator-overlap-recursion')

  // ── the poll-interval throttle is tick-bounded ──
  const agent = (await get('/remote-agents')).json.find((a) => a.name === 'polyglot-agent')
  if (agent) {
    await settings({ ambient_tick_interval_s: 60, a2a_poll_interval_s: 5, a2a_task_timeout_s: 10, ambient_quiet_hours: [] })
    await setMode(CP_BEARER, { kind: 'slow', delay: 20 })
    await nav(page, '')
    await newConversation(page)
    const parked = await askAndSettle(page, 'Ask the remote polyglot agent to research tick-bounded polling; do not wait if it is slow.', { approve: false })
    log(`parked: ${/parked/i.test(parked.final_answer || '')}`)
    await shot(page, '15-poll-throttle-parked-answer')
    await page.waitForTimeout(30000)
    let t = (await get(`/remote-agents/${agent.id}/tasks`)).json
    t = Array.isArray(t) ? t : t.items || []
    log(`after 30s with poll=5s but tick=60s: task states ${t.map((x) => x.state).join(', ')} (effective cadence is max(tick, interval))`)
    await nav(page, 'remote-agents')
    await page.getByText('polyglot-agent', { exact: true }).first().click()
    await page.waitForTimeout(1000)
    await page.getByTestId('a2a-tasks').scrollIntoViewIfNeeded()
    await shot(page, '16-poll-throttle-still-parked-after-ticks')
    await closeDrawer(page)
    await settings({ ambient_tick_interval_s: 15 })
    let delivered = false
    for (let i = 0; i < 40; i++) {
      t = (await get(`/remote-agents/${agent.id}/tasks`)).json
      t = Array.isArray(t) ? t : t.items || []
      if (t.some((x) => x.delivered)) {
        delivered = true
        break
      }
      await page.waitForTimeout(3000)
    }
    log(`tick lowered to 15s → delivered within 2 minutes: ${delivered}`)
    await page.getByText('polyglot-agent', { exact: true }).first().click()
    await page.waitForTimeout(1000)
    await page.getByTestId('a2a-tasks').scrollIntoViewIfNeeded()
    await shot(page, '17-poll-interval-lowered-task-delivered')
    await closeDrawer(page)
    await nav(page, 'ambient')
    await page.waitForTimeout(1200)
    await shot(page, '18-poll-inbox-delivery')
    await setMode(CP_BEARER, null)
  } else {
    log('no polyglot-agent registered (stage 27 did not run) — the poll-throttle legs are skipped')
  }

  // ── the overlap-guard threshold moves the dialog ──
  const notes = (await get('/skills')).json.find((s) => s.name === 'notes-formatter')
  await settings({ overlap_threshold_percent: 10 })
  await nav(page, 'skills')
  await click(page, '+ New skill')
  await page.waitForTimeout(600)
  await page.getByLabel('Name').fill('notes-tidier')
  await page.getByLabel('Description').fill(notes ? notes.description : 'Turns rough notes into a clean bullet list. No tools.')
  await page.getByLabel(/Persona/).fill('You are a crisp editor.')
  await page.locator('textarea[rows="14"]').fill('# Purpose\n1. Read the notes.\n2. Return them as tight bullets, nothing else.\n')
  await page.waitForTimeout(300)
  await shot(page, '19-overlap-near-duplicate-form')
  const res = await submitSave(page, 'Create skill', { onOverlap: () => shot(page, '20-overlap-dialog-at-threshold-10') })
  log(`near-duplicate save at threshold 10% → ${JSON.stringify(res)}`)
  if (res.outcome === 'overlap') await page.getByRole('button', { name: /Cancel/ }).first().click().catch(() => {})
  await closeDrawer(page)
  await settings({ overlap_threshold_percent: initial.overlap_threshold_percent })

  // ── the rate-limit burst moves the 429 boundary (transcript) ──
  const lines = ['# §14e-43 — rate_limit_burst moves the 429 boundary (spec §18.8 token bucket)', '']
  const burst = async (n) => {
    const out = []
    for (let i = 1; i <= n; i++) out.push(`GET /skills [${i}] -> ${(await get('/skills')).status}`)
    return out
  }
  lines.push(`$ PATCH /settings {rate_limit_burst: 5, rate_limit_per_s: 1} -> ${(await api('PATCH', '/settings', { rate_limit_burst: 5, rate_limit_per_s: 1 })).status}`)
  lines.push('', '$ burst=5, refill=1/s — eight rapid GETs:', ...(await burst(8)))
  let restore = await api('PATCH', '/settings', { rate_limit_burst: initial.rate_limit_burst, rate_limit_per_s: initial.rate_limit_per_s })
  for (let i = 0; i < 10 && restore.status === 429; i++) {
    await page.waitForTimeout(1500)
    restore = await api('PATCH', '/settings', { rate_limit_burst: initial.rate_limit_burst, rate_limit_per_s: initial.rate_limit_per_s })
  }
  lines.push('', `$ PATCH /settings {rate_limit_burst: ${initial.rate_limit_burst}, rate_limit_per_s: ${initial.rate_limit_per_s}} (retried while throttled) -> ${restore.status}`)
  await page.waitForTimeout(2000)
  lines.push('', `$ burst=${initial.rate_limit_burst} — the same eight rapid GETs, boundary moved:`, ...(await burst(8)))
  const fs = await import('node:fs')
  const dir = `${process.env.ACC_SHOTS}/28-config-hardening`
  fs.writeFileSync(`${dir}/22-rate-limit-429-transcript.txt`, lines.join('\n') + '\n')
  log(`rate-limit transcript written (${lines.filter((l) => l.includes('-> 429')).length} throttled calls)`)
  await nav(page, 'settings')
  await page.getByLabel('Rate-limit burst').scrollIntoViewIfNeeded()
  await shot(page, '21-guardrails-burst-5')

  // ── the ambient toast for a tier-0 delivery ──
  // (a tier-0 delivery inserted server-side — no click, no navigation — the
  // tick flushes it as an interrupt, /ambient/stream broadcasts it, the
  // toaster renders it on whatever page is open)
  await settings({ ambient_tick_interval_s: 15, ambient_quiet_hours: [] })
  await nav(page, 'runs')
  await shot(page, '23-ambient-toast-before')
  const { execSync } = await import('node:child_process')
  const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
  let seeded = 'db not reachable from this host — no tier-0 delivery seeded'
  try {
    seeded = execSync(
      `docker exec ${DB} psql -U ${process.env.ACC_DB_USER || 'concierge'} -d ${process.env.ACC_DB_NAME || 'concierge'} -tAc "insert into deliveries (id, category, tier, urgency, title, body, created_at) values (gen_random_uuid(), 'ops', 0, 5, 'payments-api p99 error rate 9.4% and rising', 'one in eleven checkouts failing; no rollback yet', now()) returning id"`,
      { encoding: 'utf8' },
    ).trim()
  } catch {}
  log(`tier-0 delivery seeded server-side: ${seeded}`)
  const seen = await page.getByTestId('ambient-toaster').waitFor({ timeout: 40000 }).then(() => true).catch(() => false)
  log(seen ? `toast: ${(await page.getByTestId('ambient-toaster').textContent()).trim().slice(0, 120)}` : 'no toast within 40s (a tier-0 delivery needs the interrupt tick + SSE)')
  await shot(page, '24-ambient-toast-visible')
  await settings({ ambient_tick_interval_s: initial.ambient_tick_interval_s, a2a_poll_interval_s: initial.a2a_poll_interval_s, a2a_task_timeout_s: initial.a2a_task_timeout_s, ambient_quiet_hours: initial.ambient_quiet_hours })
}
