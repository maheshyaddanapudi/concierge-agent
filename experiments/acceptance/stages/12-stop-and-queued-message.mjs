// Stage 12 — stop and the queued message (spec §14 step 6, composer
// semantics): while a run is live the composer queues one message for this
// conversation; ■ Stop cancels the live run; the queued draft then fires on
// its own as the next turn of the same conversation.
import { TRIAL_MESSAGE } from './_trial.mjs'

export default async function ({ page, nav, shot, settings, get, log, sendChat, waitRun, steps }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null })
  await nav(page, '')
  await page.getByRole('button', { name: '+ New conversation' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await sendChat(page, TRIAL_MESSAGE)
  await page.waitForTimeout(2000)
  const r1 = (await get('/runs?limit=1')).json[0]
  log(`run 1: ${r1.id} (${r1.status})`)

  // the composer flips to queue mode while the run is live
  const box = page.getByPlaceholder(/Type a message to queue it/i)
  await box.waitFor({ timeout: 30000 })
  await box.fill('Queued while the first run was still working: what is 2 + 2? Number only.')
  await page.getByRole('button', { name: /^Queue/ }).click()
  await page.getByText(/1 message queued in this chat/i).first().waitFor({ timeout: 10000 })
  await page.waitForTimeout(500)
  await shot(page, '00-message-queued')

  // stop the live run from the composer
  await page.getByRole('button', { name: /■ Stop/ }).first().click()
  log('■ Stop clicked')
  const done1 = await waitRun(r1.id, ['cancelled', 'completed', 'failed'], 120)
  log(`run 1 → ${done1.status}; steps: ${steps(done1)}`)
  await page.waitForTimeout(1500)
  await shot(page, '01-stopped')

  // the queued draft fires as the next turn once the conversation is idle
  const r2 = await (async () => {
    for (let i = 0; i < 40; i++) {
      const latest = (await get('/runs?limit=1')).json[0]
      if (latest && latest.id !== r1.id) return latest
      await page.waitForTimeout(1000)
    }
    return null
  })()
  if (!r2) throw new Error('the queued message did not fire after the stop')
  log(`queued message fired as run ${r2.id} (conversation ${r2.conversation_id === done1.conversation_id ? 'same' : 'DIFFERENT'})`)
  const done2 = await waitRun(r2.id, ['completed', 'failed', 'cancelled'], 300)
  await page.waitForTimeout(1500)
  await shot(page, '02-after-stop-queue-state')
  log(`run 2 → ${done2.status}; answer: ${(done2.final_answer || '').slice(0, 120)}`)
  const conv = (await get(`/conversations/${done1.conversation_id}`)).json
  log(`conversation runs: ${(conv.runs || []).map((r) => r.status).join(', ')}`)
}
