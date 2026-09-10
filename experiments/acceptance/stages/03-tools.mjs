// Stage 03 — tools (spec §14 steps 2 & 4): the ingested `{server}.{tool}`
// keys, the schema drawer of a dynamic tool before its toggle, the expose
// toggle flipped in the drawer, the DIRECT badge in the table, the cache
// refresh button, search and the source filter.
export default async function ({ page, nav, shot, get, log, closeDrawer }) {
  await nav(page, 'tools')
  const search = page.getByPlaceholder(/search/i).first()
  await search.fill('sitefiles')
  await page.waitForTimeout(700)
  await shot(page, '00-ingested-server-dot-tool')

  // the dynamic tool's drawer before the toggle
  await page.getByText(/^sitefiles\.echo/).first().click()
  await page.waitForTimeout(800)
  await shot(page, '06-dynamic-tool-drawer-pretoggle')

  // expose it (the drawer's switch under "Expose to orchestrator")
  const sw = page.getByRole('switch').first()
  await sw.click()
  await page.waitForTimeout(900)
  const tools = (await get('/tools?limit=200')).json
  const echo = tools.find((t) => t.tool_key === 'sitefiles.echo')
  log(`sitefiles.echo direct_exposure=${echo?.direct_exposure}`)
  if (!echo?.direct_exposure) throw new Error('expose toggle did not take')
  await shot(page, '01-expose-toggle')
  await closeDrawer(page)
  await shot(page, '02-direct-badge')

  // cache refresh button (top right), then search + source filter
  await search.fill('')
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: /refresh/i }).first().hover()
  await shot(page, '03-cache-refresh-button')
  await search.fill('file')
  await page.waitForTimeout(700)
  await shot(page, '04-search-filter')
  await search.fill('')
  const source = page.locator('select').filter({ hasText: /all sources/i }).first()
  await source.selectOption('static')
  await page.waitForTimeout(700)
  const shown = await page.locator('table tbody tr').count()
  log(`source=static rows shown: ${shown}`)
  await shot(page, '05-filter-source-static')
  await source.selectOption({ index: 0 })
}
