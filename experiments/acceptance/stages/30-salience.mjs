// Stage 30 — content salience (spec §17.5, §14g steps 48–51): the truthful
// in-app delivery record for deliveries nobody saw, the unread badge, the
// salience judge run live in auto mode over the unseen items (a hot ops
// alert escalated, a routine notice dropped), the digest preview led by the
// escalated item, and the record after the items are seen. Deliveries are
// inserted server-side so the ledger reflects exactly what the tick did.
import fs from 'node:fs'
import { execSync } from 'node:child_process'

const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
const psql = (q) => execSync(`docker exec ${DB} psql -U ${process.env.ACC_DB_USER || 'concierge'} -d ${process.env.ACC_DB_NAME || 'concierge'} -tAc "${q.replace(/"/g, '\\"')}"`, { encoding: 'utf8' }).trim()
const seed = (title, body, urgency) => psql(`with ins as (insert into deliveries (id, category, tier, urgency, title, body, created_at) values (gen_random_uuid(), 'ops', 0, ${urgency}, '${title.replace(/'/g, "''")}', '${body.replace(/'/g, "''")}', now()) returning id) select id from ins`)
const row = (id) => JSON.parse(psql(`select json_build_object('tier', tier, 'delivered_at', delivered_at, 'seen_at', seen_at, 'external', external, 'salience', salience) from deliveries where id='${id}'`))

export default async function ({ page, nav, shot, settings, get, log }) {
  const initial = (await get('/settings')).json
  const out = [`# §14g-48..51 — salience judged live (auto) — ${new Date().toISOString()}`, '']
  const say = (l) => {
    out.push(l)
    log(l)
  }
  await settings({
    ambient_enabled: true,
    ambient_tick_interval_s: 15,
    ambient_quiet_hours: [],
    ambient_salience_mode: 'auto',
    ambient_salience_min_urgency: 3,
    ambient_salience_learning: 'off',
    ambient_pursuit: 'off',
    ambient_channels: {},
  })
  await nav(page, 'settings')
  await page.getByText('Salience (§17.5)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-settings-salience-auto')
  say(`# mode=auto min_urgency=3 judge=${(await get('/settings')).json.ambient_salience_model || '(default model)'}`)

  await page.goto('about:blank')
  say('# browser off the app; waiting 25s for the SSE stream to unregister')
  await page.waitForTimeout(25000)
  const hot = seed('payments-api p99 error rate 9.4% and rising', 'one in eleven checkouts failing for 6 minutes; no rollback performed yet; on-call not paged', 5)
  const cold = seed('cache warm completed on web-03', 'routine cache warm finished in 41s with no anomalies; nothing to do', 3)
  say(`inserted: hot=${hot} cold=${cold}`)
  say('# nobody is watching the stream — waiting for the tick to flush + judge…')
  let h = row(hot)
  let c = row(cold)
  for (let i = 0; i < 40; i++) {
    h = row(hot)
    c = row(cold)
    if (h.salience && c.salience) break
    await new Promise((r) => setTimeout(r, 4000))
  }
  say(`§14g-48 in_app ledger (hot):  ${JSON.stringify(h.external)}`)
  say(`§14g-48 in_app ledger (cold): ${JSON.stringify(c.external)}`)
  say(`§14g-49 salience (hot):  ${JSON.stringify(h.salience)}`)
  say(`§14g-50 salience (cold): ${JSON.stringify(c.salience)}`)
  say(`  tiers after the judge: hot=${h.tier} cold=${c.tier} (auto applies: escalate leads the digest, drop dismisses)`)

  await nav(page, 'runs')
  const unread = (await get('/deliveries/unread-count')).json
  say(`unread badge: ${JSON.stringify(unread)}`)
  await page.getByTestId('unread-badge').waitFor({ timeout: 15000 }).catch(() => log('no unread badge rendered'))
  await shot(page, '01-unread-badge-nav')
  await nav(page, 'ambient')
  await page.waitForTimeout(1200)
  await page.getByTestId('salience-verdict').first().waitFor({ timeout: 15000 }).catch(() => log('no salience verdict block rendered'))
  await shot(page, '02-inbox-salience-verdicts')
  const preview = (await get('/deliveries/digest-preview')).json
  const items = Array.isArray(preview) ? preview : preview.items || []
  say(`digest preview: ${items.slice(0, 3).map((d) => `${d.urgency ?? ''} ${d.title}`).join(' | ') || '(empty)'}`)
  await page.getByText(/digest preview/).first().scrollIntoViewIfNeeded()
  await shot(page, '03-digest-preview-led-by-escalated')
  for (const card of await page.getByTestId('delivery-unseen').all()) await card.hover().catch(() => {})
  await page.waitForTimeout(1500)
  say(`after hovering: unread=${JSON.stringify((await get('/deliveries/unread-count')).json)} hot.seen_at=${row(hot).seen_at} cold.seen_at=${row(cold).seen_at}`)
  await shot(page, '04-after-marking-seen')
  fs.writeFileSync(`${process.env.ACC_SHOTS}/30-salience/05-salience-transcript.txt`, out.join('\n') + '\n')
  await settings({ ambient_salience_mode: initial.ambient_salience_mode, ambient_tick_interval_s: initial.ambient_tick_interval_s, ambient_quiet_hours: initial.ambient_quiet_hours, ambient_pursuit: initial.ambient_pursuit })
}
