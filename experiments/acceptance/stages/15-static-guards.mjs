// Stage 15 — static guards (spec §4): seed-owned records open in their
// drawers with the definition fields disabled and no Delete, while the
// status / direct-exposure toggles stay live. One static skill, one static
// MCP server (if the seed ships one), one native static tool.
async function drawerFacts(page) {
  const drawer = page.locator('.fixed.inset-0').last()
  const inputs = drawer.locator('input, textarea, select')
  const n = await inputs.count()
  let disabled = 0
  // a switch is an <input> in this UI and must stay LIVE, so count the
  // definition fields separately from the toggles
  const switches = await drawer.getByRole('switch').count()
  for (let i = 0; i < n; i++) if (await inputs.nth(i).isDisabled()) disabled++
  const del = await drawer.getByRole('button', { name: /^Delete$/ }).count()
  return { n, disabled, del, switches, toString: () => `fields ${disabled}/${n} disabled, Delete buttons: ${del}, live switches: ${switches}` }
}

/** §4: a static record's definition is read-only, it cannot be deleted, and
 * its status / direct-exposure toggles still work. */
function expectStaticGuards(facts, what, { expect, expectEq }) {
  expect(facts.n > 0, `${what}: the drawer rendered its definition fields (${facts.n})`)
  expect(facts.disabled > 0, `${what}: the definition fields are disabled (${facts.disabled}/${facts.n})`)
  expectEq(facts.del, 0, `${what}: no Delete button`)
  expect(facts.switches > 0, `${what}: the status / exposure toggles are still there`)
}

export default async function ({ page, nav, shot, get, log, closeDrawer, expect, expectEq }) {
  const skills = (await get('/skills')).json
  const staticSkill = skills.find((s) => s.source === 'static')
  expect(!!staticSkill, 'the seed ships a static skill')
  await nav(page, 'skills')
  await page.getByText(staticSkill.name, { exact: true }).first().click()
  await page.waitForTimeout(900)
  const skillFacts = await drawerFacts(page)
  log(`static skill ${staticSkill.name}: ${skillFacts}`)
  expectStaticGuards(skillFacts, `static skill ${staticSkill.name}`, { expect, expectEq })
  await shot(page, '00-static-skill-drawer')
  await closeDrawer(page)

  const servers = (await get('/mcp-servers')).json
  const staticServer = servers.find((s) => s.source === 'static')
  if (staticServer) {
    await nav(page, 'mcp-servers')
    await page.getByText(staticServer.name, { exact: true }).first().click()
    await page.waitForTimeout(900)
    const serverFacts = await drawerFacts(page)
    log(`static server ${staticServer.name}: ${serverFacts}`)
    expectStaticGuards(serverFacts, `static server ${staticServer.name}`, { expect, expectEq })
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
  expect(!!nativeTool, 'the seed ships a native static tool')
  const toolFacts = await drawerFacts(page)
  log(`native static tool ${nativeTool.tool_key}: ${toolFacts}`)
  expectStaticGuards(toolFacts, `native static tool ${nativeTool.tool_key}`, { expect, expectEq })
  await shot(page, '02-native-static-tool-drawer')
  await closeDrawer(page)
}
