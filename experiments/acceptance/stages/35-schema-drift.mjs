// Stage 35 — tool schema drift (spec §3.2) and the registry pinned into the
// run (§3.6), the overlap judge's own model role (§3.7). A `demo-stub` MCP
// server, registered by this stage (nothing seeds one, despite what this
// comment used to claim), runs the repo's test stub, which
// rename `echo`'s parameter at runtime through its `mutate_schema` tool: a
// live run calls that tool, the server notifies listChanged, the re-ingest
// versions the change, and the Tools page, the drawer, the trace and Settings
// each show their side of it. Then the same change under the quarantine
// policy, acknowledged from the drawer.
export default async function ({ page, nav, shot, get, post, patch, log, settings, closeDrawer, newConversation, askAndSettle, waitRun, ensureStubServer, expect, expectEq }) {
  await settings({ orchestrator_mode: 'graph', mcp_schema_change_policy: 'warn', overlap_judge_model: null, overlap_judge_model_params: null })

  // ── the stub server, reconnected so the stub (with mutate_schema) is running ──
  // registered here if absent: nothing in the repository seeds `demo-stub`,
  // so asserting it was already there could only ever fail (see
  // ensureStubServer in lib.mjs)
  const stub = await ensureStubServer('demo-stub')
  expect(!!stub, 'the demo-stub MCP server is available')
  await post(`/mcp-servers/${stub.id}/reconnect`)
  await new Promise((r) => setTimeout(r, 3000))
  const tools = async () => (await get('/tools?limit=300')).json.filter((t) => t.tool_key.startsWith('demo-stub.'))
  const echoTool = async () => (await tools()).find((t) => t.tool_key === 'demo-stub.echo')
  const mutator = (await tools()).find((t) => t.tool_key === 'demo-stub.mutate_schema')
  expect(!!mutator, 'demo-stub.mutate_schema was ingested — is the image built from this commit?')
  let echo = await echoTool()
  log(`demo-stub.echo before: schema v${echo.schema_version} hash=${(echo.schema_hash || '').slice(0, 12)} params=${Object.keys(echo.input_schema?.properties || {})} changed_at=${echo.schema_changed_at}`)
  for (const t of [mutator, echo]) if (!t.direct_exposure) await patch(`/tools/${t.id}`, { direct_exposure: true })
  if (echo.schema_changed_at) await post(`/tools/${echo.id}/acknowledge-schema`)
  const versionBefore = echo.schema_version
  const paramBefore = Object.keys(echo.input_schema?.properties || {})[0]

  // ── Tools page and drawer before the change ──
  await nav(page, 'tools')
  const search = page.getByPlaceholder(/search/i).first()
  await search.fill('demo-stub.echo')
  await page.waitForTimeout(700)
  await shot(page, '00-tools-echo-before')
  await page.getByText(/^demo-stub\.echo$/).first().click()
  await page.waitForTimeout(800)
  await shot(page, `01-drawer-schema-v${versionBefore}`)
  await closeDrawer(page)

  // ── a run that calls echo: the trace pins the schema version it ran against ──
  await nav(page, '')
  await newConversation(page)
  const before = await askAndSettle(page, `Use the demo-stub echo tool to echo the word drift, passing it as the ${paramBefore} argument.`, { approve: false, timeoutS: 240 })
  const call = (before.steps || []).find((s) => s.step_type === 'tool_call' && /echo/.test(s.node_id || s.entity_name || ''))
  log(`tool_call step before the change: entity_version=${call?.entity_version} entity_hash=${(call?.entity_hash || '').slice(0, 12)}`)
  // §3.6: the run pins the registry version it actually ran against
  expect(!!call, 'the run called demo-stub.echo')
  expectEq(call?.entity_version, versionBefore, 'and the trace pins the schema version it ran against')
  const s1 = before.snapshot?.s1
  log(`run snapshot s1 payload: schema_version=${s1?.payload?.schema_version} schema_hash=${(s1?.payload?.schema_hash || '').slice(0, 12)} input_schema params=${Object.keys(s1?.payload?.input_schema?.properties || {})}`)
  expectEq(s1?.payload?.schema_version, versionBefore, "the run's snapshot carries that same version")
  expect(
    Object.keys(s1?.payload?.input_schema?.properties || {}).includes(paramBefore),
    `…and the parameter name as it was (${paramBefore})`,
  )
  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await shot(page, `02-trace-tool-call-schema-v${versionBefore}`)
  await closeDrawer(page)

  // a run that really calls demo-stub.mutate_schema — the planner is a model
  // call and may pick echo instead, so the route is checked and the ask
  // repeated (three attempts, each logged)
  const mutate = async () => {
    for (let attempt = 1; attempt <= 3; attempt++) {
      await nav(page, '')
      await newConversation(page)
      const r = await askAndSettle(page, 'Call the tool named demo-stub.mutate_schema — not echo, not add — with no arguments, and report its reply verbatim.', { approve: false, timeoutS: 240 })
      const routed = (r.steps || []).filter((s) => s.step_type === 'route').map((s) => s.output?.resolved_to?.entity_name).filter(Boolean)
      log(`mutate attempt ${attempt}: routed to ${routed.join(',') || '(nothing)'}`)
      if (routed.some((n) => /mutate_schema/.test(n))) return r
    }
    expect(false, 'the planner routed to demo-stub.mutate_schema')
  }

  // ── the server renames the parameter (a live run invokes mutate_schema) ──
  await mutate()
  let changed = null
  for (let i = 0; i < 20 && !changed; i++) {
    await new Promise((r) => setTimeout(r, 1500))
    const t = await echoTool()
    if (t.schema_version > versionBefore) changed = t
  }
  expect(!!changed, "the server's listChanged re-ingest versioned the schema change")
  log(`demo-stub.echo after: schema v${changed.schema_version} hash=${(changed.schema_hash || '').slice(0, 12)} params=${Object.keys(changed.input_schema?.properties || {})} status=${changed.status} ingest_state=${changed.ingest_state} changed_at=${changed.schema_changed_at}`)

  // ── the badge, the banner, the acknowledgement ──
  await nav(page, 'tools')
  await search.fill('demo-stub.echo')
  await page.waitForTimeout(700)
  await shot(page, '03-tools-badge-schema-changed')
  await page.getByText(/^demo-stub\.echo$/).first().click()
  await page.waitForTimeout(800)
  await shot(page, `04-drawer-banner-v${changed.schema_version}`)
  await page.getByRole('button', { name: /^Acknowledge$/ }).click()
  await page.waitForTimeout(1200)
  const acked = await echoTool()
  log(`acknowledged: changed_at=${acked.schema_changed_at} version=${acked.schema_version} (the version stays)`)
  // acknowledging clears the BANNER, not the version history
  expect(!acked.schema_changed_at, 'the acknowledgement cleared the drift banner')
  expectEq(acked.schema_version, changed.schema_version, '…and the version it was acknowledged at stays')
  await shot(page, '05-drawer-acknowledged')
  await closeDrawer(page)

  // ── Settings: the policy control and the judge's own model role ──
  await nav(page, 'settings')
  const group = page.getByRole('group', { name: /schema change policy/i })
  await group.scrollIntoViewIfNeeded()
  await shot(page, '06-settings-schema-change-policy-warn')
  await group.getByRole('button', { name: 'quarantine' }).click()
  await page.waitForTimeout(900)
  expectEq((await get('/settings')).json.mcp_schema_change_policy, 'quarantine', 'the Settings control switched the policy to quarantine')
  await shot(page, '07-settings-policy-quarantine')
  const judge = page.getByRole('combobox', { name: 'Overlap judge model' })
  await judge.scrollIntoViewIfNeeded()
  const options = await judge.locator('option').allTextContents()
  const other = options.find((o) => /openrouter:/.test(o) && !/3\.8-max/.test(o)) || options.find((o) => /openrouter:/.test(o))
  if (other) {
    await judge.selectOption({ label: other })
    await page.waitForTimeout(900)
    expectEq((await get('/settings')).json.overlap_judge_model, other, "the overlap judge's own model role was set from Settings")
  }
  await shot(page, '08-settings-overlap-judge-model')
  // the judge runs under its own role: a near-duplicate of an existing skill
  const skills = (await get('/skills?limit=50')).json.filter((s) => s.status === 'active')
  if (skills.length) {
    const target = skills[0]
    const verdict = (await post('/skills/check-overlap', { name: `${target.name} copy`, description: target.description, instructions: target.instructions || target.description, tool_ids: [] })).json
    log(`check-overlap of a copy of '${target.name}' under the judge role (${(await get('/settings')).json.overlap_judge_model}): ${JSON.stringify(verdict).slice(0, 220)}`)
    // a copy of an existing skill IS an overlap — the judge ran and said so
    expect((verdict?.overlap_percent ?? 0) > 0, `the judge flagged a copy of '${target.name}' as overlapping`)
  }

  // ── quarantine: the same change again (the stub flips the parameter back) ──
  await mutate()
  let quarantined = null
  for (let i = 0; i < 20 && !quarantined; i++) {
    await new Promise((r) => setTimeout(r, 1500))
    const t = await echoTool()
    if (t.schema_version > changed.schema_version) quarantined = t
  }
  expect(!!quarantined, 'the second mutation versioned the schema again')
  expectEq(quarantined.ingest_state, 'quarantined', 'and under the quarantine policy the tool was quarantined')
  log(`quarantined: schema v${quarantined.schema_version} status=${quarantined.status} ingest_state=${quarantined.ingest_state} params=${Object.keys(quarantined.input_schema?.properties || {})}`)
  await post(`/mcp-servers/${stub.id}/refresh-tools`)
  await new Promise((r) => setTimeout(r, 2000))
  const still = await echoTool()
  log(`after a re-ingest: status=${still.status} ingest_state=${still.ingest_state} (a re-ingest never puts it back — only the acknowledgement does)`)
  // the rule this leg exists for: a re-ingest must NOT silently un-quarantine
  expectEq(still.ingest_state, 'quarantined', 'a re-ingest left it quarantined — only the acknowledgement re-enables it')
  await nav(page, 'tools')
  await search.fill('demo-stub.echo')
  await page.waitForTimeout(700)
  await shot(page, '09-tools-quarantined')
  await page.getByText(/^demo-stub\.echo$/).first().click()
  await page.waitForTimeout(800)
  await shot(page, '10-drawer-quarantined')
  await page.getByRole('button', { name: /Acknowledge & re-enable/ }).click()
  await page.waitForTimeout(1200)
  const back = await echoTool()
  log(`re-enabled: status=${back.status} ingest_state=${back.ingest_state} version=${back.schema_version} changed_at=${back.schema_changed_at}`)
  expect(back.ingest_state !== 'quarantined', '"Acknowledge & re-enable" brought the tool back')
  await shot(page, '11-drawer-re-enabled')
  await closeDrawer(page)

  // ── a run against the new version: the trace pins v3 ──
  const paramNow = Object.keys(back.input_schema?.properties || {})[0]
  await nav(page, '')
  await newConversation(page)
  const after = await askAndSettle(page, `Use the demo-stub echo tool to echo the word drift, passing it as the ${paramNow} argument.`, { approve: false, timeoutS: 240 })
  const call2 = (after.steps || []).find((s) => s.step_type === 'tool_call' && /echo/.test(s.node_id || ''))
  log(`tool_call step after the changes: entity_version=${call2?.entity_version} entity_hash=${(call2?.entity_hash || '').slice(0, 12)}`)
  // the later run pins the LATER version — the pin tracks the registry
  expect(!!call2, 'the run after the drift called echo again')
  expectEq(call2?.entity_version, back.schema_version, 'and its trace pins the new schema version')
  expect(call2?.entity_version > versionBefore, 'which is later than the version the first run pinned')
  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await shot(page, `12-trace-tool-call-schema-v${back.schema_version}`)
  await closeDrawer(page)

  // ── restore ──
  await settings({ mcp_schema_change_policy: 'warn', overlap_judge_model: null, overlap_judge_model_params: null })
  await patch(`/tools/${mutator.id}`, { direct_exposure: false })
  log('restored: policy warn, judge model default, mutate_schema unexposed')
}
