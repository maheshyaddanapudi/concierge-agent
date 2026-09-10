// Stage 31 — the salience decision surface (spec §17.5, §14h steps 52–54):
// the two role-model pickers (salience judge, memory extraction), a live
// proposal in propose mode with "Do it" / "Leave it", the layered "why
// this?" disclosure, apply → the item leads the digest, Undo restoring the
// row exactly, a low-value proposal declined, a second round on the same
// row (applied → undone → declined), and the precision auto-downgrade rule
// toggle.
import fs from 'node:fs'
import { execSync } from 'node:child_process'

const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
const psql = (q) => execSync(`docker exec ${DB} psql -U ${process.env.ACC_DB_USER || 'concierge'} -d ${process.env.ACC_DB_NAME || 'concierge'} -tAc "${q.replace(/"/g, '\\"')}"`, { encoding: 'utf8' }).trim()
const seed = (title, body, urgency) => psql(`insert into deliveries (id, category, tier, urgency, title, body, created_at) values (gen_random_uuid(), 'ops', 0, ${urgency}, '${title.replace(/'/g, "''")}', '${body.replace(/'/g, "''")}', now()) returning id`)
const row = (id) => JSON.parse(psql(`select json_build_object('tier', tier, 'delivered', delivered_at is not null, 'verdict', salience->>'verdict', 'decision', salience->>'decision', 'applied', salience->>'applied', 'judge_reward', salience->>'judge_reward') from deliveries where id='${id}'`))

export default async function ({ page, nav, shot, settings, get, log, MODEL }) {
  const initial = (await get('/settings')).json
  const out = [`# §14h-52..54 — salience decisions (propose) — ${new Date().toISOString()}`, '']
  const say = (l) => {
    out.push(l)
    log(l)
  }
  await settings({ ambient_enabled: true, ambient_tick_interval_s: 15, ambient_quiet_hours: [], ambient_salience_mode: 'propose', ambient_salience_min_urgency: 3, ambient_salience_learning: 'off', ambient_pursuit: 'off', ambient_channels: {} })

  // the two role-model pickers
  await nav(page, 'settings')
  await page.getByLabel('Salience judge model').selectOption(MODEL)
  await page.waitForTimeout(800)
  await page.getByLabel('Salience judge model').scrollIntoViewIfNeeded()
  await shot(page, '00-salience-model-picker')
  await page.getByLabel('Extraction model').selectOption(MODEL)
  await page.waitForTimeout(800)
  await page.getByLabel('Extraction model').scrollIntoViewIfNeeded()
  await shot(page, '01-extraction-model-picker')
  const s = (await get('/settings')).json
  say(`# salience judge=${s.ambient_salience_model} extraction=${s.memory_extraction_model} mode=${s.ambient_salience_mode}`)

  // two unseen deliveries judged live: one worth attention, one noise
  await page.goto('about:blank')
  await page.waitForTimeout(25000)
  const hot = seed('checkout-service error budget 92% burned, 3h left', 'error-rate SLO burning at 14x; two deploys in the window; no rollback yet; on-call not paged', 5)
  const cold = seed('nightly index rebuild finished', 'the nightly search index rebuild completed in 12 minutes with no warnings', 3)
  let h, c
  for (let i = 0; i < 40; i++) {
    h = row(hot)
    c = row(cold)
    if (h.verdict && c.verdict) break
    await new Promise((r) => setTimeout(r, 4000))
  }
  say(`escalate row judged: ${JSON.stringify(h)}`)
  say(`decline row judged: ${JSON.stringify(c)}`)

  await nav(page, 'ambient')
  await page.waitForTimeout(1200)
  const cardFor = (title) => page.locator('[data-testid^="delivery-"]').filter({ hasText: title }).first()
  const hotCard = cardFor('checkout-service error budget')
  await hotCard.scrollIntoViewIfNeeded()
  await shot(page, '02-escalate-proposal')
  await hotCard.getByRole('button', { name: 'why this?' }).click()
  await page.waitForTimeout(500)
  say(`why this: ${(await page.getByTestId('salience-why').first().textContent()).trim().slice(0, 240)}`)
  await shot(page, '03-why-this')
  await hotCard.getByRole('button', { name: 'Do it' }).click()
  await page.waitForTimeout(1500)
  say(`after Do it: ${JSON.stringify(row(hot))}`)
  await page.getByText(/digest preview/).first().scrollIntoViewIfNeeded()
  await shot(page, '04-escalate-applied')
  await cardFor('checkout-service error budget').getByRole('button', { name: 'Undo' }).click()
  await page.waitForTimeout(1500)
  say(`after Undo: ${JSON.stringify(row(hot))}`)
  await cardFor('checkout-service error budget').scrollIntoViewIfNeeded()
  await shot(page, '05-escalate-undone')

  const coldCard = cardFor('nightly index rebuild')
  await coldCard.scrollIntoViewIfNeeded()
  await shot(page, '06-low-value-proposal')
  await coldCard.getByRole('button', { name: 'Leave it' }).click()
  await page.waitForTimeout(1500)
  say(`after Leave it (cold): ${JSON.stringify(row(cold))}`)
  await shot(page, '07-declined')

  // a second round on the escalate row: applied → undone → declined
  const hot2 = cardFor('checkout-service error budget')
  if (await hot2.getByRole('button', { name: 'Do it' }).count()) {
    await hot2.getByRole('button', { name: 'Do it' }).click()
    await page.waitForTimeout(1500)
    say(`v2 after Do it: ${JSON.stringify(row(hot))}`)
    await shot(page, '08-v2-applied')
    await cardFor('checkout-service error budget').getByRole('button', { name: 'Undo' }).click()
    await page.waitForTimeout(1500)
    say(`v2 after Undo: ${JSON.stringify(row(hot))}`)
    await shot(page, '09-v2-undone')
    await cardFor('checkout-service error budget').getByRole('button', { name: 'Leave it' }).click()
    await page.waitForTimeout(1500)
    say(`v2 after Leave it: ${JSON.stringify(row(hot))}`)
    await shot(page, '10-v2-declined')
  } else {
    say('the escalate row offers no second "Do it" after Undo — the second round is not available in this build (recorded as-is)')
  }

  await nav(page, 'settings')
  const rule = page.getByRole('switch', { name: 'Precision auto-downgrade' }).first()
  await rule.scrollIntoViewIfNeeded()
  await rule.click()
  await page.waitForTimeout(800)
  say(`precision rule toggled → ${(await get('/settings')).json.ambient_precision_rule_enabled}`)
  await shot(page, '11-precision-rule-toggle')
  await rule.click()
  await page.waitForTimeout(500)
  fs.writeFileSync(`${process.env.ACC_SHOTS}/31-salience-decisions/transcript-decisions.txt`, out.join('\n') + '\n')
  await settings({
    ambient_salience_mode: initial.ambient_salience_mode,
    ambient_salience_model: initial.ambient_salience_model,
    memory_extraction_model: initial.memory_extraction_model,
    ambient_tick_interval_s: initial.ambient_tick_interval_s,
    ambient_quiet_hours: initial.ambient_quiet_hours,
    ambient_pursuit: initial.ambient_pursuit,
  })
}
