// Stage 05 — sub agents (spec §14 step 5): the builder from the "Branch +
// HITL approve" template with an error edge added, a dangling edge rejected
// inline by the dry-run validator, the overlap dialog on save when the judge
// flags it, `site-analyst` saved and previewed as a DAG, the static seed
// card's drawer, and a bound skill refusing deletion.
export default async function ({ page, nav, shot, get, log, click, closeDrawer, submitSave }) {
  const skills = (await get('/skills')).json
  const summarize = skills.find((s) => s.name === 'summarize-site')
  const notes = skills.find((s) => s.name === 'notes-formatter')
  if (!summarize || !notes) throw new Error('stage 04 skills missing')

  await nav(page, 'sub-agents')
  await click(page, '+ New sub agent')
  await page.waitForTimeout(600)
  await page.getByLabel('Name').fill('site-analyst')
  await page.getByLabel('Starter template').selectOption('Branch + HITL approve')
  await page.waitForTimeout(400)
  await page.getByLabel('Description').fill('Summarizes a site with summarize-site, asks before publishing, and falls back to a plain note when the tools fail.')
  await page.getByLabel('Persona').fill('You are a careful site analyst.')
  // bind the template's skill nodes to summarize-site
  const skillSelects = page.locator('select').filter({ hasText: 'pick skill…' })
  const n = await skillSelects.count()
  for (let i = 0; i < n; i++) await skillSelects.nth(i).selectOption(summarize.id)
  // add a recover node on the error edge, bound to the tool-less skill
  await click(page, '+ skill node')
  await page.waitForTimeout(300)
  const newId = page.locator('input[value^="n"]').last()
  await newId.fill('recover')
  await page.locator('select').filter({ hasText: 'pick skill…' }).last().selectOption(notes.id)
  await click(page, '+ edge')
  await page.waitForTimeout(300)
  const edgeRow = page.locator('div').filter({ has: page.getByPlaceholder('condition (optional)') }).last()
  const sel = edgeRow.locator('select')
  await sel.nth(0).selectOption('work')
  await sel.nth(1).selectOption('recover')
  await sel.nth(2).selectOption('error')
  await page.waitForTimeout(400)
  await shot(page, '00-builder-error-edge')

  // a dangling edge is refused inline at save (the server's validator, shown in the drawer)
  await click(page, '+ edge')
  await page.waitForTimeout(300)
  const refused = await submitSave(page, 'Create sub agent', { acceptOverlap: true })
  log(`create with a dangling edge → ${refused.outcome}: ${refused.text.slice(0, 160)}`)
  await shot(page, '01-validation-rejected')
  // remove the dangling edge (the last ✕ in the edges list) and save for real
  await page.getByRole('button', { name: '✕' }).last().click()
  await page.waitForTimeout(300)
  const saved = await submitSave(page, 'Create sub agent', { onOverlap: () => shot(page, '01a-overlap-dialog') })
  log(`create → ${JSON.stringify(saved)}${saved.sawOverlap ? '' : ' (the overlap judge did not flag it — nondeterministic, recorded as-is)'}`)
  const agents = (await get('/sub-agents')).json
  const mine = agents.find((a) => a.name === 'site-analyst')
  log(`saved: ${mine?.name} nodes=${mine?.workflow?.nodes?.map((x) => x.id + ':' + x.type).join(',')} edges=${mine?.workflow?.edges?.length}`)
  if (!mine) throw new Error('site-analyst not saved')
  await closeDrawer(page)
  await shot(page, '02-site-analyst-saved')

  // the static seed card's drawer, then the DAG preview of ours
  await page.getByText('research-concierge', { exact: true }).first().click()
  await page.waitForTimeout(900)
  await shot(page, '03-static-seed-card-drawer')
  await closeDrawer(page)
  await page.getByText('site-analyst', { exact: true }).first().click()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: /Validate/ }).first().click()
  await page.waitForTimeout(1200)
  await shot(page, '04-dag-preview-rendered')
  await closeDrawer(page)

  // a skill bound to a sub agent refuses deletion (409 names the dependents)
  await nav(page, 'skills')
  await page.getByText('summarize-site', { exact: true }).first().click()
  await page.waitForTimeout(800)
  await click(page, 'Delete')
  await page.waitForTimeout(1200)
  const err = await page.locator('.bg-rose-500\\/10').first().textContent({ timeout: 5000 }).catch(() => '')
  log(`delete bound skill → ${String(err).trim().slice(0, 140)}`)
  await shot(page, '05-skill-delete-conflict')
  await closeDrawer(page)
}
