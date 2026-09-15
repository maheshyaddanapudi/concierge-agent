// Stage 36 — the hardening wave: the run trace reads against the registry
// AS IT WAS (§3.6), a bound tool the loop cannot call is flagged on the
// Skills list (§8.3), an operator's tool description survives a re-ingest
// (§3.2), and the judges get their own roles in Settings (§8.7: the
// registry overlap audit gate, the eval judge model, the salience hint).
// Uses a `demo-stub` MCP server, which this stage registers itself — nothing
// in the repository seeds one, despite what this comment used to claim.
export default async function ({ page, nav, shot, get, post, patch, del, log, settings, closeDrawer, newConversation, askAndSettle, ensureStubServer, expect, expectEq, expectHttp, expectMatch, expectStatus }) {
  const before = await settings()
  await settings({ orchestrator_mode: 'graph', formatter_enabled: true, evals_enabled: true, ambient_enabled: true, ambient_salience_model: null, eval_judge_model: null, eval_judge_model_params: null, registry_overlap_audit_enabled: false })

  // ── the stub server's echo tool, bound to a skill of this stage ──
  // registered here if absent — nothing in the repository seeds `demo-stub`
  // (see ensureStubServer in lib.mjs)
  const stub = await ensureStubServer('demo-stub')
  expect(!!stub, 'the demo-stub MCP server is available')
  const tools = async () => (await get('/tools?limit=300')).json
  let echo = (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
  expect(!!echo, 'demo-stub.echo is ingested')
  if (echo.status !== 'active') await patch(`/tools/${echo.id}`, { status: 'active' })
  if (echo.description_source === 'operator') {
    // a previous pass left the operator's wording: hand it back to the server first
    await patch(`/tools/${echo.id}`, { description_source: 'server' })
    await post(`/mcp-servers/${stub.id}/refresh-tools`)
    await new Promise((r) => setTimeout(r, 2500))
    echo = (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
  }
  const created = await post('/skills', {
    name: 'hw-echo-skill',
    description: 'Echoes a word back through the demo-stub echo tool (hardening-wave stage)',
    persona: 'You echo exactly what you are asked to echo, using the echo tool.',
    instructions: `## Steps\n1. Call {tool:demo-stub.echo} with the word the user gives.\n2. Reply with the tool's output verbatim.`,
    tool_ids: [echo.id],
    direct_exposure: true,
  })
  expectHttp(created, 201, 'the stage skill was created')
  const skill = created.json
  log(`skill ${skill.name} created: definition v${skill.definition_version} hash=${(skill.definition_hash || '').slice(0, 12)}`)

  try {
    // ── an operator's wording survives a re-ingest (§3.2 description drift) ──
    log(`demo-stub.echo description before: ${JSON.stringify(echo.description)} source=${echo.description_source}`)
    const edited = (await patch(`/tools/${echo.id}`, { description: 'Operator: echoes the given word back — never anything else.' })).json
    log(`operator edit: source=${edited.description_source} hash=${(edited.description_hash || '').slice(0, 12)}`)
    expectEq(edited.description_source, 'operator', "the edit marked the description as the operator's")
    await post(`/mcp-servers/${stub.id}/refresh-tools`)
    await new Promise((r) => setTimeout(r, 2500))
    echo = (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
    log(`after refresh-tools: description=${JSON.stringify(echo.description)} source=${echo.description_source} (the server's wording did not overwrite the operator's)`)
    // §3.2: a re-ingest must NOT overwrite an operator's wording
    expectEq(echo.description_source, 'operator', "the re-ingest left the description as the operator's")
    expectMatch(echo.description, /^Operator:/, "…and the operator's text survived verbatim")
    await nav(page, 'tools')
    const search = page.getByPlaceholder(/search/i).first()
    await search.fill('demo-stub.echo')
    await page.waitForTimeout(700)
    await page.getByText(/^demo-stub\.echo$/).first().click()
    await page.waitForTimeout(800)
    await shot(page, '00-tool-operator-description-after-reingest')
    await closeDrawer(page)

    // ── a run through the skill: entity names, the format step, the pinned versions ──
    await nav(page, '')
    await newConversation(page)
    const run = await askAndSettle(page, 'Use the hw-echo-skill skill to echo the word pinned.', { approve: false, timeoutS: 240 })
    const skillSteps = (run.steps || []).filter((s) => s.step_type === 'skill')
    const fmt = (run.steps || []).find((s) => s.step_type === 'format')
    log(`skill steps: ${skillSteps.map((s) => `${s.entity_name}@def v${s.entity_version} model=${s.model} params=${JSON.stringify(s.model_params)}`).join(' | ')}`)
    log(`format step: ${fmt ? `model=${fmt.model} params=${JSON.stringify(fmt.model_params)} output=${JSON.stringify(fmt.output)}` : '(none — did the formatter run?)'}`)
    // the trace names the entity and the definition version it ran against
    expectStatus(run, 'completed', 'the run through the stage skill')
    expect(skillSteps.length > 0, 'the trace has a skill step')
    expectEq(skillSteps[0]?.entity_name, 'hw-echo-skill', 'named for the skill that ran')
    expectEq(skillSteps[0]?.entity_version, skill.definition_version, 'pinned to the definition version it ran against')
    expect(!!fmt, 'the formatter ran and left its own step')
    const snap = run.snapshot || {}
    log(`snapshot keys: ${Object.keys(snap).join(', ')}`)
    log(`snapshot.settings.default_model=${snap.settings?.default_model} prompts=${Object.keys(snap.prompts || {}).length} files, context surfaces=${(snap.context || []).map((c) => c.surface).join(',')}, catalog_calls=${(snap.catalog_calls || []).length}`)
    // §3.6: the run carries the settings and prompts it actually used
    expect(!!snap.settings?.default_model, 'the run snapshot records the model it ran on')
    expect(Object.keys(snap.prompts || {}).length > 0, '…and the prompt files as they were')
    log(`cost: $${run.cost_usd} priced=${run.cost_priced} price_snapshot=${JSON.stringify(run.price_snapshot).slice(0, 200)}`)
    await nav(page, 'runs')
    await page.locator('table tbody tr').first().click()
    await page.waitForTimeout(1200)
    await shot(page, '01-trace-entity-names-and-format-step')
    let panel = page.getByTestId('snapshot-panel')
    await panel.scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await shot(page, '02-snapshot-vs-registry-all-same')
    const panelStatus = (await panel.getByRole('status').textContent()) || ''
    log(`panel status: ${panelStatus}`)
    // nothing has changed yet, so the panel must say the registry still matches
    expectMatch(panelStatus, /same|match|unchanged/i, 'the Snapshot vs registry panel reports no drift before the edit')
    await panel.getByText(/show settings as the run saw them/).click()
    await page.waitForTimeout(400)
    await shot(page, '03-snapshot-settings-and-prompts')
    await closeDrawer(page)

    // ── the definition moves after the run: the same trace says so ──
    const bumped = (await patch(`/skills/${skill.id}`, { instructions: skill.instructions + '\n3. Never add commentary.' })).json
    log(`skill edited: definition v${bumped.definition_version} hash=${(bumped.definition_hash || '').slice(0, 12)} (a toggle would not have bumped it)`)
    expect(bumped.definition_version > skill.definition_version, 'editing the instructions bumped the definition version')
    await nav(page, 'runs')
    await page.locator('table tbody tr').first().click()
    await page.waitForTimeout(1200)
    panel = page.getByTestId('snapshot-panel')
    await panel.scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await shot(page, '04-snapshot-vs-registry-skill-changed')
    const panelAfter = (await panel.getByRole('status').textContent()) || ''
    log(`panel status after the edit: ${panelAfter}`)
    // the same trace, read after the registry moved, must SAY the registry moved
    expect(panelAfter !== panelStatus, 'the panel now reports the registry has changed under the run')
    // `moved` too: the panel's own wording is "1 of 2 pinned records MOVED
    // since this run", which reports the drift precisely — it was the
    // assertion's vocabulary that was short, not the panel's.
    expectMatch(panelAfter, /chang|differ|drift|moved/i, '…and says so in words')
    const rows = await panel.locator('tbody tr').allTextContents()
    log(`panel rows: ${rows.map((r) => r.replace(/\s+/g, ' ').trim()).join(' || ')}`)
    await closeDrawer(page)

    // ── a bound tool the loop cannot call: the Skills list says so ──
    await patch(`/tools/${echo.id}`, { status: 'inactive' })
    await nav(page, 'skills')
    const ssearch = page.getByPlaceholder(/search/i).first()
    await ssearch.fill('hw-echo-skill')
    await page.waitForTimeout(700)
    await shot(page, '05-skills-bound-tool-unavailable')
    const badge = (await page.getByRole('status').first().textContent()) || ''
    log(`skills badge: ${badge}`)
    // §8.3: a skill bound to a tool the loop cannot call says so on the list
    expectMatch(badge, /unavailable|inactive|cannot|missing/i, 'the Skills list flags the unavailable bound tool')
    await patch(`/tools/${echo.id}`, { status: 'active' })

    // ── Settings: the judges' own roles ──
    await nav(page, 'settings')
    const audit = page.getByRole('switch', { name: 'Registry overlap audit' })
    await audit.scrollIntoViewIfNeeded()
    await shot(page, '06-settings-registry-overlap-audit-off')
    await audit.click()
    await page.waitForTimeout(900)
    expectEq((await get('/settings')).json.registry_overlap_audit_enabled, true, 'the registry overlap audit gate toggled on')
    await shot(page, '07-settings-registry-overlap-audit-on')
    const judge = page.getByRole('combobox', { name: 'Eval judge model' })
    await judge.scrollIntoViewIfNeeded()
    await shot(page, '08-settings-eval-judge-inherits')
    const options = await judge.locator('option').allTextContents()
    const other = options.find((o) => /openrouter:/.test(o) && !/3\.8-max/.test(o)) || options.find((o) => /openrouter:/.test(o))
    if (other) {
      await judge.selectOption({ label: other })
      await page.waitForTimeout(900)
      expectEq((await get('/settings')).json.eval_judge_model, other, "the eval judge's own model role was set")
      await shot(page, '09-settings-eval-judge-model')
    }
    const salience = page.getByRole('combobox', { name: 'Salience judge model' })
    await salience.scrollIntoViewIfNeeded()
    await shot(page, '10-settings-salience-judge-hint')

    // ── a judge that did not run is a distinct state, never a silent 0% ──
    // (third reading, named by a reader): the overlap judge given a one-token
    // output budget (the settings API refuses a model that is not on the
    // provider's list), so its structured verdict cannot parse and the
    // judge is unavailable; a skill saved through the UI goes through and
    // says so
    const live = (await get('/settings')).json.default_model
    await settings({ overlap_judge_model: live, overlap_judge_model_params: { max_output_tokens: 1 } })
    const probe = (await post('/skills/check-overlap', { name: 'probe', description: 'x', instructions: 'y', tool_ids: [] })).json
    log(`check-overlap with the judge down: judge_available=${probe.judge_available} overlap_percent=${probe.overlap_percent} reasoning=${String(probe.reasoning).slice(0, 90)}`)
    // the whole point: a judge that did NOT run is its own state, never a
    // silent 0% that reads like a clean verdict
    expectEq(probe.judge_available, false, 'the unavailable judge is reported as unavailable')
    expect(probe.overlap_percent == null, '…and no 0% verdict is invented in its place')
    await patch(`/tools/${echo.id}`, { status: 'active' })
    await nav(page, 'skills')
    const ssearch2 = page.getByPlaceholder(/search/i).first()
    await ssearch2.fill('hw-echo-skill')
    await page.waitForTimeout(700)
    await page.getByText('hw-echo-skill', { exact: true }).first().click()
    await page.waitForTimeout(800)
    await page.getByRole('button', { name: 'Save skill' }).first().click()
    const notice = page.getByRole('status').filter({ hasText: /Saved unjudged/ }).first()
    await notice.waitFor({ timeout: 30000 })
    const unjudged = ((await notice.textContent()) || '').replace(/\s+/g, ' ').trim()
    log(`after Save with the judge down: ${unjudged}`)
    expectMatch(unjudged, /Saved unjudged/, 'the save went through and said plainly that it was unjudged')
    await shot(page, '11-skill-saved-unjudged-judge-down')
    await settings({ overlap_judge_model: null, overlap_judge_model_params: null })
  } finally {
    // ── restore ──
    await del(`/skills/${skill.id}`)
    await patch(`/tools/${echo.id}`, { status: 'active' })
    await settings({
      formatter_enabled: before.formatter_enabled,
      evals_enabled: before.evals_enabled,
      ambient_enabled: before.ambient_enabled,
      eval_judge_model: null,
      eval_judge_model_params: null,
      registry_overlap_audit_enabled: false,
      overlap_judge_model: null,
      overlap_judge_model_params: null,
    })
    log('restored: the stage skill deleted, echo active, settings as before, audit off, eval and overlap judges default')
  }
}
