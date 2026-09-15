// Stage 19 — multi-turn conversations (spec §7.5 history): a three-turn
// conversation under the graph orchestrator and a two-turn one under
// agentic, each later turn answerable only from the earlier turns' results.
// (The original campaign's slot for this stage was provider-swap parity;
// with one provider configured here it proves conversational continuity on
// that provider — the same substitution the previous campaign made.)
export default async function ({ page, nav, shot, settings, log, newConversation, askAndSettle, expectMatch, expectStatus }) {
  await settings({ orchestrator_mode: 'graph', default_model_params: null })
  await nav(page, '')
  await newConversation(page)
  const g1 = await askAndSettle(page, 'Use the sitefiles add tool to add 17 and 25, then echo the result.')
  await shot(page, 'graph-t1')
  expectStatus(g1, 'completed', 'graph turn 1')
  expectMatch(g1.final_answer, /42/, 'graph turn 1 added 17 and 25')
  const g2 = await askAndSettle(page, 'Double the number from your previous answer. Reply with the number only.')
  await shot(page, 'graph-t2')
  expectStatus(g2, 'completed', 'graph turn 2')
  // turn 2 is answerable ONLY from turn 1 — this is the continuity claim
  expectMatch(g2.final_answer, /84/, 'graph turn 2 doubled turn 1\'s answer')
  // "both numbers … in the order they appeared" was ambiguous and a model
  // answering "17 and 25" was reading it correctly — those are the numbers
  // that appeared first. Ask for the two RESULTS, which is what continuity
  // over the earlier turns actually requires.
  const t3 = await askAndSettle(page, 'In one sentence, give the two results you calculated earlier in this conversation, in order.')
  await shot(page, 'graph-t3')
  log(`graph continuity check: mentions 42=${/42/.test(t3.final_answer || '')} 84=${/84/.test(t3.final_answer || '')}`)
  expectStatus(t3, 'completed', 'graph turn 3')
  expectMatch(t3.final_answer, /42/, 'graph turn 3 recalled 42')
  expectMatch(t3.final_answer, /84/, 'graph turn 3 recalled 84')

  await settings({ orchestrator_mode: 'agentic' })
  await nav(page, '')
  await newConversation(page)
  const a1 = await askAndSettle(page, 'Use the sitefiles add tool to add 30 and 12 and report the sum.')
  await shot(page, 'agentic-t1')
  expectStatus(a1, 'completed', 'agentic turn 1')
  expectMatch(a1.final_answer, /42/, 'agentic turn 1 added 30 and 12')
  const a2 = await askAndSettle(page, 'Subtract 2 from the sum you just reported. Reply with the number only.')
  await shot(page, 'agentic-t2')
  log(`agentic continuity check: mentions 40=${/40/.test(a2.final_answer || '')}`)
  expectStatus(a2, 'completed', 'agentic turn 2')
  expectMatch(a2.final_answer, /40/, 'agentic turn 2 answered from turn 1')
  await settings({ orchestrator_mode: 'graph' })
}
