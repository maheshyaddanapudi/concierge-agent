// Stage 24 — the formatter (spec §7.1): settings on with A2UI first; raw
// first makes the raw answer primary with the structured view behind a
// toggle; off hides the options and produces no artifact and no toggle; and
// history is immutable — a run rendered under one presentation keeps it
// after the setting flips back.
const ASK = 'Use the sitefiles add tool to add 21 and 21, then present the result as a short report: a heading, one stat, and one sentence.'

async function formatterSection(page) {
  await page.getByText('Formatter (structured answers)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
}

export default async function ({ page, nav, shot, settings, get, log, newConversation, askAndSettle, openConversation }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null, formatter_enabled: true, formatter_presentation: 'a2ui_first' })
  await nav(page, 'settings')
  await formatterSection(page)
  await page.getByRole('button', { name: 'A2UI first' }).first().click()
  await page.waitForTimeout(600)
  await shot(page, '00-settings-on-a2ui-first')

  // raw first
  await page.getByRole('button', { name: 'raw first' }).first().click()
  await page.waitForTimeout(800)
  log(`presentation → ${(await get('/settings')).json.formatter_presentation}`)
  await nav(page, '')
  await newConversation(page)
  const rawFirstRun = await askAndSettle(page, ASK)
  const rawConvTitle = ASK.slice(0, 30)
  await shot(page, '01-raw-first-primary')
  const showStructured = page.getByRole('button', { name: /show structured summary/ }).first()
  if (await showStructured.count()) {
    await showStructured.click()
    await page.waitForTimeout(600)
    await shot(page, '02-raw-first-structured-expanded')
  } else {
    log('no structured summary toggle on the raw-first answer (no artifact produced) — recorded as-is')
  }
  log(`raw-first run answer_ui present: ${Boolean(rawFirstRun.answer_ui)}; components: ${(rawFirstRun.answer_ui?.components || rawFirstRun.answer_ui?.a2ui || []).length}`)

  // off: options hidden, no artifact, no toggle
  await nav(page, 'settings')
  await formatterSection(page)
  const sw = page.getByRole('switch', { name: 'Formatter' }).first()
  if ((await sw.getAttribute('aria-checked')) === 'true') await sw.click()
  await page.waitForTimeout(800)
  const optionsVisible = await page.getByText('Presentation', { exact: true }).count()
  log(`formatter_enabled → ${(await get('/settings')).json.formatter_enabled}; presentation options rendered: ${optionsVisible}`)
  await shot(page, '03-settings-off-options-hidden')
  await nav(page, '')
  await newConversation(page)
  const offRun = await askAndSettle(page, ASK)
  const toggles = await page.getByRole('button', { name: /view raw response|show structured summary/ }).count()
  log(`formatter off: answer_ui=${offRun.answer_ui ? 'present' : 'null'}; toggles on the page: ${toggles}`)
  await shot(page, '04-off-raw-only-no-toggle')

  // back on with A2UI first — the raw-first run still renders raw first
  await settings({ formatter_enabled: true, formatter_presentation: 'a2ui_first' })
  await nav(page, '')
  await openConversation(page, rawConvTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const stillRawFirst = await page.getByRole('button', { name: /show structured summary|hide structured summary/ }).count()
  log(`history after the flip back: raw-first conversation shows the structured-summary toggle: ${stillRawFirst} (presentation frozen per run)`)
  await shot(page, '05-history-immutable-after-flip')
}
