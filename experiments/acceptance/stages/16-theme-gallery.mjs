// Stage 16 — the theme gallery (spec §9 appearance): the same settled
// structured answer rendered in all four palettes, plus the Settings picker
// in each, and the picker restored to default at the end. The theme is a
// browser preference (localStorage), so each palette is applied then the
// page reloaded.
const THEMES = ['default', 'anthropic', 'openai', 'google']

export default async function ({ page, nav, shot, get, log, setTheme, openConversation }) {
  const runs = (await get('/runs?limit=50')).json
  const withArtifact = runs.find((r) => r.status === 'completed' && r.answer_ui)
  const target = withArtifact || runs.find((r) => r.status === 'completed')
  log(`answer used for the gallery: run ${target?.id} (${withArtifact ? 'structured artifact present' : 'no structured artifact on any completed run — plain answer shown'})`)
  const title = (target?.chat_message || '').slice(0, 30).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (!title) throw new Error('no completed run to render — the gallery needs a settled answer')

  for (const t of THEMES) {
    await setTheme(page, t)
    await nav(page, 'settings')
    await page.getByText('Appearance', { exact: true }).first().scrollIntoViewIfNeeded()
    await page.waitForTimeout(500)
    await shot(page, `theme-${t}`)
    await nav(page, '')
    await openConversation(page, title)
    await page.waitForTimeout(800)
    await shot(page, `answer-theme-${t}`)
    log(`theme ${t}: html[data-theme]=${await page.evaluate(() => document.documentElement.getAttribute('data-theme'))} localStorage=${await page.evaluate(() => localStorage.getItem('concierge-theme'))}`)
  }

  await setTheme(page, 'default')
  await nav(page, 'settings')
  await page.getByText('Appearance', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await shot(page, 'picker-restored-default')
}
