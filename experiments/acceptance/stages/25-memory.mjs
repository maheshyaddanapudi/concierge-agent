// Stage 25 — memory (spec §16): the layer switches in Settings, the empty
// store, a manual "+ Remember", a chat that teaches a preference and an
// instruction (extraction lands the preference active and the instruction
// in review, per the admission gate), the detail drawer with provenance,
// review-queue approval, edit-as-supersede, pin, genuine recall in a brand
// new conversation, and the hard delete.
const TEACH = 'My favorite color is teal. From now on, always answer me in bullet points.'

async function setSwitch(page, name, on) {
  const sw = page.getByRole('switch', { name }).first()
  await sw.scrollIntoViewIfNeeded()
  if (((await sw.getAttribute('aria-checked')) === 'true') !== on) await sw.click()
  await page.waitForTimeout(500)
}

export default async function ({ page, nav, shot, settings, get, post, log, closeDrawer, newConversation, askAndSettle }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null, memory_forget_enabled: false })
  await nav(page, 'settings')
  for (const name of ['Memory enabled', 'Extraction (L2 writes)', 'Reflection (L4)', 'Procedural learning (L3)']) await setSwitch(page, name, true)
  const s = (await get('/settings')).json
  log(`layers: memory=${s.memory_enabled} extraction=${s.memory_extraction_enabled} procedural=${s.procedural_learning_enabled} reflection=${s.memory_reflection_enabled} forget=${s.memory_forget_enabled}`)
  await page.getByText('Memory (§16 — the experiment layers)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-settings-memory-layers')

  // the empty store
  await post('/memories/purge', {})
  await nav(page, 'memory')
  log(`status: ${JSON.stringify((await get('/memories/status')).json).slice(0, 200)}`)
  await shot(page, '01-store-empty')

  // + Remember
  await page.getByPlaceholder('remember something new…').fill("The team's staging cluster is named aurora-2.")
  await page.locator('select').nth(2).selectOption('fact')
  await page.getByRole('button', { name: '+ Remember' }).click()
  await page.waitForTimeout(1200)
  const manual = (await get('/memories')).json
  log(`after + Remember: ${manual.length} rows — ${manual.map((m) => `${m.kind}/${m.status}/${m.source}`).join(', ')}`)
  await shot(page, '02-remember-quick-add')

  // a chat that teaches a preference and an instruction
  await nav(page, '')
  await newConversation(page)
  const done = await askAndSettle(page, TEACH)
  let rows = []
  for (let i = 0; i < 60; i++) {
    rows = (await get('/memories')).json
    if (rows.some((m) => m.source !== 'manual' && m.run_id === done.id) && rows.filter((m) => m.run_id === done.id).length >= 2) break
    await page.waitForTimeout(2000)
  }
  const extracted = rows.filter((m) => m.run_id === done.id)
  log(`extracted from the run: ${extracted.map((m) => `${m.kind}/${m.status}: ${m.text.slice(0, 50)}`).join(' | ') || 'nothing yet'}`)
  await shot(page, '03-chat-teaches-fact-and-instruction')
  await nav(page, 'memory')
  await shot(page, '04-store-post-extraction')

  // the drawer with provenance (the preference, active)
  const pref = extracted.find((m) => m.kind === 'preference') || extracted[0]
  if (!pref) throw new Error('no extracted memory to open')
  await page.locator('tr').filter({ hasText: pref.text.slice(0, 40) }).first().click()
  await page.waitForTimeout(800)
  await shot(page, '05-memory-detail-provenance')
  await closeDrawer(page)

  // the review queue: the instruction landed quarantined
  const instr = extracted.find((m) => m.status === 'quarantined')
  await page.getByRole('button', { name: /^Review queue/ }).click()
  await page.waitForTimeout(800)
  await shot(page, '06-review-queue-instruction')
  if (instr) {
    await page.locator('tr').filter({ hasText: instr.text.slice(0, 40) }).first().click()
    await page.waitForTimeout(800)
    await page.getByPlaceholder('optional review note…').fill('Approved — a standing formatting preference.')
    await page.getByRole('button', { name: '✓ Approve' }).click()
    await page.waitForTimeout(1200)
    const after = (await get(`/memories/${instr.id}`)).json
    log(`review approve → ${after.status}; note: ${after.review_note}`)
  } else {
    log('no quarantined instruction from this run — the review leg has nothing to approve (recorded as-is)')
  }
  await page.getByRole('button', { name: 'Store' }).click()
  await page.waitForTimeout(800)
  await shot(page, '07-review-approved')

  // edit as supersede: the preference gains a version
  await page.locator('tr').filter({ hasText: pref.text.slice(0, 40) }).first().click()
  await page.waitForTimeout(800)
  await page.getByLabel('Memory text').fill(pref.text.replace(/teal/i, 'deep teal'))
  await page.getByRole('button', { name: 'Save as new version' }).click()
  await page.waitForTimeout(1500)
  const versions = (await get('/memories')).json.filter((m) => /teal/i.test(m.text))
  log(`after the edit: ${versions.map((m) => `${m.status}${m.supersedes ? ' supersedes ' + m.supersedes.slice(0, 8) : ''}: ${m.text.slice(0, 40)}`).join(' | ')}`)
  await page.locator('select').nth(1).selectOption('')
  await page.waitForTimeout(800)
  await shot(page, '08-edit-as-supersede')

  // pin the new version
  const current = versions.find((m) => m.status === 'active') || versions[0]
  await page.locator('tr').filter({ hasText: current.text.slice(0, 40) }).first().click()
  await page.waitForTimeout(800)
  await page.getByRole('button', { name: 'Pin (always injected)' }).click()
  await page.waitForTimeout(1200)
  log(`pinned: ${(await get(`/memories/${current.id}`)).json.pinned}`)
  await shot(page, '09-pinned-memory')

  // recall in a brand-new conversation
  await nav(page, '')
  await newConversation(page)
  const recall = await askAndSettle(page, 'What is my favorite color? One sentence.')
  log(`recall mentions teal: ${/teal/i.test(recall.final_answer || '')}; include_memories=${recall.include_memories}`)
  await shot(page, '10-recall-in-new-chat')

  // hard delete of the manual fact
  await nav(page, 'memory')
  await page.locator('tr').filter({ hasText: 'aurora-2' }).first().click()
  await page.waitForTimeout(800)
  page.once('dialog', (d) => {
    log(`confirm: ${d.message()}`)
    void d.accept()
  })
  await page.getByRole('button', { name: /Delete permanently|Erase completely/ }).click()
  await page.waitForTimeout(1200)
  log(`after the delete: ${(await get('/memories')).json.length} rows; status ${JSON.stringify((await get('/memories/status')).json.counts)}`)
  await shot(page, '11-hard-delete')
}
