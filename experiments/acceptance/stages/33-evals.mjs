// Stage 33 — evals (spec §15, §14c-31): the Evals launcher on a skill's
// drawer, a three-case dataset (exact / contains / llm_judge graders)
// uploaded through the page, the cases listed in the dataset drawer, and
// "Run eval" graded live on the default model — every case an ordinary run
// tagged eval=true.
import fs from 'node:fs'
import path from 'node:path'

export default async function ({ page, nav, shot, settings, get, post, del, log, closeDrawer }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null, evals_enabled: true, formatter_enabled: true })
  for (const s of (await get('/skills')).json) if (s.name === 'quiz-answerer') await del(`/skills/${s.id}`)
  const skill = (await post('/skills', {
    name: 'quiz-answerer',
    description: 'Answers a short factual question directly, in the form the question asks for. No tools.',
    persona: 'You are a precise quiz answerer.',
    instructions: '# Purpose\n1. Read the question.\n2. Answer it directly in exactly the form requested (one word, one sentence, two sentences). No preamble.\n',
    tool_ids: [],
  })).json
  log(`skill quiz-answerer ${skill.id}`)

  // the launcher on the skill drawer
  await nav(page, 'skills')
  await page.getByText('quiz-answerer', { exact: true }).first().click()
  await page.waitForTimeout(800)
  const launcher = page.getByRole('button', { name: 'Evals →' }).first()
  await launcher.scrollIntoViewIfNeeded()
  await shot(page, '01-skill-drawer-launcher')
  await launcher.click()
  await page.waitForTimeout(1200)
  log(`launcher → ${page.url().split('#')[1]}`)

  // the dataset, uploaded through the page
  const csv = [
    'level,target_id,input,expected,judge_notes,grader',
    `skill,${skill.id},"What is the capital of France? Answer with one word.",Paris,,exact`,
    `skill,${skill.id},"What is the chemical symbol for gold? One word.",Au,,contains`,
    `skill,${skill.id},"Why is the sky blue? Two sentences.","explains that sunlight is scattered by the atmosphere (shorter wavelengths scatter more)","Rayleigh need not be named; any correct scattering explanation passes",llm_judge`,
  ].join('\n')
  const file = path.join(process.env.ACC_SHOTS || '.', '33-evals', 'quiz-eval.csv')
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, csv + '\n')
  await page.getByTestId('eval-upload').locator('input[type=file]').setInputFiles(file)
  await page.getByPlaceholder('dataset name (optional)').fill('quiz-3')
  await page.getByRole('button', { name: 'Upload' }).click()
  await page.waitForTimeout(2000)
  const listed = (await get('/evals/datasets')).json
  const datasets = Array.isArray(listed) ? listed : listed.items || []
  const ds = datasets.find((d) => d.name === 'quiz-3') || datasets[0]
  log(`dataset: ${ds?.name} level=${ds?.level} cases=${ds?.case_count ?? ds?.cases?.length ?? '?'}`)
  await page.getByText('cases', { exact: true }).first().scrollIntoViewIfNeeded().catch(() => {})
  await shot(page, '02-dataset-uploaded')

  // run it, graded live
  await page.getByRole('button', { name: 'Run eval' }).click()
  await page.waitForTimeout(1500)
  let run = null
  for (let i = 0; i < 150; i++) {
    const runs = (await get(`/evals/runs?dataset_id=${ds.id}`)).json
    run = (Array.isArray(runs) ? runs : runs.items || [])[0]
    if (run && ['completed', 'failed'].includes(run.status)) break
    await page.waitForTimeout(3000)
  }
  const detail = run ? (await get(`/evals/runs/${run.id}`)).json : null
  log(`eval run → ${run?.status}: ${detail?.passed_cases}/${detail?.total_cases} passed, ${detail?.failed_cases} failed, ${detail?.error_cases} errors`)
  for (const r of detail?.results || []) log(`  ${r.grader}: ${r.passed ? 'pass' : r.status} score=${r.score} — ${String(r.reason || '').slice(0, 120)}`)
  await page.getByTestId('eval-results').waitFor({ timeout: 15000 }).catch(() => {})
  await page.getByTestId('eval-results').scrollIntoViewIfNeeded().catch(() => {})
  await page.waitForTimeout(800)
  await shot(page, '03-graded-results')
  // every case ran as an ordinary run — the results name them
  const caseRuns = (detail?.results || []).map((r) => r.run_id).filter(Boolean)
  const statuses = []
  for (const id of caseRuns) statuses.push((await get(`/runs/${id}`)).json?.status)
  log(`case runs on the Runs surface: ${caseRuns.length} (${statuses.join(', ')})`)
  await closeDrawer(page)
}
