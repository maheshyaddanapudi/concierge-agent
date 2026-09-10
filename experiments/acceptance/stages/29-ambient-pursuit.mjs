// Stage 29 — ambient pursuit (spec §17.5 / §18.4, §14f steps 45–47): the
// presence-conditional external channels, driven live against the host
// sinks (an SMTP receiver and an SMS-gateway-shaped webhook). The matrix:
//   away   + watching       → toast fires, external channels HELD
//   away   + nobody         → both external channels PURSUE
//   quiet hours over now    → demoted, nothing sent (quiet hours beat pursuit)
//   off    + nobody         → in-app only
//   always + watching       → external fires anyway (the pre-M41 default)
// The backend must have AMBIENT_WEBHOOK_URL and SMTP_* pointing at the sinks
// (ACC_SINK_LOG is the sinks' log file on this host).
import fs from 'node:fs'
import { execSync } from 'node:child_process'

const SINK_LOG = process.env.ACC_SINK_LOG || ''
const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
const psql = (q) => execSync(`docker exec ${DB} psql -U ${process.env.ACC_DB_USER || 'concierge'} -d ${process.env.ACC_DB_NAME || 'concierge'} -tAc "${q.replace(/"/g, '\\"')}"`, { encoding: 'utf8' }).trim()
const sinkCounts = () => {
  if (!SINK_LOG || !fs.existsSync(SINK_LOG)) return { smtp: 0, webhook: 0, lines: [] }
  const lines = fs.readFileSync(SINK_LOG, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
  return { smtp: lines.filter((l) => l.kind === 'smtp').length, webhook: lines.filter((l) => l.kind === 'webhook').length, lines }
}
function hhmm(offsetMin) {
  const d = new Date(Date.now() + offsetMin * 60000)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}

export default async function ({ page, nav, shot, settings, get, log }) {
  const initial = (await get('/settings')).json
  const out = ['# §14f-45..47 — ambient pursuit against live SMTP + SMS-gateway sinks', `# ${new Date().toISOString()} · quiet hours for the non-quiet scenarios: [${hhmm(120)}, ${hhmm(150)}]`, '']
  const say = (l) => {
    out.push(l)
    log(l)
  }
  await settings({
    ambient_enabled: true,
    ambient_tick_interval_s: 15,
    ambient_quiet_hours: [hhmm(120), hhmm(150)],
    ambient_notification_budget_per_day: 40,
    ambient_salience_mode: 'off',
    ambient_channels: { interrupt: ['in_app', 'email', 'webhook'] },
  })
  const s0 = (await get('/settings')).json
  say(`# channels=${JSON.stringify(s0.ambient_channels)} budget=${s0.ambient_notification_budget_per_day} tick=${s0.ambient_tick_interval_s}s`)

  const seed = (title) => psql(`insert into deliveries (id, category, tier, urgency, title, body, created_at) values (gen_random_uuid(), 'ops', 0, 5, '${title}', 'pursuit matrix', now()) returning id`)
  const row = (id) => JSON.parse(psql(`select json_build_object('tier', tier, 'delivered_at', delivered_at, 'channel', channel, 'external', external) from deliveries where id='${id}'`))
  const settle = async (id, s) => {
    for (let i = 0; i < 40; i++) {
      const r = row(id)
      if (r.delivered_at || (r.tier > 0 && i > 8)) return r
      await new Promise((res) => setTimeout(res, 3000))
    }
    return row(id)
  }
  const scenario = async ({ code, name, pursuit, watching, quiet }) => {
    await settings({ ambient_pursuit: pursuit, ambient_quiet_hours: quiet ? [hhmm(-5), hhmm(60)] : [hhmm(120), hhmm(150)] })
    if (watching) await nav(page, 'runs')
    else {
      await page.goto('about:blank')
      log('# browser off the app; waiting for the SSE stream to unregister')
      await page.waitForTimeout(25000)
    }
    const before = sinkCounts()
    const id = seed(`PURSUIT ${code}: ${name}`)
    let toast = false
    if (watching) toast = await page.getByTestId('ambient-toaster').waitFor({ timeout: 60000 }).then(() => true).catch(() => false)
    if (watching && code === '45') await shot(page, '01-away-watching-toast-no-external')
    const r = await settle(id)
    await new Promise((res) => setTimeout(res, 4000))
    const after = sinkCounts()
    const ext = r.external ? JSON.stringify(r.external) : 'null'
    const smtp = after.smtp - before.smtp
    const hook = after.webhook - before.webhook
    return { id, r, toast, smtp, hook, ext, after }
  }

  await nav(page, 'settings')
  await settings({ ambient_pursuit: 'away' })
  await nav(page, 'settings')
  await page.getByText('Pursuit (§17.5)', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-settings-pursuit-away')

  let x = await scenario({ code: '45', name: 'away + watching', pursuit: 'away', watching: true })
  say(`${x.toast && x.smtp === 0 && x.hook === 0 ? 'PASS' : 'FAIL'}  §14f-45  away + watching → toast fires, external channels HELD`)
  say(`      toast: ${x.toast ? 'shown' : 'not shown'} | smtp +${x.smtp} | webhook +${x.hook} | ledger: ${x.ext}`)

  x = await scenario({ code: '46', name: 'away + nobody watching', pursuit: 'away', watching: false })
  say(`${x.smtp === 1 && x.hook === 1 ? 'PASS' : 'FAIL'}  §14f-46  away + nobody watching → both external channels PURSUE`)
  say(`      smtp +${x.smtp} | webhook +${x.hook} | ledger: ${x.ext}`)
  const mail = x.after.lines.filter((l) => l.kind === 'smtp').pop()
  const hook = x.after.lines.filter((l) => l.kind === 'webhook').pop()
  if (mail) say(`  --- the SMTP sink actually received ---\n  from=${mail.mail_from} to=${JSON.stringify(mail.rcpts)}\n  Subject: ${mail.subject}\n  ${String(mail.body).split('\n').filter((l) => /•|PURSUIT/.test(l)).slice(0, 3).join('\n  ')}`)
  if (hook) say(`  --- the SMS-gateway-shaped webhook sink actually received ---\n  POST ${hook.path}  ${JSON.stringify(hook.body).slice(0, 260)}`)

  x = await scenario({ code: '47a', name: 'quiet hours beat pursuit', pursuit: 'away', watching: false, quiet: true })
  say(`${x.smtp === 0 && x.hook === 0 && !x.r.delivered_at ? 'PASS' : 'FAIL'}  §14f-47a quiet hours over now beat pursuit → demoted, NOTHING sent`)
  say(`      tier ${x.r.tier} (seeded at 0) | delivered_at ${x.r.delivered_at || 'null'} | smtp +${x.smtp} | webhook +${x.hook}`)

  x = await scenario({ code: '47b', name: "pursuit 'off' + nobody watching", pursuit: 'off', watching: false })
  say(`${x.r.delivered_at && x.smtp === 0 && x.hook === 0 ? 'PASS' : 'FAIL'}  §14f-47b pursuit 'off' + nobody watching → in-app only, nothing external`)
  say(`      delivered in-app: ${x.r.delivered_at ? 'yes' : 'no'} | smtp +${x.smtp} | webhook +${x.hook} | ledger: ${x.ext}`)

  x = await scenario({ code: '47c', name: "pursuit 'always' + watching", pursuit: 'always', watching: true })
  say(`${x.smtp === 1 && x.hook === 1 ? 'PASS' : 'FAIL'}  §14f-47c pursuit 'always' + watching → external fires anyway (pre-M41 default)`)
  say(`      smtp +${x.smtp} | webhook +${x.hook} | ledger: ${x.ext}`)

  await nav(page, 'ambient')
  await page.waitForTimeout(1500)
  await shot(page, '02-inbox-pursued-deliveries')
  fs.writeFileSync(`${process.env.ACC_SHOTS}/29-ambient-pursuit/03-pursuit-matrix-transcript.txt`, out.join('\n') + '\n')
  await settings({
    ambient_pursuit: initial.ambient_pursuit,
    ambient_quiet_hours: initial.ambient_quiet_hours,
    ambient_notification_budget_per_day: initial.ambient_notification_budget_per_day,
    ambient_channels: initial.ambient_channels,
    ambient_tick_interval_s: initial.ambient_tick_interval_s,
  })
  say(`# restored: pursuit=${initial.ambient_pursuit} quiet=${JSON.stringify(initial.ambient_quiet_hours)} channels=${JSON.stringify(initial.ambient_channels)}`)
  say(`# ${out.filter((l) => l.startsWith('PASS')).length}/5 scenarios passed`)
}
