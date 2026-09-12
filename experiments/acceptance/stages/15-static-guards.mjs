// Stage 15 — static guards (spec §4): seed-owned records open in their
// drawers with the definition fields disabled and no Delete, while the
// status / direct-exposure toggles stay live. One static skill, one static
// MCP server (if the seed ships one), one native static tool.
async function drawerFacts(page) {
  const drawer = page.locator('.fixed.inset-0').last()
  const inputs = drawer.locator('input, textarea, select')
  const n = await inputs.count()
  let disabled = 0
  for (let i = 0; i < n; i++) if (await inputs.nth(i).isDisabled()) disabled++
  const del = await drawer.getByRole('button', { name: /^Delete$/ }).count()
  const switches = await drawer.getByRole('switch').count()
  return `fields ${disabled}/${n} disabled, Delete buttons: ${del}, live switches: ${switches}`
}

export default async function ({ page, nav, shot, get, log, closeDrawer }) {
  const skills = (await get('/skills')).json
  const staticSkill = skills.find((s) => s.source === 'static')
  await nav(page, 'skills')
  await page.getByText(staticSkill.name, { exact: true }).first().click()
  await page.waitForTimeout(900)
  log(`static skill ${staticSkill.name}: ${await drawerFacts(page)}`)
  await shot(page, '00-static-skill-drawer')
  await closeDrawer(page)

  const servers = (await get('/mcp-servers')).json
  const staticServer = servers.find((s) => s.source === 'static')
  if (staticServer) {
    await nav(page, 'mcp-servers')
    await page.getByText(staticServer.name, { exact: true }).first().click()
    await page.waitForTimeout(900)
    log(`static server ${staticServer.name}: ${await drawerFacts(page)}`)
    await shot(page, '01-static-server-drawer-no-delete')
    await closeDrawer(page)
  } else {
    log(`no static MCP server in this seed (servers: ${servers.map((s) => s.name + ':' + s.source).join(', ')}) — frame 01 not produced`)
  }

  const tools = (await get('/tools')).json
  const nativeTool =
    tools.find((t) => t.source === 'static' && t.kind === 'native' && /^file\./.test(t.tool_key)) ||
    tools.find((t) => t.source === 'static' && t.kind === 'native')
  await nav(page, 'tools')
  await page.getByPlaceholder('Search…').fill(nativeTool.tool_key)
  await page.waitForTimeout(700)
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(900)
  log(`native static tool ${nativeTool.tool_key}: ${await drawerFacts(page)}`)
  await shot(page, '02-native-static-tool-drawer')
  await closeDrawer(page)
}
