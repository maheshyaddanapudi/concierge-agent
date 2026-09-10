// Stage 14 — runs and ops (spec §14 steps 9/10, §10): the Runs table, a
// completed run's trace drawer (answer + structured artifact, then the step
// timeline), the search filter, the observability controls in Settings, the
// direct-exposure cap banner on the Tools page when the cap is lowered under
// the exposed count, and an idempotent seed reload.
export default async function ({ page, nav, shot, settings, get, log, closeDrawer, click }) {
  await nav(page, 'runs')
  const runs = (await get('/runs?limit=50')).json
  log(`runs listed: ${runs.length} (${runs.map((r) => r.status).join(', ')})`)
  await shot(page, '00-runs-list')

  // the newest completed run's drawer: answer + artifact, then the timeline
  const completed = runs.find((r) => r.status === 'completed')
  if (completed) {
    const row = page.locator('table tbody tr').filter({ hasText: (completed.chat_message || completed.message || '').slice(0, 40) }).first()
    await row.click()
    await page.waitForTimeout(1200)
    await shot(page, '01-trace-drawer-answer-and-artifact')
    const drawer = page.locator('.fixed.inset-0').last()
    await drawer.getByText(/step timeline/i).first().scrollIntoViewIfNeeded().catch(() => {})
    await page.waitForTimeout(500)
    await shot(page, '02-step-timeline')
    await closeDrawer(page)
  } else {
    log('no completed run on the table — drawer frames skipped (recorded as-is)')
  }

  // search filters the table by message text
  await page.getByPlaceholder('Search…').fill('summary')
  await page.waitForTimeout(800)
  const shown = await page.locator('table tbody tr').count()
  log(`search "summary" → ${shown} rows`)
  await shot(page, '03-runs-search-filter')
  await page.getByPlaceholder('Search…').fill('')

  // observability controls
  await nav(page, 'settings')
  await page.getByText('Observability', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await shot(page, '04-observability-controls')

  // the exposure-cap banner: lower the cap below the exposed count
  const tools = (await get('/tools')).json
  const skills = (await get('/skills')).json
  const exposed = tools.filter((t) => t.direct_exposure).length + skills.filter((s) => s.direct_exposure).length
  const before = (await get('/settings')).json.direct_exposure_cap_warning
  log(`directly exposed capabilities: ${exposed}; cap warning before: ${before}`)
  const capInput = page.getByLabel('Direct-exposure cap warning').first()
  await capInput.scrollIntoViewIfNeeded()
  await capInput.fill('1')
  await capInput.press('Enter')
  await capInput.blur()
  await page.waitForTimeout(1200)
  let cap = (await get('/settings')).json.direct_exposure_cap_warning
  if (cap !== 1) {
    log(`the number field did not commit on Enter/blur (cap=${cap}) — set through the API instead`)
    await settings({ direct_exposure_cap_warning: 1 })
    cap = 1
  }
  log(`cap warning now: ${cap}`)
  await nav(page, 'tools')
  const banner = page.getByText(/capabilities are directly exposed/i).first()
  const sawBanner = await banner.waitFor({ timeout: 10000 }).then(() => true).catch(() => false)
  log(sawBanner ? `banner: ${(await banner.textContent()).trim().slice(0, 160)}` : 'no banner — exposed count is not above the cap')
  await shot(page, '05-exposure-cap-banner-tools')
  await settings({ direct_exposure_cap_warning: before ?? 10 })

  // seed reload is idempotent: registry counts unchanged, ids unchanged
  const idsBefore = { tools: tools.map((t) => t.id).sort(), skills: skills.map((s) => s.id).sort() }
  await nav(page, 'settings')
  const reload = page.getByRole('button', { name: /Reload seed/ }).first()
  await reload.scrollIntoViewIfNeeded()
  await reload.click()
  await page.waitForTimeout(3000)
  const toolsAfter = (await get('/tools')).json
  const skillsAfter = (await get('/skills')).json
  const same =
    JSON.stringify(toolsAfter.map((t) => t.id).sort()) === JSON.stringify(idsBefore.tools) &&
    JSON.stringify(skillsAfter.map((s) => s.id).sort()) === JSON.stringify(idsBefore.skills)
  log(`seed reload → tools ${tools.length}→${toolsAfter.length}, skills ${skills.length}→${skillsAfter.length}, ids ${same ? 'unchanged' : 'CHANGED'}`)
  await shot(page, '06-after-seed-reload')
  if (!same) throw new Error('seed reload changed registry ids')
}
