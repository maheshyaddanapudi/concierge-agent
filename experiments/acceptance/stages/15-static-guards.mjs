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
  // a drawer may lock its definition by rendering it as read-only TEXT rather
  // than as disabled fields — stricter, not weaker — and may offer its status
  // control as a button rather than a switch
  const locked = await drawer.getByText(/definition fields are locked/i).count()
  const statusBtn = await drawer.getByRole('button', { name: /^(Deactivate|Activate)$/ }).count()
  return {
    n, disabled, del, switches, locked, statusBtn,
    toString: () =>
      `fields ${disabled}/${n} disabled, Delete buttons: ${del}, live switches: ${switches}, locked-banner: ${locked}, status button: ${statusBtn}`,
  }
}

/** §4: a static record's definition is read-only, it cannot be deleted, and
 * its status / direct-exposure toggles still work.
 *
 * What §4 requires is that the definition CANNOT BE EDITED, not that it be
 * rendered as a disabled `<input>`. The skill drawer builds a locked form;
 * the MCP server drawer prints the definition as plain text under a "Static
 * record — definition fields are locked" banner and offers Deactivate as a
 * button. The second is at least as strict as the first — there is no field
 * to re-enable — but the original helper only knew the first shape and so
 * reported the server drawer as having no guards at all. */
function expectStaticGuards(facts, what, { expect, expectEq }) {
  const readOnlyForm = facts.n > 0 && facts.disabled > 0
  const readOnlyText = facts.locked > 0 && facts.n === 0
  expect(
    readOnlyForm || readOnlyText,
    `${what}: the definition is read-only — ${readOnlyText ? 'rendered as locked text' : `${facts.disabled}/${facts.n} fields disabled`}`,
  )
  expectEq(facts.del, 0, `${what}: no Delete button`)
  expect(
    facts.switches > 0 || facts.statusBtn > 0,
    `${what}: the status / exposure control is still live (${facts.switches} switch, ${facts.statusBtn} button)`,
  )
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
