// Stage 21 — the M8 features (spec §3.5 form gates, §7.1 charts, agentic
// research): a directly-targeted sub agent whose HITL gate is a form
// (text + choice) filled and submitted from the chat card; a chart inside
// the structured answer; and an agentic research run within its iteration
// budget.
export default async function ({ page, nav, shot, settings, get, post, del, log, newConversation, askAndSettle }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null, formatter_enabled: true, formatter_presentation: 'a2ui_first', answer_ui_charts_enabled: true })

  // 1. the form gate — a sub agent created through the API (the builder has
  //    no question editor), exposed directly so the composer can target it
  const skills = (await get('/skills')).json
  const notes = skills.find((s) => s.name === 'notes-formatter')
  for (const a of (await get('/sub-agents')).json) if (a.name === 'form-demo') await del(`/sub-agents/${a.id}`)
  const created = await post('/sub-agents', {
    name: 'form-demo',
    description: 'Collects deployment details through a form gate, then writes the deployment note.',
    persona: 'You are a release coordinator.',
    direct_exposure: true,
    workflow: {
      nodes: [
        { id: 'draft', type: 'skill', skill_id: notes.id },
        {
          id: 'confirm',
          type: 'hitl',
          prompt: 'Confirm the deployment details',
          questions: [
            { id: 'what', prompt: 'What is being deployed?', kind: 'text' },
            { id: 'priority', prompt: 'Priority level', kind: 'choice', options: ['low', 'medium', 'high'] },
          ],
        },
        { id: 'finish', type: 'skill', skill_id: notes.id },
      ],
      edges: [
        { from: 'START', to: 'draft' },
        { from: 'draft', to: 'confirm' },
        { from: 'confirm', to: 'finish' },
        { from: 'finish', to: 'END' },
      ],
    },
  })
  log(`form-demo → HTTP ${created.status} ${created.status >= 300 ? JSON.stringify(created.json).slice(0, 200) : created.json.id}`)
  if (created.status >= 300) throw new Error('form-demo not created')

  await nav(page, '')
  await newConversation(page)
  const target = page.locator('select').filter({ hasText: 'Orchestrator (auto)' }).first()
  await target.selectOption({ label: 'form-demo' })
  await page.waitForTimeout(400)
  const done1 = await askAndSettle(page, 'Prepare the deployment note for the payments service.', {
    answerForm: async () => {
      await page.waitForTimeout(500)
      await shot(page, '00-form-gate-empty')
      await page.getByPlaceholder('type your answer…').first().fill('payments service v2.3 (blue/green)')
      await page.getByRole('button', { name: 'high', exact: true }).first().click()
      await page.waitForTimeout(400)
      await shot(page, '01-form-gate-filled')
    },
  })
  await shot(page, '02-form-gate-run-completed')
  const hitl = (done1.steps || []).find((s) => s.step_type === 'hitl')
  log(`form gate answers recorded: ${JSON.stringify(hitl?.output || {}).slice(0, 240)}`)
  await target.selectOption({ label: 'Orchestrator (auto)' })

  // 2. a chart inside the structured answer
  await newConversation(page)
  // (numbers given inline — naming a tool here sends the planner down the
  // rung-1 direct route to the one exposed tool, which cannot chart)
  const done2 = await askAndSettle(
    page,
    'Here are three quarterly totals: Q1 = 30, Q2 = 50, Q3 = 70. Present them as a bar chart labelled Q1, Q2 and Q3, then one sentence on the trend.',
  )
  // the formatter's charts live in answer_ui.charts and as chart blocks
  const ui = done2.answer_ui || {}
  const charts = ui.charts || (ui.blocks || []).filter((b) => b.chart).map((b) => b.chart)
  log(`answer_ui: ${(ui.a2ui || []).length} a2ui messages, ${(ui.blocks || []).length} blocks, ${charts.length} chart(s): ${charts.map((c) => `${c.kind} "${c.title}" ${JSON.stringify(c.labels)} → ${JSON.stringify(c.series?.[0]?.values)}`).join(' | ')}`)
  await page.locator('svg').last().scrollIntoViewIfNeeded().catch(() => {})
  await shot(page, '10-chart-in-a2ui-first-answer')
  if (!charts.length) log('no chart in this answer — the formatter chose not to chart it (recorded as-is)')

  // 3. agentic research within the iteration budget
  await settings({ orchestrator_mode: 'agentic' })
  await nav(page, '')
  await newConversation(page)
  // (the research-concierge sub agent gates before publishing — the gate can
  // arm minutes in, after the fetch attempts, so the watch is long)
  const done3 = await askAndSettle(page, 'Research what pgvector is used for. Three bullet points, each with a source link.', { timeoutS: 420, gateWaitS: 300 })
  const toolCalls = (done3.steps || []).filter((s) => s.step_type === 'tool_call')
  log(`research: ${toolCalls.length} tool calls (${[...new Set(toolCalls.map((s) => s.node_id))].join(', ')}); errors: ${toolCalls.filter((s) => s.status === 'failed').length}; iterations budget max_tool_iterations=${(await get('/settings')).json.max_tool_iterations}`)
  await shot(page, '20-research-run-agentic')
  await settings({ orchestrator_mode: 'graph' })
}
