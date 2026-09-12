// Stage 02 — MCP servers (spec §14 step 2): register a stdio server from the
// UI, watch it connect and ingest, open its drawer, refresh its tools (busy
// state), reconnect it; the http register form as the alternative transport.
export default async function ({ page, nav, shot, get, del, log, click, closeDrawer }) {
  // idempotent: a previous pass may have left the server behind
  for (const s of (await get('/mcp-servers')).json) if (s.name === 'sitefiles') await del(`/mcp-servers/${s.id}`)
  await nav(page, 'mcp-servers')
  await shot(page, '00-servers-page')

  await click(page, '+ Register server')
  await page.waitForTimeout(600)
  await page.getByPlaceholder('my-server').fill('sitefiles')
  await page.getByPlaceholder('what this server provides — the planner reads this').fill('the demo stub server: echo, add, mutate_toolset — registered live during the acceptance run')
  await page.getByPlaceholder('uvx').fill('python')
  await page.getByPlaceholder('mcp-server-fetch').fill('/app/tests/stub_mcp_server.py')
  await shot(page, '01-register-form')
  await click(page, 'Register & connect')
  await page.waitForTimeout(4000)
  const servers = (await get('/mcp-servers')).json
  const mine = servers.find((s) => s.name === 'sitefiles')
  log(`registered: ${mine?.name} ${mine?.status} tools=${mine?.tool_count} transport=${mine?.transport}`)
  if (mine?.status !== 'active') throw new Error(`sitefiles not active: ${JSON.stringify(mine)}`)
  await shot(page, '02-sitefiles-active')

  // the http transport's form (not submitted — no http server in the seed)
  await click(page, '+ Register server')
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: 'http', exact: true }).click()
  await page.getByPlaceholder('my-server').fill('remote-tools')
  await page.getByPlaceholder('http://host:8080/mcp').fill('http://tools.example.internal:8080/mcp')
  await shot(page, '03-register-form-http')
  await closeDrawer(page)

  // the drawer: detail, refresh-tools in its busy state, reconnect
  await page.getByRole('cell', { name: 'sitefiles' }).first().click().catch(async () => {
    await page.getByText('sitefiles', { exact: true }).first().click()
  })
  await page.waitForTimeout(800)
  await shot(page, '04-server-drawer-detail')
  const refresh = page.getByRole('button', { name: /refresh tools/i }).first()
  await refresh.click()
  await page.waitForTimeout(150)
  await shot(page, '05-refresh-tools-clicked')
  await page.waitForTimeout(2500)
  await page.getByRole('button', { name: /^reconnect/i }).first().click()
  await page.waitForTimeout(3500)
  const after = (await get(`/mcp-servers/${mine.id}`)).json
  log(`after reconnect: ${after.status} tools=${after.tool_count} last_connected=${after.last_connected_at}`)
  await shot(page, '06-reconnect-done')
  await closeDrawer(page)
}
