// Stage 20 — heterogeneous models per role (spec §2.1 / §8): the planner and
// the formatter on a different model (and effort) from the default, set
// from the Settings page, then one gated run whose trace shows the model
// per step. Only one provider is configured in this environment, so the mix
// is between that provider's models.
import { TRIAL_MESSAGE } from './_trial.mjs'

const PLANNER = process.env.ACC_PLANNER_MODEL || 'openrouter:qwen/qwen3.6-plus'
const FORMATTER = process.env.ACC_FORMATTER_MODEL || 'openrouter:qwen/qwen3.6-plus'

export default async function ({ page, nav, shot, settings, get, log, MODEL, newConversation, askAndSettle, closeDrawer }) {
  await settings({
    orchestrator_mode: 'graph',
    default_model: MODEL,
    default_model_params: { effort: 'high' },
    planner_model: null,
    formatter_model: null,
  })
  await nav(page, 'settings')
  await page.getByLabel('Planner model').selectOption(PLANNER)
  await page.waitForTimeout(800)
  await page.getByLabel('Formatter model').selectOption(FORMATTER)
  await page.waitForTimeout(800)
  await settings({ planner_model_params: { effort: 'high' }, formatter_model_params: { effort: 'medium' } })
  await nav(page, 'settings')
  const s = (await get('/settings')).json
  log(`roles: default=${s.default_model}@${s.default_model_params?.effort} planner=${s.planner_model}@${s.planner_model_params?.effort} aggregator=${s.aggregator_model || '(default)'} formatter=${s.formatter_model}@${s.formatter_model_params?.effort}`)
  await page.getByText('Models', { exact: true }).first().scrollIntoViewIfNeeded()
  await page.waitForTimeout(400)
  await shot(page, '00-role-mix-settings')

  await nav(page, '')
  await newConversation(page)
  let gateShot = false
  const done = await askAndSettle(page, TRIAL_MESSAGE, {
    answerForm: async () => {
      if (!gateShot) {
        await shot(page, '01-gate')
        gateShot = true
      }
    },
  })
  await shot(page, '02-answer-role-mix')
  const perStep = (done.steps || []).map((x) => `${x.step_type}${x.node_id ? ':' + x.node_id : ''}=${x.model || '-'}`)
  log(`models per step: ${perStep.join(' | ')}`)
  const planModel = (done.steps || []).find((x) => x.step_type === 'plan')?.model
  const fmtModel = (done.steps || []).find((x) => x.step_type === 'format' || x.step_type === 'formatter')?.model
  log(`plan step model=${planModel} formatter step model=${fmtModel || '(no formatter step recorded)'}`)

  await nav(page, 'runs')
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(1200)
  await page.locator('.fixed.inset-0').last().getByText(/step timeline/i).first().scrollIntoViewIfNeeded().catch(() => {})
  await page.waitForTimeout(500)
  await shot(page, '03-trace-models-per-step')
  await closeDrawer(page)

  await settings({ planner_model: null, planner_model_params: null, formatter_model: null, formatter_model_params: null, default_model_params: null })
  log('roles restored to the default model')
}
