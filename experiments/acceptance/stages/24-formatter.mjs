// Stage 24 — the formatter (spec §7.1): settings on with A2UI first; raw
// first makes the raw answer primary with the structured view behind a
// toggle; off hides the options and produces no artifact and no toggle; and
// history is immutable — a run rendered under one presentation keeps it
// after the setting flips back.
// (no tool named in the asks — naming one sends the planner down the rung-1
// direct route to the one exposed tool; the two asks differ so the two
// conversations can be told apart in the sidebar)
const ASK = 'Add 21 and 21 and present the result as a short report: a heading, one stat, and one sentence.'
const ASK_OFF = 'Add 30 and 12 and present the result as a short report: a heading, one stat, and one sentence.'

async function formatterSection(page) {
  await page.getByText('Formatter (structured answers)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
}

export default async function ({ page, nav, shot, settings, get, log, newConversation, askAndSettle, openConversation, expect, expectEq, expectStatus }) {
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
  expectEq((await get('/settings')).json.formatter_presentation, 'raw_first', 'the raw-first button set the presentation')
  await nav(page, '')
  await newConversation(page)
  const rawFirstRun = await askAndSettle(page, ASK)
  const rawConvTitle = ASK.slice(0, 30)
  await shot(page, '01-raw-first-primary')
  const showStructured = page.getByRole('button', { name: /show structured summary/ }).first()
  // raw first means the structured view is BEHIND a toggle — the toggle
  // existing is the claim of this frame
  expectStatus(rawFirstRun, 'completed', 'the raw-first run')
  expect(!!rawFirstRun.answer_ui, 'the formatter still produced a structured artifact under raw first')
  expect((await showStructured.count()) > 0, 'the structured view is behind a "show structured summary" toggle')
  await showStructured.click()
  await page.waitForTimeout(600)
  await shot(page, '02-raw-first-structured-expanded')
  log(`raw-first run answer_ui present: ${Boolean(rawFirstRun.answer_ui)}; components: ${(rawFirstRun.answer_ui?.components || rawFirstRun.answer_ui?.a2ui || []).length}`)

  // off: options hidden, no artifact, no toggle
  await nav(page, 'settings')
  await formatterSection(page)
  const sw = page.getByRole('switch', { name: 'Formatter' }).first()
  if ((await sw.getAttribute('aria-checked')) === 'true') await sw.click()
  await page.waitForTimeout(800)
  const optionsVisible = await page.getByText('Presentation', { exact: true }).count()
  log(`formatter_enabled → ${(await get('/settings')).json.formatter_enabled}; presentation options rendered: ${optionsVisible}`)
  expectEq((await get('/settings')).json.formatter_enabled, false, 'the switch turned the formatter off')
  expectEq(optionsVisible, 0, 'the presentation options are hidden with it')
  await shot(page, '03-settings-off-options-hidden')
  await nav(page, '')
  await newConversation(page)
  const offRun = await askAndSettle(page, ASK_OFF)
  const toggles = await page.getByRole('button', { name: /view raw response|show structured summary/ }).count()
  log(`formatter off: answer_ui=${offRun.answer_ui ? 'present' : 'null'}; toggles on the page: ${toggles}`)
  // off must mean off: no artifact on the run, no toggle in the chat
  expectStatus(offRun, 'completed', 'the run with the formatter off')
  expect(!offRun.answer_ui, 'no structured artifact was produced')
  expectEq(toggles, 0, 'and no presentation toggle is rendered')
  await shot(page, '04-off-raw-only-no-toggle')

  // back on with A2UI first — the raw-first run still renders raw first
  await settings({ formatter_enabled: true, formatter_presentation: 'a2ui_first' })
  await nav(page, '')
  await openConversation(page, rawConvTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const stillRawFirst = await page.getByRole('button', { name: /show structured summary|hide structured summary/ }).count()
  log(`history after the flip back: raw-first conversation shows the structured-summary toggle: ${stillRawFirst} (presentation frozen per run)`)
  // §7.1: the presentation is frozen per run — flipping the setting back does
  // NOT re-render history under the new one
  expect(stillRawFirst > 0, 'the raw-first run still renders raw first after the setting flipped back')
  await shot(page, '05-history-immutable-after-flip')
}
