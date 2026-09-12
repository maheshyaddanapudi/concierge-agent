// Stage 19 — multi-turn conversations (spec §7.5 history): a three-turn
// conversation under the graph orchestrator and a two-turn one under
// agentic, each later turn answerable only from the earlier turns' results.
// (The original campaign's slot for this stage was provider-swap parity;
// with one provider configured here it proves conversational continuity on
// that provider — the same substitution the previous campaign made.)
export default async function ({ page, nav, shot, settings, log, newConversation, askAndSettle }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null })
  await nav(page, '')
  await newConversation(page)
  await askAndSettle(page, 'Use the sitefiles add tool to add 17 and 25, then echo the result.')
  await shot(page, 'graph-t1')
  await askAndSettle(page, 'Double the number from your previous answer. Reply with the number only.')
  await shot(page, 'graph-t2')
  const t3 = await askAndSettle(page, 'In one sentence, list both numbers from this conversation in the order they appeared.')
  await shot(page, 'graph-t3')
  log(`graph continuity check: mentions 42=${/42/.test(t3.final_answer || '')} 84=${/84/.test(t3.final_answer || '')}`)

  await settings({ orchestrator_mode: 'agentic' })
  await nav(page, '')
  await newConversation(page)
  await askAndSettle(page, 'Use the sitefiles add tool to add 30 and 12 and report the sum.')
  await shot(page, 'agentic-t1')
  const a2 = await askAndSettle(page, 'Subtract 2 from the sum you just reported. Reply with the number only.')
  await shot(page, 'agentic-t2')
  log(`agentic continuity check: mentions 40=${/40/.test(a2.final_answer || '')}`)
  await settings({ orchestrator_mode: 'graph' })
}
