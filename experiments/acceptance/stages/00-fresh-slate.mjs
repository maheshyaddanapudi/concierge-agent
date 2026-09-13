// Stage 00 — fresh slate (spec §14 step 1): the seed as the admin UI shows it
// on an empty database — two MCP servers, static tools, two skills, the
// research concierge, an empty Runs page and the chat home.
export default async function ({ page, nav, shot, get, log, expect, expectEq }) {
  const servers = (await get('/mcp-servers')).json
  const tools = (await get('/tools?limit=200')).json
  const skills = (await get('/skills')).json
  const agents = (await get('/sub-agents')).json
  log(`seed: ${servers.length} servers ${servers.map((s) => `${s.name}:${s.status}/${s.tool_count}`).join(' ')}; ${tools.length} tools; skills ${skills.map((s) => s.name).join(', ')}; sub agents ${agents.map((a) => a.name).join(', ')}`)
  const runs = (await get('/runs?limit=5')).json

  // the claim of this stage: the seed put the three layers on an empty DB
  expect(servers.length >= 2, `seed registered at least two MCP servers (${servers.length})`)
  expect(tools.some((t) => t.source === 'static'), 'the static tools are in the registry')
  expect(skills.length >= 2, `the native skills are seeded (${skills.map((s) => s.name).join(', ')})`)
  expect(
    agents.some((a) => a.name === 'research-concierge'),
    'the research-concierge sub agent is seeded',
  )
  // …and that nothing has run yet — "fresh" is half of what this stage proves
  expectEq(Array.isArray(runs) ? runs.length : -1, 0, 'the Runs page is empty on a fresh slate')

  await nav(page, 'mcp-servers')
  await shot(page, '00-servers-seeded')
  await nav(page, 'tools')
  await shot(page, '01-tools-seeded')
  await nav(page, 'skills')
  await shot(page, '02-skills-seeded')
  await nav(page, 'sub-agents')
  await shot(page, '03-research-concierge')
  await nav(page, 'runs')
  await shot(page, '04-runs-empty')
  await nav(page, '')
  await shot(page, '05-chat-home-empty')
}
