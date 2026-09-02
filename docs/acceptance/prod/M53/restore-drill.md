# §14p-90 — the restore drill, timed

Stack: compose, single replica, image rebuilt with M53, the database as left by the M49–M53 drills (248 runs, 412 memory embeddings). Run on 2026-09-02T03:01:55Z: `./backup.sh` (`pg_dump -Fc` + workspace tarball into `BACKUP_DIR`), then the volume is destroyed (`docker compose down`, `docker volume rm concierge-agent_pgdata`), a fresh stack is booted on the empty volume (migrations + seeds), and `./restore.sh <dump> <workspace.tar>` restores into it. The transcript is verbatim except that the sandbox's backup directory is shown as `$BACKUP_DIR`. Times are UTC.

```
$ the data set (row counts) and a reference conversation
runs|248
run_steps|259
memories|3
memory_embeddings|412
ambient_events|151
deliveries|185
tools|29
memory_embeddings_pkey
memory_embeddings_model_idx
conversation c00354f2-dbad-47be-9c2b-2e1aae3be1ba
2 messages; last answer: Healthy — no pending work or anomalies; trigger payload contains only benign interval metadata (60s interval, trigger_index 0).

$ ./backup.sh
database  $BACKUP_DIR/concierge-20260902T030155Z.dump (2.1M)
workspace $BACKUP_DIR/concierge-20260902T030155Z.workspace.tar (12K)
took 4 s
dump=$BACKUP_DIR/concierge-20260902T030155Z.dump (2.1M)

$ fresh volume: docker compose down; docker volume rm pgdata; up db + backend (empty schema, seeds)
 Network concierge-agent_default Resource is still in use 
concierge-agent_pgdata
 Container concierge-agent-db-1 Started 
 Container concierge-agent-backend-1 Started 
fresh stack ready in 20 s
runs|0
memory_embeddings|0
GET /conversations/c00354f2-dbad-47be-9c2b-2e1aae3be1ba on the fresh stack → HTTP 404

$ ./restore.sh $BACKUP_DIR/concierge-20260902T030155Z.dump $BACKUP_DIR/concierge-20260902T030155Z.workspace.tar
== stop backend (readiness first) ==
 Container concierge-agent-backend-1 Stopping 
 Container concierge-agent-backend-1 Stopped 
== restore database ==
pg_restore took 1 s (schema, data and every index, pgvector included)
== restore workspace ==
 Container concierge-agent-backend-run-e392fb8d371d Creating 
 Container concierge-agent-backend-run-e392fb8d371d Created 
== start backend ==
 Container concierge-agent-backend-1 Starting 
 Container concierge-agent-backend-1 Started 
== restored: RTO 10 s (stop → restore → ready) ==

$ after: row counts, the pgvector index, the same conversation
runs|248
run_steps|259
memories|3
memory_embeddings|412
ambient_events|151
deliveries|185
tools|29
memory_embeddings_pkey
memory_embeddings_model_idx
messages before/after: 2 2 — identical text: True
{"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}
[('fetch', 'active'), ('filesystem', 'active')]
 Container concierge-agent-frontend-1 Started 
# end — 2026-09-02T03:02:33Z
```
