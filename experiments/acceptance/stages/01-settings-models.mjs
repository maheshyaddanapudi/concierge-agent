// Stage 01 — settings & models (spec §14 step 10 groundwork): the Settings
// page at rest, the default model picked through the UI select (the live
// model every later stage uses), the formatter section in its shipped state.
export default async function ({ page, nav, shot, settings, log, MODEL }) {
  await nav(page, 'settings')
  await shot(page, '00-settings-top')

  const before = await settings()
  log(`default_model before: ${before.default_model}; formatter ${before.formatter_enabled}/${before.formatter_presentation}`)
  await page.getByLabel('Default model').selectOption(MODEL)
  await page.waitForTimeout(1200)
  const after = await settings()
  log(`default_model after the UI select: ${after.default_model}`)
  if (after.default_model !== MODEL) throw new Error(`default_model did not take: ${after.default_model}`)
  await shot(page, '01-models-set')

  const formatter = page.getByText('Formatter (structured answers)').first()
  await formatter.scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '02-formatter-section-default-on')
}
