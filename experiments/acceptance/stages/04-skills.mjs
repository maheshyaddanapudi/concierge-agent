// Stage 04 — skills (spec §14 step 3): the native skills, the editor with
// tool tags and the live preview, a bad `{tool:…}` mention rejected at
// save, `summarize-site` created from the registered server's tools, its
// badges on both pages, an edit that moves `updated_at`, and a second skill
// (`notes-formatter`) exposed directly.
export default async function ({ page, nav, shot, get, log, click, closeDrawer, submitSave }) {
  await nav(page, 'skills')
  await shot(page, '00-native-skills')

  await click(page, '+ New skill')
  await page.waitForTimeout(600)
  await page.getByLabel('Name').fill('summarize-site')
  await page.getByLabel('Description').fill('Echo the request back and add any two numbers in it with the sitefiles tools, then summarize in one line.')
  await page.getByLabel(/Persona/).fill('You are a terse site summarizer.')
  const filter = page.getByPlaceholder('filter tools…')
  await filter.fill('sitefiles')
  await page.waitForTimeout(400)
  for (const key of ['sitefiles.echo', 'sitefiles.add']) {
    await page.locator(`label:has(code:text-is("${key}")) input[type=checkbox]`).first().check()
  }
  const instructions = page.locator('textarea[rows="14"]')
  await instructions.fill('# Purpose\n1. Echo the request with {tool:sitefiles.echo}.\n2. Add the two numbers with {tool:sitefiles.add}.\n3. Answer in one line.\n')
  await page.waitForTimeout(500)
  await shot(page, '01-skill-editor')

  // a mention of an unbound tool is rejected at save
  await instructions.fill('# Purpose\n1. Echo with {tool:sitefiles.echo}.\n2. Then {tool:sitefiles.nope} — not bound.\n')
  const refused = await submitSave(page, 'Create skill')
  log(`save with an unbound mention → ${refused.outcome}: ${refused.text.slice(0, 140)}`)
  await shot(page, '03-bad-tool-mention-rejected')
  await instructions.fill('# Purpose\n1. Echo the request with {tool:sitefiles.echo}.\n2. Add the two numbers with {tool:sitefiles.add}.\n3. Answer in one line.\n')
  log(`create → ${JSON.stringify(await submitSave(page, 'Create skill'))}`)
  const skills = (await get('/skills')).json
  const mine = skills.find((s) => s.name === 'summarize-site')
  log(`created: ${mine?.name} ${mine?.kind} tools=${(mine?.tools || []).map((t) => t.tool_key).join(',')}`)
  if (!mine) throw new Error('summarize-site not created')
  await closeDrawer(page)
  await shot(page, '02-skill-saved-badges')

  // a second, tool-less skill exposed directly (rung 2 for later trials)
  await click(page, '+ New skill')
  await page.waitForTimeout(500)
  await page.getByLabel('Name').fill('notes-formatter')
  await page.getByLabel('Description').fill('Turns rough notes into a clean bullet list. No tools.')
  await page.getByLabel(/Persona/).fill('You are a crisp editor.')
  await page.locator('textarea[rows="14"]').fill('# Purpose\n1. Read the notes.\n2. Return them as tight bullets, nothing else.\n')
  const expose = page.getByRole('switch').first()
  await expose.click()
  await page.waitForTimeout(300)
  await shot(page, '04-notes-formatter-exposed')
  log(`create → ${JSON.stringify(await submitSave(page, 'Create skill'))}`)
  await closeDrawer(page)

  // edit → updated_at moves
  const before = (await get(`/skills/${mine.id}`)).json.updated_at
  await page.getByText('summarize-site', { exact: true }).first().click()
  await page.waitForTimeout(800)
  await page.getByLabel('Description').fill('Echo the request back and add any two numbers in it with the sitefiles tools, then summarize in one line. (edited)')
  log(`save → ${JSON.stringify(await submitSave(page, 'Save skill'))}`)
  const after = (await get(`/skills/${mine.id}`)).json.updated_at
  log(`updated_at ${before} → ${after}`)
  if (after === before) throw new Error('updated_at did not move')
  await shot(page, '06-edited-skill-updated')
  await closeDrawer(page)

  // the cross-link on the Tools page: the tool row names the skill
  await nav(page, 'tools')
  await page.getByPlaceholder(/search/i).first().fill('sitefiles.echo')
  await page.waitForTimeout(700)
  await shot(page, '07-tools-page-skill-crosslink')
}
