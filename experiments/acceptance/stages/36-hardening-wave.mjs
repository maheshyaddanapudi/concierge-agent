// Stage 36 — the hardening wave: the run trace reads against the registry
// AS IT WAS (§3.6), a bound tool the loop cannot call is flagged on the
// Skills list (§8.3), an operator's tool description survives a re-ingest
// (§3.2), and the judges get their own roles in Settings (§8.7: the
// registry overlap audit gate, the eval judge model, the salience hint).
// Uses the seeded `demo-stub` MCP server (the M56 ceremony registers it).
export default async function ({ page, nav, shot, get, post, patch, del, log, settings, closeDrawer, newConversation, askAndSettle }) {
  const before = await settings()
  await settings({ orchestrator_mode: 'graph', formatter_enabled: true, evals_enabled: true, ambient_enabled: true, ambient_salience_model: null, eval_judge_model: null, eval_judge_model_params: null, registry_overlap_audit_enabled: false })

  // ── the stub server's echo tool, bound to a skill of this stage ──
  const servers = (await get('/mcp-servers')).json
  const stub = servers.find((s) => s.name === 'demo-stub')
  if (!stub) throw new Error('demo-stub MCP server not registered (the M56 ceremony registers it)')
  const tools = async () => (await get('/tools?limit=300')).json
  let echo = (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
  if (!echo) throw new Error('demo-stub.echo not ingested')
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
  if (created.status !== 201) throw new Error(`POST /skills ${created.status}: ${JSON.stringify(created.json)}`)
  const skill = created.json
  log(`skill ${skill.name} created: definition v${skill.definition_version} hash=${(skill.definition_hash || '').slice(0, 12)}`)

  try {
    // ── an operator's wording survives a re-ingest (§3.2 description drift) ──
    log(`demo-stub.echo description before: ${JSON.stringify(echo.description)} source=${echo.description_source}`)
    const edited = (await patch(`/tools/${echo.id}`, { description: 'Operator: echoes the given word back — never anything else.' })).json
    log(`operator edit: source=${edited.description_source} hash=${(edited.description_hash || '').slice(0, 12)}`)
    await post(`/mcp-servers/${stub.id}/refresh-tools`)
    await new Promise((r) => setTimeout(r, 2500))
    echo = (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
    log(`after refresh-tools: description=${JSON.stringify(echo.description)} source=${echo.description_source} (the server's wording did not overwrite the operator's)`)
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
    const snap = run.snapshot || {}
    log(`snapshot keys: ${Object.keys(snap).join(', ')}`)
    log(`snapshot.settings.default_model=${snap.settings?.default_model} prompts=${Object.keys(snap.prompts || {}).length} files, context surfaces=${(snap.context || []).map((c) => c.surface).join(',')}, catalog_calls=${(snap.catalog_calls || []).length}`)
    log(`cost: $${run.cost_usd} priced=${run.cost_priced} price_snapshot=${JSON.stringify(run.price_snapshot).slice(0, 200)}`)
    await nav(page, 'runs')
    await page.locator('table tbody tr').first().click()
    await page.waitForTimeout(1200)
    await shot(page, '01-trace-entity-names-and-format-step')
    let panel = page.getByTestId('snapshot-panel')
    await panel.scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await shot(page, '02-snapshot-vs-registry-all-same')
    log(`panel status: ${await panel.getByRole('status').textContent()}`)
    await panel.getByText(/show settings as the run saw them/).click()
    await page.waitForTimeout(400)
    await shot(page, '03-snapshot-settings-and-prompts')
    await closeDrawer(page)

    // ── the definition moves after the run: the same trace says so ──
    const bumped = (await patch(`/skills/${skill.id}`, { instructions: skill.instructions + '\n3. Never add commentary.' })).json
    log(`skill edited: definition v${bumped.definition_version} hash=${(bumped.definition_hash || '').slice(0, 12)} (a toggle would not have bumped it)`)
    await nav(page, 'runs')
    await page.locator('table tbody tr').first().click()
    await page.waitForTimeout(1200)
    panel = page.getByTestId('snapshot-panel')
    await panel.scrollIntoViewIfNeeded()
    await page.waitForTimeout(400)
    await shot(page, '04-snapshot-vs-registry-skill-changed')
    log(`panel status after the edit: ${await panel.getByRole('status').textContent()}`)
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
    log(`skills badge: ${await page.getByRole('status').first().textContent().catch(() => '(none)')}`)
    await patch(`/tools/${echo.id}`, { status: 'active' })

    // ── Settings: the judges' own roles ──
    await nav(page, 'settings')
    const audit = page.getByRole('switch', { name: 'Registry overlap audit' })
    await audit.scrollIntoViewIfNeeded()
    await shot(page, '06-settings-registry-overlap-audit-off')
    await audit.click()
    await page.waitForTimeout(900)
    log(`registry_overlap_audit_enabled via API: ${(await get('/settings')).json.registry_overlap_audit_enabled}`)
    await shot(page, '07-settings-registry-overlap-audit-on')
    const judge = page.getByRole('combobox', { name: 'Eval judge model' })
    await judge.scrollIntoViewIfNeeded()
    await shot(page, '08-settings-eval-judge-inherits')
    const options = await judge.locator('option').allTextContents()
    const other = options.find((o) => /openrouter:/.test(o) && !/3\.8-max/.test(o)) || options.find((o) => /openrouter:/.test(o))
    if (other) {
      await judge.selectOption({ label: other })
      await page.waitForTimeout(900)
      log(`eval_judge_model via API: ${(await get('/settings')).json.eval_judge_model}`)
      await shot(page, '09-settings-eval-judge-model')
    }
    const salience = page.getByRole('combobox', { name: 'Salience judge model' })
    await salience.scrollIntoViewIfNeeded()
    await shot(page, '10-settings-salience-judge-hint')
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
    })
    log('restored: the stage skill deleted, echo active, settings as before, audit off, eval judge default')
  }
}
