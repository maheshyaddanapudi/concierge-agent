```
[   0.0s] # 32-durable-forgetting — 2026-09-10T19:53:05.728Z
[   0.0s] settings ← {"orchestrator_mode":"graph","memory_enabled":true,"memory_extraction_enabled":true,"memory_forget_enabled":false,"ambient_enabled":true}
[   2.7s] # forget=true similarity=0.85 embedding_model=(none — exact-text suppression only)
[   2.8s] shot 00-settings-forget-controls.png
[   4.9s] UI send: Remember this for later: The invoice S3 bucket is s3://acme-invoices-prod. Reply
[  11.0s] run 44fac772-7dcd-48c2-8138-17a04d940d2e → completed after 4s
[  11.0s] run 44fac772-7dcd-48c2-8138-17a04d940d2e → completed after 0s
[  12.2s] run 44fac772 → completed; steps: plan::completed
[  12.2s] answer: OK
[  20.2s] memory admitted: true ["The invoice S3 bucket is s3://acme-invoices-prod."]
[  21.9s] shot 01-memory-admitted.png
[  22.8s] drawer verbs: Forget / Erase completely
[  22.9s] shot 02-drawer-forget-vs-erase.png
[  22.9s] confirm: Forget this memory? It is removed and will NOT be re-learned — a content-free tombstone suppresses re-admission (undo via the Forgotten list).
[  25.3s] tombstones: fact/global suppressed 0× (content-free: yes)
[  25.4s] shot 03-forgotten-tab.png
[  27.5s] UI send: Remember this for later: The invoice S3 bucket is s3://acme-invoices-prod. Reply
[  37.6s] run ab5f731b-6144-441c-aaa2-1a5f0a673283 → completed after 8s
[  37.6s] run ab5f731b-6144-441c-aaa2-1a5f0a673283 → completed after 0s
[  38.8s] run ab5f731b → completed; steps: plan::completed
[  38.8s] answer: OK
[ 129.2s] re-admission after Forget: suppressed=true | re-admitted rows: 0 | tombstone counts: 1
[ 131.7s] shot 04-suppression-counted.png
[ 133.0s] tombstones after Unforget: 0
[ 133.1s] shot 05-unforgotten.png
[ 133.2s] learner proposal seeded server-side: 72fe9261-5d36-4fcb-800f-28b561e94a67
[ 136.2s] shot 06-proposal-pending.png
[ 137.6s] proposal after Reject: source=learner_rejected; policies now: {"items":[{"id":"72fe9261-5d36-4fcb-800f-28b561e94a67","category":"build-noise","tier_override":2,"reason":"rejected 2026-09-10T19:55:21.986587+00:00: learner: 
[ 137.7s] shot 07-proposal-rejected.png
[ 137.7s] # semantic legs (paraphrase suppression at 0.88 / 0.85 / hybrid gate): not exercisable — the configured provider has no embeddings API; the exact-text leg above is the whole evidence from this environment
[ 137.7s] settings ← {"memory_forget_enabled":true}
[ 137.7s] # end — 2026-09-10T19:55:23.450Z
```
