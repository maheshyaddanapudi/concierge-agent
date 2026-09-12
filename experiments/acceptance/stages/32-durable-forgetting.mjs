// Stage 32 — durable forgetting (spec §16.4, §14i steps 55–57): the forget
// controls in Settings, a fact admitted from a chat, the drawer's two verbs
// (Forget vs Erase completely), the Forgotten tab with the content-free
// tombstone, re-admission of the same fact suppressed and counted, Unforget,
// and the §17.7 rider: a learner proposal pending in the Ledger, rejected.
// Only the exact-text (hash) suppression leg runs here: the configured
// provider has no embeddings API, so the semantic legs are recorded as not
// exercisable in this environment rather than faked.
import fs from 'node:fs'
import { execSync } from 'node:child_process'

const FACT = 'The invoice S3 bucket is s3://acme-invoices-prod.'
const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
const psql = (q) => execSync(`docker exec ${DB} psql -U ${process.env.ACC_DB_USER || 'concierge'} -d ${process.env.ACC_DB_NAME || 'concierge'} -tAc "${q.replace(/"/g, '\\"')}"`, { encoding: 'utf8' }).trim()

export default async function ({ page, nav, shot, settings, get, post, log, closeDrawer, newConversation, askAndSettle }) {
  const initial = (await get('/settings')).json
  const out = [`# §14i-55..57 — durable forgetting, exact-text leg — ${new Date().toISOString()}`, '']
  const say = (l) => {
    out.push(l)
    log(l)
  }
  await settings({ orchestrator_mode: 'graph', memory_enabled: true, memory_extraction_enabled: true, memory_forget_enabled: false, ambient_enabled: true })
  await nav(page, 'settings')
  const forget = page.getByRole('switch', { name: 'Durable forgetting' }).first()
  await forget.scrollIntoViewIfNeeded()
  if ((await forget.getAttribute('aria-checked')) !== 'true') await forget.click()
  await page.waitForTimeout(1000)
  const s = (await get('/settings')).json
  say(`# forget=${s.memory_forget_enabled} similarity=${s.memory_forget_similarity} embedding_model=${s.embedding_model || '(none — exact-text suppression only)'}`)
  await shot(page, '00-settings-forget-controls')

  // a fact admitted from a chat
  await post('/memories/purge', {})
  const teach = async () => {
    await nav(page, '')
    await newConversation(page)
    const done = await askAndSettle(page, `Remember this for later: ${FACT} Reply with OK.`)
    let rows = []
    for (let i = 0; i < 45; i++) {
      rows = (await get('/memories')).json.filter((m) => /acme-invoices-prod/.test(m.text))
      if (rows.length) break
      await page.waitForTimeout(2000)
    }
    return { done, rows }
  }
  const first = await teach()
  say(`memory admitted: ${first.rows.length > 0} ${JSON.stringify(first.rows.map((m) => m.text))}`)
  await nav(page, 'memory')
  await shot(page, '01-memory-admitted')
  if (!first.rows.length) throw new Error('the fact was not extracted')
  await page.locator('tr').filter({ hasText: 'acme-invoices-prod' }).first().click()
  await page.waitForTimeout(800)
  const verbs = await page.getByRole('button', { name: /^Forget$|Erase completely/ }).allTextContents()
  say(`drawer verbs: ${verbs.join(' / ')}`)
  await shot(page, '02-drawer-forget-vs-erase')
  page.once('dialog', (d) => {
    say(`confirm: ${d.message()}`)
    void d.accept()
  })
  await page.getByRole('button', { name: 'Forget', exact: true }).click()
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: 'Forgotten' }).click()
  await page.waitForTimeout(800)
  let tomb = (await get('/memories/tombstones')).json.items || []
  say(`tombstones: ${tomb.map((t) => `${t.kind}/${t.scope} suppressed ${t.suppressed_count}× (content-free: ${'text' in t ? 'NO' : 'yes'})`).join(', ')}`)
  await shot(page, '03-forgotten-tab')

  // the same fact taught again is suppressed, not re-admitted
  const second = await teach()
  let suppressed = false
  for (let i = 0; i < 20; i++) {
    tomb = (await get('/memories/tombstones')).json.items || []
    if (tomb.some((t) => t.suppressed_count > 0)) {
      suppressed = true
      break
    }
    await page.waitForTimeout(3000)
  }
  say(`re-admission after Forget: suppressed=${suppressed} | re-admitted rows: ${second.rows.length} | tombstone counts: ${tomb.map((t) => t.suppressed_count).join(',')}`)
  await nav(page, 'memory')
  await page.getByRole('button', { name: 'Forgotten' }).click()
  await page.waitForTimeout(800)
  await shot(page, '04-suppression-counted')
  await page.getByRole('button', { name: 'Unforget' }).first().click()
  await page.waitForTimeout(1200)
  say(`tombstones after Unforget: ${((await get('/memories/tombstones')).json.items || []).length}`)
  await shot(page, '05-unforgotten')

  // the §17.7 rider: a learner proposal is inert until approved; reject it
  const pid = psql(`with ins as (insert into ambient_policies (id, category, tier_override, reason, source, created_at) values (gen_random_uuid(), 'build-noise', 2, 'learner: 9 of 11 build-noise interrupts dismissed this week', 'learner_proposal', now()) returning id) select id from ins`)
  say(`learner proposal seeded server-side: ${pid}`)
  await nav(page, 'ambient')
  await page.getByRole('tab', { name: 'Ledger' }).click()
  await page.waitForTimeout(1200)
  await page.getByText(/learning proposals/).first().waitFor({ timeout: 15000 })
  await shot(page, '06-proposal-pending')
  await page.getByRole('button', { name: 'Reject' }).first().click()
  await page.waitForTimeout(1200)
  say(`proposal after Reject: source=${psql(`select source from ambient_policies where id='${pid}'`)}; policies now: ${JSON.stringify((await get('/ambient/policies')).json).slice(0, 160)}`)
  await shot(page, '07-proposal-rejected')
  say('# semantic legs (paraphrase suppression at 0.88 / 0.85 / hybrid gate): not exercisable — the configured provider has no embeddings API; the exact-text leg above is the whole evidence from this environment')
  fs.writeFileSync(`${process.env.ACC_SHOTS}/32-durable-forgetting/transcript-leg1-hash-only.txt`, out.join('\n') + '\n')
  await settings({ memory_forget_enabled: initial.memory_forget_enabled })
}
