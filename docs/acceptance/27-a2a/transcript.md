```
[   0.0s] # 27-a2a — 2026-09-10T20:24:44.263Z
[   0.0s] settings ← {"orchestrator_mode":"graph","default_model_params":null,"a2a_enabled":false,"ambient_enabled":true}
[   1.6s] nav shows Remote Agents while off: 0
[   2.2s] shot 00-dark-nav-no-remote-agents.png
[   3.5s] nav shows Remote Agents after the switch: 1
[   3.6s] shot 01-enabled-nav-remote-agents.png
[   5.3s] shot 02-remote-agents-empty.png
[   6.5s] shot 03-register-form-filled.png
[   9.6s] registered: polyglot-agent status=active auth=ok tools=3 card=http://172.18.0.1:8027
[  10.1s] shot 04-agent-registered-active.png
[  11.3s] shot 05-agent-detail-card-skills-auth.png
[  11.9s] shot 06-credentials-editor-write-only.png
[  15.5s] after save + refresh: auth=ok schemes={"main":{"type":"http","scheme":"bearer"}} credentials in API response: never returned
[  15.6s] shot 07-auth-ok-after-save.png
[  18.5s] a2a tools: polyglot-agent.research, polyglot-agent.summarize, polyglot-agent.translate, polyglot-agent.research-334604, polyglot-agent.summarize-ebfce9, polyglot-agent.translate-86573d
[  18.6s] shot 08-tools-kind-a2a-projected.png
[  19.7s] shot 09-a2a-tool-drawer.png
[  23.6s] shot 10-skill-editor-a2a-tool.png
[  35.2s] overlap judge flagged the save — dialog shown
[  35.7s] create skill → {"outcome":"saved","text":"","sawOverlap":true}
[  36.3s] shot 11-skill-saved-a2a-badge.png
[  39.5s] shot 12-excomm-builder.png
[  53.5s] overlap judge flagged the save — dialog shown
[  54.0s] create sub agent → {"outcome":"saved","text":"","sawOverlap":true}
[  54.5s] shot 13-excomm-saved.png
[  56.6s] UI send: Ask the remote polyglot agent to research the history of the metric system and r
[  68.7s] shot 14-organic-plan-routes-translation.png
[ 189.7s] run e6505e83-e65b-4a92-8492-19c22d6922bb → completed after 121s
[ 191.2s] organic run → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 191.2s] answer: The remote polyglot agent did not provide any research on the history of the metric system. What it returned was only placeholder “stub-echo” text that mirrored the request back, such as: > “stub-echo
[ 191.3s] shot 15-organic-answer-completed.png
[ 194.3s] shot 16-trace-run-top.png
[ 195.0s] fenced remote output in the trace: yes (tool step expanded)
[ 195.1s] shot 17-trace-fenced-remote-output.png
[ 197.7s] UI send: Ask the remote polyglot agent to research the metric system; answer any question
[ 209.7s] shot 18-hitl-card-remote-question.png
[ 210.2s] shot 19-hitl-reply-typed.png
[ 316.5s] question run → completed; answer: I couldn’t get substantive research from the remote polyglot agent. It returned only stub/echo messages, including `stub-answered: the 1790s`, and later simply 
[ 316.7s] shot 20-hitl-approved-remote-completed.png
[ 317.2s] UI send: Ask the remote polyglot agent to research the metric system again.
[ 332.6s] shot 21-hitl-deny-note-typed.png
[ 368.5s] deny → completed; error: ; counterparty cancelled tasks 1 → 2
[ 368.6s] shot 22-hitl-denied-run-outcome.png
[ 369.1s] UI send: Ask the remote polyglot agent to research the metric system slowly.
[ 396.5s] shot 23-stop-midcall-remote-inflight.png
[ 397.5s] run f1e637b0-11d7-4cf1-b3f1-ccca9562566f → cancelled after 1s
[ 400.0s] stop → cancelled; counterparty cancelled tasks 2 → 3
[ 400.2s] shot 24-stopped-run.png
[ 400.2s] settings ← {"a2a_task_timeout_s":10,"a2a_poll_interval_s":5,"ambient_tick_interval_s":15,"ambient_quiet_hours":[]}
[ 400.7s] UI send: Ask the remote polyglot agent to research the metric system; if it is slow, do n
[ 514.3s] run c0f39154-6210-4a16-b277-bb09f8000a70 → completed after 112s
[ 515.5s] run c0f39154 → completed; steps: plan::completed route::completed skill:s1:completed tool_call:polyglot-agent_research:completed tool_call:polyglot-agent_research:completed route:route:step-1:completed route:route:step-2:completed skill:step-1:completed skill:step-2:completed aggregate::completed
[ 515.5s] answer: No substantive metric-system research is available yet. The request was made with a “do not wait” constraint, but within the short non-blocking window the only 
[ 515.5s] parked note in the answer: true
[ 515.6s] shot 25-parked-answer-note.png
[ 518.5s] tasks: completed/delivered, completed/delivered, canceled, canceled, completed, completed, completed, completed, completed, completed, completed, completed/delivered, completed/delivered, completed, completed, completed, completed, completed, completed, completed, completed/delivered, completed/delivered, completed/delivered, input-required, input-required, completed/delivered, completed/delivered, completed/delivered, canceled, input-required, input-required, completed, completed, completed, completed
[ 518.7s] shot 26-task-drawer-parked.png
[ 519.1s] a2a delivery: 2/pending: [polyglot-agent] remote task completed
[ 522.0s] shot 27-ambient-inbox-a2a-delivery.png
[ 525.0s] shot 28-task-drawer-delivered.png
[ 527.5s] UI send: Ask the remote polyglot agent to research unit systems; do not wait if it is slo
[ 611.0s] run 8af415ad-a909-4742-be44-2454731d38d1 → completed after 81s
[ 612.2s] run 8af415ad → completed; steps: plan::completed route::completed skill:s1:completed tool_call:sitefiles_add:completed tool_call:sitefiles_echo:completed route:route:work:completed skill:work:completed aggregate::completed
[ 612.2s] answer: I couldn’t complete the requested unit-systems research: the remote polyglot agent was not available, so nothing was dispatched and no delayed research task was
[ 612.2s] input-required task: Metric or imperial units in the report?
[ 615.4s] shot 29-inbox-needs-input-tier1.png
[ 618.7s] shot 30-drawer-reply-typed.png
[ 622.4s] shot 31-drawer-replied-completed.png
[ 622.4s] tasks after the reply: completed, completed, canceled, canceled, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, completed, input-required, completed, completed, completed, canceled, input-required, input-required, completed, completed, completed, completed
[ 626.6s] shot 32-card-drift-new-skill.png
[ 629.4s] a2a tools after drift: polyglot-agent.research:active, polyglot-agent.summarize:active, polyglot-agent.translate:active, polyglot-agent.research-334604:active, polyglot-agent.summarize-ebfce9:active, polyglot-agent.translate-86573d:active
[ 629.6s] shot 33-drift-tool-projected.png
[ 629.7s] register keyed → 201 ok; oauth → 201 ok; mtls → 201 unsupported
[ 632.0s] auth matrix: polyglot-agent=ok/active, polyglot-agent=ok/active, keyed-agent=ok/active, oauth-agent=ok/active, mtls-agent=unsupported/active
[ 632.3s] shot 34-auth-matrix-agent-list.png
[ 633.5s] shot 35-auth-apikey-env-ok.png
[ 635.1s] shot 36-auth-unsupported-chip.png
[ 635.6s] settings ← {"a2a_task_timeout_s":120}
[ 637.7s] UI send: Use the keyed-agent.summarize tool to summarize this sentence: the metric system
[ 709.7s] run 69df0a75-4370-4713-a085-3518197101e0 → completed after 70s
[ 710.9s] run 69df0a75 → completed; steps: plan::completed route::completed skill::completed tool_call:keyed-agent_summarize-540244:completed aggregate::completed
[ 710.9s] answer: The requested summarize call did not produce a real summary. It returned only: > stub-echo: Summarize this sentence: the metric system spread with the Napoleoni
[ 710.9s] apikey-env call: completed; steps: plan::completed route::completed skill::completed tool_call:keyed-agent_summarize-540244:completed aggregate::completed; fenced: true
[ 711.1s] shot 37-auth-apikey-env-call-answer.png
[ 711.6s] UI send: Use the oauth-agent.summarize tool to summarize this sentence: the metric system
[ 751.8s] run aeec125c-cca7-4a0c-aeaa-cd740ab0ed35 → completed after 38s
[ 753.0s] run aeec125c → completed; steps: plan::completed route::completed skill::completed tool_call:oauth-agent_summarize-7a2fd5:completed aggregate::completed
[ 753.0s] answer: The requested `oauth-agent.summarize` tool did not produce a real summary; it returned only a stub/echo response. A direct summary of the sentence is: > The Nap
[ 753.0s] oauth2 call: completed; steps: plan::completed route::completed skill::completed tool_call:oauth-agent_summarize-7a2fd5:completed aggregate::completed; token requests on the counterparty: 1
[ 753.1s] shot 38-auth-oauth2-call-answer.png
[ 753.6s] UI send: Use the mtls-agent.summarize tool to summarize this sentence: the metric system 
[ 802.4s] run cc924fa5-c675-4afc-9105-3bcfe86d76a1 → completed after 47s
[ 803.6s] run cc924fa5 → completed; steps: plan::completed route::completed skill::completed tool_call:mtls-agent_summarize-f79886:failed aggregate::completed
[ 803.6s] answer: The requested `mtls-agent.summarize` call could not be completed because it returned **HTTP 401 Unauthorized**, likely due to a mutual TLS credential/configurat
[ 803.6s] unsupported-scheme call: run completed; tool step failed: HTTP Error 401: Client error '401 Unauthorized' for url 'http://172.18.0.1:8029/'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/
[ 803.7s] shot 39-auth-unsupported-call-fails.png
[ 803.8s] settings ← {"ambient_quiet_hours":["22:14","22:44"],"ambient_tick_interval_s":15,"a2a_poll_interval_s":60}
[ 803.8s] # end — 2026-09-10T20:38:08.024Z
```
