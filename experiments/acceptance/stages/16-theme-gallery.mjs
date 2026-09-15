// Stage 16 — the theme gallery (spec §9 appearance): the same settled
// structured answer rendered in all four palettes, plus the Settings picker
// in each, and the picker restored to default at the end. The theme is a
// browser preference (localStorage), so each palette is applied then the
// page reloaded.
const THEMES = ['default', 'anthropic', 'openai', 'google']

export default async function ({ page, nav, shot, get, log, setTheme, openConversation, expect, expectEq }) {
  const runs = (await get('/runs?limit=50')).json
  const withArtifact = runs.find((r) => r.status === 'completed' && r.answer_ui)
  const target = withArtifact || runs.find((r) => r.status === 'completed')
  log(`answer used for the gallery: run ${target?.id} (${withArtifact ? 'structured artifact present' : 'no structured artifact on any completed run — plain answer shown'})`)
  const title = (target?.chat_message || '').slice(0, 30).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  expect(!!title, 'there is a settled answer for the gallery to render')

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
    const applied = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
    const stored = await page.evaluate(() => localStorage.getItem('concierge-theme'))
    log(`theme ${t}: html[data-theme]=${applied} localStorage=${stored}`)
    // the gallery is only a gallery if each frame is a DIFFERENT palette
    expectEq(stored, t, `the ${t} palette is the stored preference`)
    // `default` is the ABSENCE of the attribute, by design: theme.ts removes
    // `data-theme` for it and index.css defines rules only for the three
    // branded palettes, so the default look is the bare `:root`. Asserting
    // `data-theme === 'default'` could never pass.
    expectEq(
      applied,
      t === 'default' ? null : t,
      t === 'default'
        ? '…and the document carries no palette attribute (default is bare :root)'
        : '…and the document is actually painted with it',
    )
  }

  await setTheme(page, 'default')
  await nav(page, 'settings')
  await page.getByText('Appearance', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await shot(page, 'picker-restored-default')
  expectEq(
    // null, for the same reason as above: `default` is the absence of the
    // attribute. This second copy of the assumption survived the first fix.
    await page.evaluate(() => document.documentElement.getAttribute('data-theme')),
    null,
    'the picker is back on the default palette for the stages that follow',
  )
}
