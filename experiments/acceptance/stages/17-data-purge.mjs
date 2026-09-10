// Stage 17 — data purge (spec §14 step 10): the Runs table before, the
// purge from Settings › Data (browser confirm accepted), the empty Runs
// table after, and a clean run completing on the purged store.
export default async function ({ page, nav, shot, get, log, sendChat, waitRun, steps }) {
  await nav(page, 'runs')
  const before = (await get('/runs?limit=200')).json
  log(`runs before purge: ${before.length}`)
  await shot(page, '02-runs-before-purge')

  await nav(page, 'settings')
  const purge = page.getByRole('button', { name: /Purge run history/ }).first()
  await purge.scrollIntoViewIfNeeded()
  page.once('dialog', (d) => {
    log(`confirm dialog: ${d.message()}`)
    void d.accept()
  })
  await purge.click()
  await page.waitForTimeout(2500)
  const after = (await get('/runs?limit=200')).json
  const convs = (await get('/conversations')).json
  log(`runs after purge: ${after.length}; conversations: ${Array.isArray(convs) ? convs.length : '?'}`)
  await shot(page, '00-purged-settings')
  await nav(page, 'runs')
  await shot(page, '01-runs-empty-after-purge')
  if (after.length !== 0) throw new Error('purge left runs behind')

  // a clean run on the purged store
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, 'Add 40 and 2 with the sitefiles add tool and answer with the number only.')
  await page.waitForTimeout(2000)
  const r = (await get('/runs?limit=1')).json[0]
  const gate = page.getByText('HUMAN APPROVAL REQUIRED').first()
  if (await gate.waitFor({ timeout: 45000 }).then(() => true).catch(() => false)) {
    await page.getByRole('button', { name: /✓ Approve/ }).first().click()
    log('gate armed on the post-purge ask — approved')
  }
  const done = await waitRun(r.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '04-post-purge-clean-run')
  log(`post-purge run → ${done.status}; answer: ${(done.final_answer || '').slice(0, 120)}; steps: ${steps(done)}`)
}
