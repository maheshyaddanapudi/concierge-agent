// Stage 34 — the builtin auth provider in the UI (spec §18.8): with
// AUTH_ENABLED=1 the app opens on the login gate; admin signs in with the
// bootstrap one-time password; a run under that identity; a member signs in
// in a second browser context and sees an empty Runs page. Run by
// prod/m34-auth.sh, which supplies ACC_AUTH_PASSWORD, ACC_MEMBER_PASSWORD
// and ACC_BEARER (the lib's API calls ride the admin session).
export default async function ({ page, context, browser, nav, shot, get, log, newConversation, askAndSettle, expect, expectEq, expectStatus }) {
  // the page may not be on the app origin yet, so localStorage can be
  // inaccessible here; the login gate below is what actually proves the
  // session is clean
  await page.evaluate(() => localStorage.removeItem('auth_token')).catch(() => {})
  await nav(page, '')
  await page.getByPlaceholder('username').waitFor({ timeout: 15000 })
  await shot(page, '00-login-gate')
  await page.getByPlaceholder('username').fill('admin')
  await page.getByPlaceholder('password').fill(process.env.ACC_AUTH_PASSWORD || '')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForTimeout(1500)
  const token = Boolean(await page.evaluate(() => localStorage.getItem('auth_token')))
  const me = (await get('/auth/me')).json
  log(`signed in: token in localStorage=${token}; me=${JSON.stringify(me)}`)
  expect(token, 'the bootstrap password signed admin in')
  expectEq(me?.username, 'admin', 'and the session identifies as admin')
  await nav(page, 'runs')
  await shot(page, '01-signed-in-admin')
  await nav(page, '')
  await newConversation(page)
  const done = await askAndSettle(page, 'In one sentence: what does a login gate protect?')
  log(`run under admin: ${done.status}`)
  expectStatus(done, 'completed', 'a run under the signed-in identity')
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
  log(`mallory's Runs page rows: ${rows} (her own runs only — admin's run is invisible to her)`)
  // §18.8 tenancy: a member sees HER runs, never the admin's
  expectEq(rows, 0, "the member's Runs page is empty — admin's run is not visible to her")
  await member.screenshot({ path: `${process.env.ACC_SHOTS}/34-auth-builtin/03-member-own-runs-only.png` })
  log('shot 03-member-own-runs-only.png (member context)')
  await other.close()
}
