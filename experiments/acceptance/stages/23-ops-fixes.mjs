// Stage 23 — ops (spec §10 / §14 step 10): the OTLP endpoint and the log
// level switched live from Settings; a per-run delete that also removes the
// run's LangGraph checkpoints (counted in the database when the db
// container is reachable); and the purge leaving the Runs table empty.
import { execSync } from 'node:child_process'

const DB = process.env.ACC_DB_CONTAINER || 'concierge-agent-db-1'
const DB_USER = process.env.ACC_DB_USER || 'concierge'
const DB_NAME = process.env.ACC_DB_NAME || 'concierge'

function sql(q) {
  try {
    return execSync(`docker exec ${DB} psql -U ${DB_USER} -d ${DB_NAME} -tAc "${q.replace(/"/g, '\\"')}"`, { encoding: 'utf8' }).trim()
  } catch {
    return null
  }
}
const ckpt = (runId) =>
  runId
    ? sql(`select (select count(*) from checkpoints where thread_id='${runId}')||'/'||(select count(*) from checkpoint_writes where thread_id='${runId}')||'/'||(select count(*) from checkpoint_blobs where thread_id='${runId}')`)
    : sql(`select (select count(*) from checkpoints)||'/'||(select count(*) from checkpoint_writes)||'/'||(select count(*) from checkpoint_blobs)`)

export default async function ({ page, nav, shot, settings, get, log, closeDrawer, click, newConversation, askAndSettle }) {
  const initial = (await get('/settings')).json
  await nav(page, 'settings')

  // OTLP endpoint, live
  const otlp = page.getByLabel('OTLP endpoint').first()
  await otlp.scrollIntoViewIfNeeded()
  await otlp.fill('http://otel-collector:4318')
  await otlp.blur()
  await page.waitForTimeout(1000)
  log(`otlp_endpoint → ${(await get('/settings')).json.otlp_endpoint}`)
  await shot(page, '02-otlp-endpoint-set')

  // log level, live
  const level = page.getByLabel('Log level').first()
  await level.selectOption('DEBUG')
  await page.waitForTimeout(1000)
  log(`log_level → ${(await get('/settings')).json.log_level}`)
  await shot(page, '03-debug-selected-visible')
  await settings({ otlp_endpoint: initial.otlp_endpoint ?? '', log_level: initial.log_level })
  log(`restored otlp_endpoint='${initial.otlp_endpoint}' log_level=${initial.log_level}`)

  // a run to delete, with its checkpoints counted
  await nav(page, '')
  await newConversation(page)
  const done = await askAndSettle(page, 'Use the sitefiles add tool to add 5 and 6 and answer with the number only.')
  const before = ckpt(done.id)
  const totalBefore = ckpt(null)
  log(`checkpoints/writes/blobs for run ${done.id.slice(0, 8)}: ${before ?? 'db not reachable'}; totals: ${totalBefore ?? '-'}`)
  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await shot(page, '04-run-drawer-before-delete')
  await click(page, 'Delete')
  await page.waitForTimeout(1500)
  const after = ckpt(done.id)
  log(`after the per-run delete: run → HTTP ${(await get(`/runs/${done.id}`)).status}; checkpoints/writes/blobs: ${after ?? 'db not reachable'}; totals: ${ckpt(null) ?? '-'}`)
  await shot(page, '05-after-per-run-delete')

  // purge → empty
  await nav(page, 'settings')
  const purge = page.getByRole('button', { name: /Purge run history/ }).first()
  await purge.scrollIntoViewIfNeeded()
  page.once('dialog', (d) => void d.accept())
  await purge.click()
  await page.waitForTimeout(2500)
  log(`after purge: runs=${(await get('/runs?limit=5')).json.length}; checkpoint totals: ${ckpt(null) ?? '-'}`)
  await nav(page, 'runs')
  await shot(page, '06-runs-empty-post-purge')
}
