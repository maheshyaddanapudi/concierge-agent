```
[   0.0s] # 27-a2a — 2026-09-11T22:57:10.878Z
[   0.1s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"a2a_enabled":false,"ambient_enabled":true}
[   1.8s] nav shows Remote Agents while off: 0
[   2.4s] shot 00-dark-nav-no-remote-agents.png
[   3.6s] nav shows Remote Agents after the switch: 1
[   3.8s] shot 01-enabled-nav-remote-agents.png
[   3.9s] delete polyglot-agent → HTTP 204
[   3.9s] delete polyglot-agent → HTTP 204
[   5.6s] shot 02-remote-agents-empty.png
[   6.7s] shot 03-register-form-filled.png
[   9.8s] registered: polyglot-agent status=active auth=ok tools=3 card=http://172.18.0.1:8027
[  10.3s] shot 04-agent-registered-active.png
[  11.5s] shot 05-agent-detail-card-skills-auth.png
[  12.0s] shot 06-credentials-editor-write-only.png
[  15.6s] after save + refresh: auth=ok schemes={"main":{"type":"http","scheme":"bearer"}} credentials in API response: never returned
[  15.8s] shot 07-auth-ok-after-save.png
[  18.6s] a2a tools: polyglot-agent.translate-58aeb6, polyglot-agent.research-9b9fa3, polyglot-agent.summarize-dc282d
[  18.7s] shot 08-tools-kind-a2a-projected.png
[  19.8s] shot 09-a2a-tool-drawer.png
[  23.5s] shot 10-skill-editor-a2a-tool.png
[  34.3s] overlap judge flagged the save — dialog shown
[  34.8s] create skill → {"outcome":"saved","text":"","sawOverlap":true}
[  35.4s] shot 11-skill-saved-a2a-badge.png
[  38.5s] shot 12-excomm-builder.png
[  56.2s] overlap judge flagged the save — dialog shown
[  56.7s] create sub agent → {"outcome":"saved","text":"","sawOverlap":true}
[  57.3s] shot 13-excomm-saved.png
[  59.3s] UI send: Ask the remote polyglot agent to research the history of the metric system and r
[  64.8s] shot 14-organic-plan-routes-translation.png
[ 125.6s] run a00f5f0a-96c7-48a8-a9cd-136fd200b3ed → completed after 61s
[ 127.1s] organic run → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research-9b9fa3:completed tool_call:polyglot-agent_research-9b9fa3:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 127.1s] answer: I asked the remote polyglot agent to research the history of the metric system. It reported that it had completed the request, but its entire response was only: `stub-echo: the history of the metric s
[ 127.2s] shot 15-organic-answer-completed.png
[ 130.2s] shot 16-trace-run-top.png
[ 130.9s] fenced remote output in the trace: yes (tool step expanded)
[ 131.0s] shot 17-trace-fenced-remote-output.png
[ 133.6s] UI send: Ask the remote polyglot agent to research the metric system; answer any question
[ 145.6s] shot 18-hitl-card-remote-question.png
[ 146.1s] shot 19-hitl-reply-typed.png
[ 196.0s] question run → completed; answer: The remote polyglot agent did not provide usable research on the metric system. It returned only a stub response — `stub-answered: the 1790s` — and asked no cla
[ 196.1s] shot 20-hitl-approved-remote-completed.png
[ 196.6s] UI send: Ask the remote polyglot agent to research the metric system again.
[ 207.0s] shot 21-hitl-deny-note-typed.png
[ 214.6s] deny → completed; error: ; counterparty cancelled tasks 2 → 3
[ 214.7s] shot 22-hitl-denied-run-outcome.png
[ 215.2s] UI send: Ask the remote polyglot agent to research the metric system slowly.
[ 236.8s] shot 23-stop-midcall-remote-inflight.png
[ 237.9s] run af3884a9-3254-4ff7-9572-058459b7f633 → cancelled after 1s
[ 240.4s] stop → cancelled; counterparty cancelled tasks 3 → 4
[ 240.5s] shot 24-stopped-run.png
[ 240.5s] settings ← {"a2a_task_timeout_s":10,"a2a_poll_interval_s":5,"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 241.0s] UI send: Ask the remote polyglot agent to research the metric system; if it is slow, do n
[ 303.9s] run 783e7602-443c-49d3-ac8b-b01a0b993d93 → completed after 61s
[ 305.1s] run 783e7602 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research-9b9fa3:completed tool_call:polyglot-agent_research-9b9fa3:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 305.1s] answer: The remote polyglot agent was asked to research the metric system, but no research content came back. The only response was that it was still working after 10 s
[ 305.1s] parked note in the answer: true
[ 305.2s] shot 25-parked-answer-note.png
[ 308.1s] tasks: parked, completed/delivered, canceled, canceled, completed, completed, completed, completed
[ 308.2s] shot 26-task-drawer-parked.png
[ 308.7s] a2a delivery: 2/pending: [polyglot-agent] remote task completed
[ 311.6s] shot 27-ambient-inbox-a2a-delivery.png
[ 314.6s] shot 28-task-drawer-delivered.png
[ 317.1s] UI send: Ask the remote polyglot agent to research unit systems; do not wait if it is slo
[ 394.1s] run e2486aa3-194b-4931-b9a9-bc4563794a03 → completed after 75s
[ 395.3s] run e2486aa3 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research-9b9fa3:completed tool_call:polyglot-agent_research-9b9fa3:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 395.3s] answer: The remote polyglot agent was asked to research unit systems, and I did not wait for it to finish. The request covered: - SI units: base units, derived units, a
[ 395.3s] input-required task: Metric or imperial units in the report?
[ 398.5s] shot 29-inbox-needs-input-tier1.png
[ 401.8s] shot 30-drawer-reply-typed.png
[ 405.5s] shot 31-drawer-replied-completed.png
[ 405.5s] tasks after the reply: input-required, completed, completed, completed, canceled, canceled, completed, completed, completed, completed
[ 409.8s] shot 32-card-drift-new-skill.png
[ 412.6s] a2a tools after drift: polyglot-agent.translate-58aeb6:active, polyglot-agent.research-9b9fa3:active, polyglot-agent.summarize-dc282d:active
[ 412.7s] shot 33-drift-tool-projected.png
[ 412.8s] register keyed → 201 ok; oauth → 201 ok; mtls → 201 unsupported
[ 415.2s] auth matrix: polyglot-agent=ok/active, keyed-agent=ok/active, oauth-agent=ok/active, mtls-agent=unsupported/active
[ 415.3s] shot 34-auth-matrix-agent-list.png
[ 416.5s] shot 35-auth-apikey-env-ok.png
[ 418.1s] shot 36-auth-unsupported-chip.png
[ 418.6s] settings ← {"a2a_task_timeout_s":10}
[ 420.7s] UI send: Use the keyed-agent.summarize tool to summarize this sentence: the metric system
[ 466.3s] run 6727f74a-9e78-4862-82d6-c26b20fc5bfb → completed after 44s
[ 467.5s] run 6727f74a → completed; steps: plan::completed route::completed tool_call:keyed-agent_summarize:completed aggregate::completed
[ 467.5s] answer: The requested summarization could not be completed from the returned result because it was only a stub echo: “Please summarize this sentence: ‘the metric system
[ 467.5s] apikey-env call: completed; steps: plan::completed route::completed tool_call:keyed-agent_summarize:completed aggregate::completed; fenced: true
[ 467.7s] shot 37-auth-apikey-env-call-answer.png
[ 468.1s] UI send: Use the oauth-agent.summarize tool to summarize this sentence: the metric system
[ 508.4s] run 393455aa-7f47-4e98-a34c-cf206bbd7716 → completed after 38s
[ 509.6s] run 393455aa → completed; steps: plan::completed route::completed tool_call:oauth-agent_summarize:completed aggregate::completed
[ 509.6s] answer: The requested summarization did not produce a summary; it returned only a stub echo of the input: “Summarize the following sentence: ‘the metric system spread w
[ 509.6s] oauth2 call: completed; steps: plan::completed route::completed tool_call:oauth-agent_summarize:completed aggregate::completed; token requests on the counterparty: 1
[ 509.7s] shot 38-auth-oauth2-call-answer.png
[ 510.2s] UI send: Use the mtls-agent.summarize tool to summarize this sentence: the metric system 
[ 527.5s] run 1fb9d9b4-3b62-4c46-bd85-1e7768fb414f → completed after 15s
[ 528.7s] run 1fb9d9b4 → completed; steps: plan::completed route::completed tool_call:mtls-agent_summarize:failed aggregate::completed
[ 528.7s] answer: The requested summary could not be completed because the summarization request failed with HTTP 401 Unauthorized. No summarized output was produced.
[ 528.7s] unsupported-scheme call: run completed; tool step failed: HTTP Error 401: Client error '401 Unauthorized' for url 'http://172.18.0.1:8029/'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/
[ 528.8s] shot 39-auth-unsupported-call-fails.png
[ 528.8s] settings ← {"ambient_quiet_hours":[],"ambient_tick_interval_s":15,"a2a_poll_interval_s":5}
[ 528.8s] # end — 2026-09-11T23:05:59.706Z
```
