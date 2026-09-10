// Stage 27 — A2A remote agents (spec §19, §14d steps 33–40): the dark gate,
// card registration against live counterparties (the repo's scripted stub
// server, started on the host), write-only credentials, skills projected as
// kind=a2a tools, a skill and an ExComm sub agent authored on them, organic
// routing with fenced traces, the remote agent's question surfacing as a
// HITL card (reply / deny), Stop propagating a cancel mid-call, park →
// poller → Inbox delivery, a reply from the task drawer, card drift, and the
// auth matrix (apiKey via env, oauth2, an unsupported scheme).
//
// Counterparties (environment): ACC_A2A_BEARER (default http://172.18.0.1:8027),
// ACC_A2A_APIKEY (…:8028, expects env:A2A_STUB_API_KEY on the backend),
// ACC_A2A_OAUTH (…:8030), ACC_A2A_MTLS (…:8029, declares mutualTLS). Their
// control endpoints are reached from this host at ACC_A2A_*_LOCAL (default
// http://localhost:<port>).
const CP = {
  bearer: process.env.ACC_A2A_BEARER || 'http://172.18.0.1:8027',
  apikey: process.env.ACC_A2A_APIKEY || 'http://172.18.0.1:8028',
  mtls: process.env.ACC_A2A_MTLS || 'http://172.18.0.1:8029',
  oauth: process.env.ACC_A2A_OAUTH || 'http://172.18.0.1:8030',
}
const LOCAL = (url) => (process.env.ACC_A2A_LOCAL_HOST || 'http://localhost') + ':' + url.split(':').pop()

