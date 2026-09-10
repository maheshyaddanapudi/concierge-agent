// Stage 34 — the builtin auth provider in the UI (spec §18.8): with
// AUTH_ENABLED=1 the app opens on the login gate; admin signs in with the
// bootstrap one-time password; a run under that identity; a member signs in
// in a second browser context and sees an empty Runs page. Run by
// prod/m34-auth.sh, which supplies ACC_AUTH_PASSWORD, ACC_MEMBER_PASSWORD
// and ACC_BEARER (the lib's API calls ride the admin session).
export default async function ({ page, context, browser, nav, shot, get, log, newConversation, askAndSettle }) {
  await page.evaluate(() => localStorage.removeItem('auth_token')).catch(() => {})
  await nav(page, '')
  await page.getByPlaceholder('username').waitFor({ timeout: 15000 })
  await shot(page, '00-login-gate')
  await page.getByPlaceholder('username').fill('admin')
  await page.getByPlaceholder('password').fill(process.env.ACC_AUTH_PASSWORD || '')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForTimeout(1500)
  log(`signed in: token in localStorage=${Boolean(await page.evaluate(() => localStorage.getItem('auth_token')))}; me=${JSON.stringify((await get('/auth/me')).json)}`)
  await nav(page, 'runs')
  await shot(page, '01-signed-in-admin')
  await nav(page, '')
  await newConversation(page)
  const done = await askAndSettle(page, 'In one sentence: what does a login gate protect?')
  log(`run under admin: ${done.status}`)
  await shot(page, '02-run-under-identity')

  const other = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const member = await other.newPage()
  await member.goto(page.url().split('#')[0])
  await member.getByPlaceholder('username').fill('mallory')
  await member.getByPlaceholder('password').fill(process.env.ACC_MEMBER_PASSWORD || '')
  await member.getByRole('button', { name: 'Sign in' }).click()
  await member.waitForTimeout(1500)
  await member.goto(`${page.url().split('#')[0]}#/runs`)
  await member.waitForTimeout(1500)
  const rows = await member.locator('table tbody tr').count()
  log(`mallory's Runs page rows: ${rows} (admin's run is invisible to her)`)
  await member.screenshot({ path: `${process.env.ACC_SHOTS}/34-auth-builtin/03-member-empty-runs.png` })
  log('shot 03-member-empty-runs.png (member context)')
  await other.close()
}
