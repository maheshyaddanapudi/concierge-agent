# §14q-91 — a run created on one replica is stopped from another

Live model (`openrouter:qwen/qwen3.8-max`). Replica A creates the run, replica B serves the cancel, replica C holds the stream.

```
# §14q-91 — a run created on one replica is stopped from another — 2026-09-03T00:42:38Z

$ PATCH /settings: live model openrouter:qwen/qwen3.8-max, formatter off (via replica 1)
{'default_model': 'openrouter:qwen/qwen3.8-max', 'formatter_enabled': False}

$ POST /chat on replica A (:8007) — a research-sized prompt on the live model
run 81a01ab9-344b-4af8-96d5-8f7f7e788fb4
GET /runs/81a01ab9-344b-4af8-96d5-8f7f7e788fb4 → owner_replica 53ca6c1b373e = backend-1, status running

$ a stream for the run held open on replica C (:8009) — curl -N, foreign to the owner
C stream so far: 0 ids; steps on the owner: 1 ['running']

$ POST /runs/81a01ab9-344b-4af8-96d5-8f7f7e788fb4/cancel served by replica B (:8008) — not the owner
{"status":"cancelled"}
HTTP 200 in 0.117507s
row after 265 ms: cancelled | cancelled by request (from ff318a532d30)
cancelled|t|53ca6c1b373e|t

$ the owner's log: how it learned of the cancel
backend-1: {"run_id": "81a01ab9-344b-4af8-96d5-8f7f7e788fb4", "reason": "cancelled by request (from ff318a532d30)", "event": "run_cancel_local" @ 2026-09-03T00:42:44.881668Z

$ 30 s later: the row never resurrects, no new steps, the provider is not called again
cancelled|cancelled by request (from ff318a532d30)|2026-09-03 00:42:44.885774+00
steps at cancel: 1, steps now: 1, llm calls on the owner since cancel: 0
steps: [(None, 'cancelled')]

$ the stream on replica C resolved from the record (run_status cancelled) when the owner announced the transition
id: 1
event: run_status
data: {"type": "run_status", "run_id": "81a01ab9-344b-4af8-96d5-8f7f7e788fb4", "ts": "2026-09-03T00:42:44.897074+00:00", "payload": {"status": "cancelled"}, "seq": 1, "replayed_from": "record"}
C stream closed by the server: sdata: {"type": "run_status", "run_id": "81a01ab9-344b-4af8-96d5-8f7f7e788fb4", "ts": "2026-09-03T00:42:44.897074+00:00", "payload": {"status": "cancelled"}, "
# end §91 — 2026-09-03T00:43:16Z
```
