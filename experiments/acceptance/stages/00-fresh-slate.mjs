// Stage 00 — fresh slate (spec §14 step 1): the seed as the admin UI shows it
// on an empty database — two MCP servers, static tools, two skills, the
// research concierge, an empty Runs page and the chat home.
export default async function ({ page, nav, shot, get, log }) {
  const servers = (await get('/mcp-servers')).json
  const tools = (await get('/tools?limit=200')).json
  const skills = (await get('/skills')).json
  const agents = (await get('/sub-agents')).json
  log(`seed: ${servers.length} servers ${servers.map((s) => `${s.name}:${s.status}/${s.tool_count}`).join(' ')}; ${tools.length} tools; skills ${skills.map((s) => s.name).join(', ')}; sub agents ${agents.map((a) => a.name).join(', ')}`)
  const runs = (await get('/runs?limit=5')).json
  log(`runs at rest: ${Array.isArray(runs) ? runs.length : JSON.stringify(runs).slice(0, 60)}`)

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