async function control(url, path, body) {
  const res = await fetch(`${LOCAL(url)}/_control/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return res.json().catch(() => ({}))
}

async function setMode(url, mode) {
  return control(url, 'set-mode', mode)
}

export default async function (ctx) {
  const { page, nav, shot, settings, get, post, patch, del, api, log, closeDrawer, submitSave, click, newConversation, askAndSettle, sendChat, waitRun, steps } = ctx
  const initial = (await get('/settings')).json
  await settings({ orchestrator_mode: 'graph', default_model_params: null, a2a_enabled: false, ambient_enabled: true })
  await setMode(CP.bearer, null)

  // the dark gate: no nav item while off; the switch reveals it
  await nav(page, 'settings')
  log(`nav shows Remote Agents while off: ${await page.getByRole('link', { name: /Remote Agents/ }).count()}`)
  await page.getByText('A2A — remote agents (§19)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-dark-nav-no-remote-agents')
  await page.getByRole('switch', { name: 'A2A' }).first().click()
  await page.waitForTimeout(1200)
  log(`nav shows Remote Agents after the switch: ${await page.getByRole('link', { name: /Remote Agents/ }).count()}`)
  await shot(page, '01-enabled-nav-remote-agents')

  // the empty registry, then a registration against the bearer counterparty
  for (const a of (await get('/remote-agents')).json) await del(`/remote-agents/${a.id}`)
  await nav(page, 'remote-agents')
  await shot(page, '02-remote-agents-empty')
  await click(page, '+ Register agent')
  await page.waitForTimeout(600)
  await page.getByLabel('Agent card URL').fill(CP.bearer)
  await page.getByLabel('Name (optional)').fill('polyglot-agent')
  await page.getByRole('button', { name: '+ credential' }).click()
  const rows = page.getByTestId('credential-rows')
  await rows.getByPlaceholder('scheme name (from the card)').fill('main')
  await rows.locator('select').first().selectOption('secret')
  await rows.getByPlaceholder(/secret, "user:pass" for basic/).fill('stub-bearer-token')
  await page.waitForTimeout(300)
  await shot(page, '03-register-form-filled')
  // the drawer's own button — the page header's "+ Register agent" also matches by substring
  await page.locator('.fixed.inset-0').last().getByRole('button', { name: 'Register', exact: true }).click()
  await page.waitForTimeout(3000)
  const agents = (await get('/remote-agents')).json
  const agent = agents.find((a) => a.name === 'polyglot-agent')
  log(`registered: ${agent?.name} status=${agent?.status} auth=${agent?.auth_status} tools=${agent?.tool_count} card=${agent?.card_url}`)
  if (!agent) throw new Error('polyglot-agent not registered')
  await closeDrawer(page)
  await shot(page, '04-agent-registered-active')

  // the drawer: card, skills, auth chips; write-only credentials
  await page.getByText('polyglot-agent', { exact: true }).first().click()
  await page.waitForTimeout(1000)
  await shot(page, '05-agent-detail-card-skills-auth')
  const drawer = page.locator('.fixed.inset-0').last()
  await drawer.getByText('Set credentials', { exact: true }).scrollIntoViewIfNeeded()
  await drawer.getByRole('button', { name: '+ credential' }).click()
  const rows2 = drawer.getByTestId('credential-rows')
  await rows2.getByPlaceholder('scheme name (from the card)').fill('main')
  await rows2.getByPlaceholder(/secret, "user:pass" for basic/).fill('stub-bearer-token')
  await page.waitForTimeout(300)
  await shot(page, '06-credentials-editor-write-only')
  await drawer.getByRole('button', { name: 'Save credentials' }).click()
  await page.waitForTimeout(1500)
  await drawer.getByRole('button', { name: 'Refresh card' }).click()
  await page.waitForTimeout(2000)
  const a2 = (await get(`/remote-agents/${agent.id}`)).json
  log(`after save + refresh: auth=${a2.auth_status} schemes=${JSON.stringify(a2.card?.securitySchemes || {}).slice(0, 120)} credentials in API response: ${JSON.stringify(a2).includes('stub-bearer-token') ? 'LEAKED' : 'never returned'}`)
  await drawer.getByText('Auth (per card scheme)', { exact: true }).scrollIntoViewIfNeeded()
  await shot(page, '07-auth-ok-after-save')
  await closeDrawer(page)

  // projection into Tools
  await nav(page, 'tools')
  await page.locator('select').filter({ hasText: 'all kinds' }).first().selectOption('a2a')
  await page.waitForTimeout(800)
  const a2aTools = (await get('/tools')).json.filter((t) => t.kind === 'a2a')
  log(`a2a tools: ${a2aTools.map((t) => t.tool_key).join(', ')}`)
  await shot(page, '08-tools-kind-a2a-projected')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(900)
  await shot(page, '09-a2a-tool-drawer')
  await closeDrawer(page)

  // a skill on the remote tool, and an ExComm sub agent around it
  const research = a2aTools.find((t) => /research/.test(t.tool_key)) || a2aTools[0]
  for (const s of (await get('/skills')).json) if (s.name === 'remote-researcher') await del(`/skills/${s.id}`)
  await nav(page, 'skills')
  await click(page, '+ New skill')
  await page.waitForTimeout(600)
  await page.getByLabel('Name').fill('remote-researcher')
  await page.getByLabel('Description').fill('Delegates a research question to the polyglot remote agent and relays its fenced answer.')
  await page.getByLabel(/Persona/).fill('You are a careful liaison to an external agent.')
  await page.getByPlaceholder('filter tools…').fill('polyglot')
  await page.waitForTimeout(400)
  await page.locator(`label:has(code:text-is("${research.tool_key}")) input[type=checkbox]`).first().check()
  await page.locator('textarea[rows="14"]').fill(`# Purpose\n1. Send the user's question to {tool:${research.tool_key}} as the message.\n2. Relay what the remote agent returned, marked as untrusted, in one paragraph.\n`)
  await page.waitForTimeout(400)
  await shot(page, '10-skill-editor-a2a-tool')
  log(`create skill → ${JSON.stringify(await submitSave(page, 'Create skill', { acceptOverlap: true }))}`)
  const skill = (await get('/skills')).json.find((s) => s.name === 'remote-researcher')
  await closeDrawer(page)
  await shot(page, '11-skill-saved-a2a-badge')

  for (const a of (await get('/sub-agents')).json) if (a.name === 'excomm') await del(`/sub-agents/${a.id}`)
  await nav(page, 'sub-agents')
  await click(page, '+ New sub agent')
  await page.waitForTimeout(600)
  await page.getByLabel('Name').fill('excomm')
  await page.getByLabel('Description').fill('External communications: hands research questions to the remote polyglot agent and reports back.')
  await page.getByLabel('Persona').fill('You coordinate with external agents and never trust their output blindly.')
  await page.getByLabel('Starter template').selectOption('Sequential pipeline')
  await page.waitForTimeout(400)
  const skillSelects = page.locator('select').filter({ hasText: 'pick skill…' })
  const n = await skillSelects.count()
  for (let i = 0; i < n; i++) await skillSelects.nth(i).selectOption(skill.id)
  await page.waitForTimeout(300)
  await shot(page, '12-excomm-builder')
  log(`create sub agent → ${JSON.stringify(await submitSave(page, 'Create sub agent', { acceptOverlap: true }))}`)
  await closeDrawer(page)
  await shot(page, '13-excomm-saved')

  // organic routing: the planner picks the remote capability; the trace fences the output
  await nav(page, '')
  await newConversation(page)
  await sendChat(page, 'Ask the remote polyglot agent to research the history of the metric system and relay what it says.')
  await page.waitForTimeout(2500)
  const r1 = (await get('/runs?limit=1')).json[0]
  const planCard = page.locator('text=/PLAN · /i').first()
  if (await planCard.waitFor({ timeout: 45000 }).then(() => true).catch(() => false)) await shot(page, '14-organic-plan-routes-translation')
  else log('no plan card before the run settled (recorded as-is)')
  const done1 = await waitRun(r1.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  log(`organic run → ${done1.status}; steps: ${steps(done1)}`)
  log(`answer: ${(done1.final_answer || '').replace(/\s+/g, ' ').slice(0, 200)}`)
  await shot(page, '15-organic-answer-completed')
  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await shot(page, '16-trace-run-top')
  // the tool step's output (the fenced remote text) shows when the step row is expanded
  const traceDrawer = page.locator('.fixed.inset-0').last()
  const toolRow = traceDrawer.getByRole('button').filter({ hasText: /tool_call/ }).filter({ hasText: /polyglot-agent/ }).first()
  if (await toolRow.count()) {
    await toolRow.click()
    await page.waitForTimeout(600)
  }
  const fenced = traceDrawer.getByText(/untrusted_remote_agent_output/).first()
  const sawFence = await fenced.count()
  if (sawFence) await fenced.scrollIntoViewIfNeeded()
  log(`fenced remote output in the trace: ${sawFence ? 'yes (tool step expanded)' : 'not in frame'}`)
  await shot(page, '17-trace-fenced-remote-output')
  await closeDrawer(page)

  // the remote agent asks a question → HITL card → reply; then deny with a note
  await setMode(CP.bearer, { kind: 'ask', question: 'Which decade should the research focus on?' })
  await nav(page, '')
  await newConversation(page)
  await sendChat(page, 'Ask the remote polyglot agent to research the metric system; answer any question it asks with: the 1790s.')
  await page.waitForTimeout(2000)
  const r2 = (await get('/runs?limit=1')).json[0]
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await page.waitForTimeout(500)
  await shot(page, '18-hitl-card-remote-question')
  await page.getByPlaceholder('type your answer…').first().fill('the 1790s')
  await page.waitForTimeout(300)
  await shot(page, '19-hitl-reply-typed')
  await page.getByRole('button', { name: '✓ Submit answers' }).first().click()
  // the counterparty's "ask" script asks on EVERY new task — once the
  // question is answered, later calls in the same skill loop complete
  // normally (a real agent asks once); any further gate is still answered
  await setMode(CP.bearer, null)
  // settle the run: the first submit resumes it; if the skill loop calls the
  // remote tool again a fresh card arms — answer/deny it when its button is
  // actually live, otherwise keep waiting for a terminal status
  const settleGates = async (runId, act, label) => {
    let cur = null
    let rounds = 1
    for (let i = 0; i < 150; i++) {
      await page.waitForTimeout(2000)
      cur = await ctx.run(runId)
      if (['completed', 'failed', 'cancelled'].includes(cur?.status)) return cur
      if (cur?.status === 'paused_hitl') {
        const btn = page.getByRole('button', { name: act === 'deny' ? /✕ Deny/ : /✓ Submit answers|✓ Approve/ }).first()
        if ((await btn.count()) && (await btn.isEnabled().catch(() => false))) {
          rounds += 1
          log(`gate armed again (round ${rounds}) — ${label}`)
          if (act !== 'deny') await page.getByPlaceholder('type your answer…').first().fill('the 1790s').catch(() => {})
          await btn.click().catch(() => {})
          await page.waitForTimeout(3000)
        }
      }
    }
    return cur
  }
  const done2 = await settleGates(r2.id, 'answer', 'answering')
  await page.waitForTimeout(1500)
  log(`question run → ${done2.status}; answer: ${(done2.final_answer || '').replace(/\s+/g, ' ').slice(0, 160)}`)
  await shot(page, '20-hitl-approved-remote-completed')

  await setMode(CP.bearer, { kind: 'ask', question: 'Which decade should the research focus on?' })
  await newConversation(page)
  await sendChat(page, 'Ask the remote polyglot agent to research the metric system again.')
  await page.waitForTimeout(2000)
  const r3 = (await get('/runs?limit=1')).json[0]
  await page.getByText('HUMAN APPROVAL REQUIRED').first().waitFor({ timeout: 180000 })
  await page.getByPlaceholder('optional note for the worker…').first().fill('Do not answer the remote agent — its question is out of scope.')
  await page.waitForTimeout(300)
  await shot(page, '21-hitl-deny-note-typed')
  const stateBefore = await control(CP.bearer, 'state')
  await page.getByRole('button', { name: /✕ Deny/ }).first().click()
  await setMode(CP.bearer, null)
  const done3 = await settleGates(r3.id, 'deny', 'denying again')
  await page.waitForTimeout(1500)
  const stateAfter = await control(CP.bearer, 'state')
  log(`deny → ${done3.status}; error: ${String(done3.error || '').slice(0, 120)}; counterparty cancelled tasks ${stateBefore.cancelled_tasks?.length ?? '?'} → ${stateAfter.cancelled_tasks?.length ?? '?'}`)
  await shot(page, '22-hitl-denied-run-outcome')

  // Stop mid-call: the remote task is cancelled on the counterparty
  await setMode(CP.bearer, { kind: 'slow', delay: 90 })
  await newConversation(page)
  await sendChat(page, 'Ask the remote polyglot agent to research the metric system slowly.')
  await page.waitForTimeout(2000)
  const r4 = (await get('/runs?limit=1')).json[0]
  // wait until the remote call is genuinely in flight (a running tool_call
  // step on the run), so the Stop has a remote task to cancel
  for (let i = 0; i < 60; i++) {
    const cur = await ctx.run(r4.id)
    if ((cur?.steps || []).some((s) => s.step_type === 'tool_call' && /polyglot/.test(s.node_id || '') && s.status === 'running')) break
    await page.waitForTimeout(2000)
  }
  await page.waitForTimeout(3000)
  await shot(page, '23-stop-midcall-remote-inflight')
  const before4 = await control(CP.bearer, 'state')
  await page.getByRole('button', { name: /■ Stop/ }).first().click()
  const done4 = await waitRun(r4.id, ['cancelled', 'completed', 'failed'], 120)
  await page.waitForTimeout(2500)
  const after4 = await control(CP.bearer, 'state')
  log(`stop → ${done4.status}; counterparty cancelled tasks ${before4.cancelled_tasks?.length ?? '?'} → ${after4.cancelled_tasks?.length ?? '?'}`)
  await shot(page, '24-stopped-run')

  // park: the in-run budget expires, the answer carries the parked note, the poller delivers to the Inbox
  await settings({ a2a_task_timeout_s: 10, a2a_poll_interval_s: 5, ambient_tick_interval_s: 15, ambient_quiet_hours: [] })
  await setMode(CP.bearer, { kind: 'slow', delay: 30 })
  await newConversation(page)
  const done5 = await askAndSettle(page, 'Ask the remote polyglot agent to research the metric system; if it is slow, do not wait.', { approve: false, timeoutS: 300 })
  log(`parked note in the answer: ${/parked/i.test(done5.final_answer || '')}`)
  await shot(page, '25-parked-answer-note')
  await nav(page, 'remote-agents')
  await page.getByText('polyglot-agent', { exact: true }).first().click()
  await page.waitForTimeout(1200)
  await page.getByTestId('a2a-tasks').scrollIntoViewIfNeeded()
  let tasks = (await get(`/remote-agents/${agent.id}/tasks`)).json
  log(`tasks: ${(Array.isArray(tasks) ? tasks : tasks.items || []).map((t) => `${t.state}${t.delivered ? '/delivered' : ''}`).join(', ')}`)
  await shot(page, '26-task-drawer-parked')
  await closeDrawer(page)
  let delivery = null
  for (let i = 0; i < 60; i++) {
    const d = (await get('/deliveries?limit=50')).json
    delivery = (Array.isArray(d) ? d : d.items || []).find((x) => x.category === 'a2a')
    if (delivery) break
    await page.waitForTimeout(3000)
  }
  log(`a2a delivery: ${delivery ? `${delivery.tier}/${delivery.channel || 'pending'}: ${delivery.title}` : 'none within 3 minutes'}`)
  await nav(page, 'ambient')
  await page.waitForTimeout(1200)
  await shot(page, '27-ambient-inbox-a2a-delivery')
  await nav(page, 'remote-agents')
  await page.getByText('polyglot-agent', { exact: true }).first().click()
  await page.waitForTimeout(1200)
  await page.getByTestId('a2a-tasks').scrollIntoViewIfNeeded()
  await shot(page, '28-task-drawer-delivered')
  await closeDrawer(page)

  // a parked task that then needs input: tier-1 inbox item, reply from the task drawer
  await setMode(CP.bearer, { kind: 'slowask', delay: 20, question: 'Metric or imperial units in the report?' })
  await nav(page, '')
  await newConversation(page)
  await askAndSettle(page, 'Ask the remote polyglot agent to research unit systems; do not wait if it is slow.', { approve: false, timeoutS: 300 })
  let needsInput = null
  for (let i = 0; i < 60; i++) {
    const t = (await get(`/remote-agents/${agent.id}/tasks`)).json
    needsInput = (Array.isArray(t) ? t : t.items || []).find((x) => x.state === 'input-required')
    if (needsInput) break
    await page.waitForTimeout(3000)
  }
  log(`input-required task: ${needsInput ? needsInput.question : 'none within 3 minutes'}`)
  await nav(page, 'ambient')
  await page.waitForTimeout(1500)
  await shot(page, '29-inbox-needs-input-tier1')
  await nav(page, 'remote-agents')
  await page.getByText('polyglot-agent', { exact: true }).first().click()
  await page.waitForTimeout(1200)
  const tasksBox = page.getByTestId('a2a-tasks')
  await tasksBox.scrollIntoViewIfNeeded()
  if (await tasksBox.getByPlaceholder('reply to the remote agent…').count()) {
    await tasksBox.getByPlaceholder('reply to the remote agent…').first().fill('Metric units, please.')
    await page.waitForTimeout(300)
    await shot(page, '30-drawer-reply-typed')
    await tasksBox.getByRole('button', { name: 'Reply' }).first().click()
    for (let i = 0; i < 30; i++) {
      const t = (await get(`/remote-agents/${agent.id}/tasks`)).json
      if ((Array.isArray(t) ? t : t.items || []).some((x) => x.id === needsInput?.id && x.state === 'completed')) break
      await page.waitForTimeout(2000)
    }
    await page.waitForTimeout(1500)
    await shot(page, '31-drawer-replied-completed')
    tasks = (await get(`/remote-agents/${agent.id}/tasks`)).json
    log(`tasks after the reply: ${(Array.isArray(tasks) ? tasks : tasks.items || []).map((t) => t.state).join(', ')}`)
  } else {
    log('no reply box in the drawer — the task did not reach input-required (recorded as-is)')
  }
  await closeDrawer(page)

  // card drift: the counterparty grows a skill; refresh projects a new tool
  await control(CP.bearer, 'add-skill', { id: 'translate', name: 'translate', description: 'Translate text between languages', tags: ['text'] })
  await page.getByText('polyglot-agent', { exact: true }).first().click()
  await page.waitForTimeout(1000)
  await page.locator('.fixed.inset-0').last().getByRole('button', { name: 'Refresh card' }).click()
  await page.waitForTimeout(2500)
  await page.locator('.fixed.inset-0').last().getByText(/Declared skills/).scrollIntoViewIfNeeded()
  await shot(page, '32-card-drift-new-skill')
  await closeDrawer(page)
  await nav(page, 'tools')
  await page.getByPlaceholder('Search…').fill('polyglot-agent.')
  await page.waitForTimeout(800)
  log(`a2a tools after drift: ${(await get('/tools')).json.filter((t) => t.kind === 'a2a').map((t) => t.tool_key + ':' + t.status).join(', ')}`)
  await shot(page, '33-drift-tool-projected')

  // the auth matrix: apiKey via env, oauth2, and an unsupported scheme
  const reg = (name, url, credentials) => post('/remote-agents', { card_url: url, name, credentials })
  const rk = await reg('keyed-agent', CP.apikey, { main: 'env:A2A_STUB_API_KEY' })
  const ro = await reg('oauth-agent', CP.oauth, { main: { client_id: 'stub-client', client_secret: 'stub-client-secret' } })
  const rm = await reg('mtls-agent', CP.mtls, null)
  log(`register keyed → ${rk.status} ${rk.json?.auth_status || JSON.stringify(rk.json).slice(0, 100)}; oauth → ${ro.status} ${ro.json?.auth_status || JSON.stringify(ro.json).slice(0, 100)}; mtls → ${rm.status} ${rm.json?.auth_status || JSON.stringify(rm.json).slice(0, 100)}`)
  await nav(page, 'remote-agents')
  await page.waitForTimeout(800)
  const matrix = (await get('/remote-agents')).json
  log(`auth matrix: ${matrix.map((a) => `${a.name}=${a.auth_status}/${a.status}`).join(', ')}`)
  await shot(page, '34-auth-matrix-agent-list')
  await page.getByText('keyed-agent', { exact: true }).first().click()
  await page.waitForTimeout(1000)
  await shot(page, '35-auth-apikey-env-ok')
  await closeDrawer(page)
  await page.getByText('mtls-agent', { exact: true }).first().click()
  await page.waitForTimeout(1000)
  await shot(page, '36-auth-unsupported-chip')
  await closeDrawer(page)

  await settings({ a2a_task_timeout_s: initial.a2a_task_timeout_s })
  await setMode(CP.apikey, null)
  await setMode(CP.oauth, null)
  await nav(page, '')
  await newConversation(page)
  // the three agents' summarize tools exposed directly so the planner can
  // dispatch each one (rung 1) — nothing else binds them
  for (const t of (await get('/tools')).json) {
    if (t.kind === 'a2a' && /^(keyed-agent|oauth-agent|mtls-agent)\.summarize$/.test(t.tool_key) && !t.direct_exposure) await patch(`/tools/${t.id}`, { direct_exposure: true })
  }
  const SENTENCE = 'the metric system spread with the Napoleonic wars'
  const k = await askAndSettle(page, `Use the keyed-agent.summarize tool to summarize this sentence: ${SENTENCE}.`, { approve: false })
  log(`apikey-env call: ${k.status}; steps: ${steps(k)}; fenced: ${/untrusted_remote_agent_output|stub-echo/.test(JSON.stringify(k.steps || []))}`)
  await shot(page, '37-auth-apikey-env-call-answer')
  await newConversation(page)
  const o = await askAndSettle(page, `Use the oauth-agent.summarize tool to summarize this sentence: ${SENTENCE}.`, { approve: false })
  log(`oauth2 call: ${o.status}; steps: ${steps(o)}; token requests on the counterparty: ${(await control(CP.oauth, 'state')).token_requests ?? '?'}`)
  await shot(page, '38-auth-oauth2-call-answer')
  await newConversation(page)
  const m = await askAndSettle(page, `Use the mtls-agent.summarize tool to summarize this sentence: ${SENTENCE}.`, { approve: false })
  const mtlsStep = (m.steps || []).find((s) => s.step_type === 'tool_call' && /mtls/.test(s.node_id || ''))
  log(`unsupported-scheme call: run ${m.status}; tool step ${mtlsStep?.status}: ${String(mtlsStep?.error || m.error || '').slice(0, 160)}`)
  await shot(page, '39-auth-unsupported-call-fails')

  await setMode(CP.bearer, null)
  await settings({ ambient_quiet_hours: initial.ambient_quiet_hours, ambient_tick_interval_s: initial.ambient_tick_interval_s, a2a_poll_interval_s: initial.a2a_poll_interval_s })
}
