# §14p-83 — rolling deploy with open streams and in-flight runs (live model)

Stack: compose, single replica, image rebuilt with M53, `default_model=openrouter:qwen/qwen3.8-max`, ambient on. Three chat runs started with a stream client each (`m53_streams.py`: manual reconnect with `Last-Event-ID`, idempotent folding by sequence), then `DEPLOY_SKIP_BUILD=1 DEPLOY_FORCE_RECREATE=1 DRAIN_WAIT_S=10 ./deploy.sh`.

```
02:27:57.173 == settings: live model, ambient on (so a leader lease exists) ==
02:27:57.337 old backend container: a413f296b75027c7392513f6d02262f5317d837e0a2c2fd64a4859af5a26584a
02:27:57.360 old leader acquired: "timestamp": "2026-09-02T02:24:33.569877Z"
02:27:57.362 == start 3 runs with streams (harness) ==
02:28:03.419 runs now: completed|1 running|3 
02:28:03.434 /ready before: {"status": "ready", "db": "ok", "accepting": true, "running": 3, "queued": 0, "max_concurrent": 8, "draining_since": null} HTTP 200
02:28:03.437 == deploy.sh (readiness-first roll; same image, force-recreate) ==
02:28:03.575 deploy: == drain (SIGUSR1: readiness first) ==
02:28:03.694 deploy:  Container concierge-agent-backend-1 Killing 
02:28:03.706 deploy:  Container concierge-agent-backend-1 Killed 
02:28:03.726 deploy: backend reports draining (/ready 503)
02:28:03.728 deploy: == roll ==
02:28:03.913 deploy:  Container concierge-agent-backend-1 Recreate 
02:28:35.158 deploy:  Container concierge-agent-backend-1 Recreated 
02:28:35.197 deploy:  Container concierge-agent-backend-1 Starting 
02:28:35.384 deploy:  Container concierge-agent-backend-1 Started 
02:28:40.675 deploy: backend ready (/ready 200)
02:28:40.934 deploy:  Container concierge-agent-frontend-1 Recreate 
02:28:41.395 deploy:  Container concierge-agent-frontend-1 Recreated 
02:28:41.443 deploy:  Container concierge-agent-frontend-1 Starting 
02:28:41.654 deploy:  Container concierge-agent-frontend-1 Started 
02:28:41.658 deploy: == deployed ==
02:28:43.695 deploy: {"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}
02:28:43.713 deploy.sh returned after 40.3 s
02:28:43.842 new backend container: 3de342ccff5ed84120528f6ed388657ee1dba78106b596b9771d031096204c99
02:28:43.845 == waiting for the stream harness ==
02:28:44.007 harness exit 0
02:28:44.009 == leadership transfer ==
new: {"channel": "registry_cache_inv", "pid": 725, "event": "listener_started", "level": "info", "timestamp": "2026-09-02T02:28:39.557984Z"}
new: {"channel": "registry_cache_inv", "origin": "2595bbb62b794d2bbf4e9d50168afedc", "event": "cache_listener_started", "level": "info", "timestamp": "2026-09-02T02:28:39.558389Z"}
new: {"tier": "ambient", "kind": "leader", "event": "ambient_leader_acquired", "level": "info", "timestamp": "2026-09-02T02:28:40.372686Z"}
new: {"channel": "ambient_events", "pid": 745, "event": "listener_started", "level": "info", "timestamp": "2026-09-02T02:28:43.760475Z"}
02:28:44.054 == run rows (nothing may be left running/queued) ==
be56116e-0aa4-495f-8c4d-f15a6d345e16|completed|
372f8fcd-88da-4d79-b141-5d20b98ea99d|completed|
d3526f07-a1a3-4409-92ef-0f2169df4317|completed|
44a64a7a-d29b-4284-93fe-47be1c3a1c42|completed|
6a5847bd-14c5-41fc-9c4e-dea22cc8ab2a|completed|
c0f2da32-9e43-46ff-ae5e-182981df0a42|completed|
1c1ee928-dd34-45a1-9181-6e219a40fba6|completed|
27f1ca3d-aea3-4f42-83ef-d1864d2c3d9f|completed|
f01c43c5-a93b-4cbf-ad3d-433727ef57e1|completed|
ff2bf9be-70a3-4b5e-9995-67fad546a87e|completed|
283c2259-4047-4dba-990a-42f111e3f2f6|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUT
b108feb6-243b-481c-8b46-aa175b5842df|cancelled|cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUT
02:28:44.164 non-terminal: 0
02:28:44.166 == probe timeline (transitions only) ==
02:28:03.465 probe ready=200 health=200
02:28:03.994 probe ready=503 health=200
02:28:04.518 probe ready=000000 health=000000
02:28:40.691 probe ready=200 health=200
02:28:43.217 probe ready=000000 health=000000
02:28:43.786 probe ready=200 health=200
```

## Per-stream report

```json
[
 {
  "label": "c1",
  "run_id": "ff2bf9be-70a3-4b5e-9995-67fad546a87e",
  "row_status": "completed",
  "row_error": null,
  "client_terminal": "completed",
  "ids": "5 ids, first [1] last [5]",
  "ids_strictly_increasing": true,
  "duplicates_dropped": 0,
  "reconnects": 22,
  "reconnect_hints": 0,
  "record_replays": 2,
  "folded_chars": 0,
  "folded_is_prefix_of_final": true,
  "done_answer_equals_row": true,
  "events": [
   "1:run_status",
   "2:activity",
   "3:activity",
   "4:run_status",
   "5:done"
  ]
 },
 {
  "label": "c2",
  "run_id": "283c2259-4047-4dba-990a-42f111e3f2f6",
  "row_status": "cancelled",
  "row_error": "cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) \u2014 retry it",
  "client_terminal": "cancelled",
  "ids": "4 ids, first [1] last [4]",
  "ids_strictly_increasing": true,
  "duplicates_dropped": 0,
  "reconnects": 22,
  "reconnect_hints": 0,
  "record_replays": 1,
  "folded_chars": 0,
  "folded_is_prefix_of_final": true,
  "done_answer_equals_row": null,
  "events": [
   "1:run_status",
   "2:activity",
   "3:activity",
   "4:run_status"
  ]
 },
 {
  "label": "c3",
  "run_id": "b108feb6-243b-481c-8b46-aa175b5842df",
  "row_status": "cancelled",
  "row_error": "cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) \u2014 retry it",
  "client_terminal": "cancelled",
  "ids": "4 ids, first [1] last [4]",
  "ids_strictly_increasing": true,
  "duplicates_dropped": 0,
  "reconnects": 22,
  "reconnect_hints": 0,
  "record_replays": 1,
  "folded_chars": 0,
  "folded_is_prefix_of_final": true,
  "done_answer_equals_row": null,
  "events": [
   "1:run_status",
   "2:activity",
   "3:activity",
   "4:run_status"
  ]
 }
]
```

## Stream client logs

```
02:27:57.676 [c1] tailing run ff2bf9be-70a3-4b5e-9995-67fad546a87e
02:27:57.730 [c2] tailing run 283c2259-4047-4dba-990a-42f111e3f2f6
02:27:57.780 [c3] tailing run b108feb6-243b-481c-8b46-aa175b5842df
02:27:57.851 [c1] connected (Last-Event-ID=-)
02:27:57.852 [c2] connected (Last-Event-ID=-)
02:27:57.852 [c3] connected (Last-Event-ID=-)
02:28:04.366 [c1] server closed the stream
02:28:04.368 [c2] server closed the stream
02:28:04.368 [c3] server closed the stream
02:28:06.042 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:06.042 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:06.042 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:07.710 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:07.710 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:07.711 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:09.394 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:09.394 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:09.394 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:11.074 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:11.074 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:11.074 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:12.767 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:12.767 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:12.767 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:14.484 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:14.484 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:14.484 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:16.171 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:16.171 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:16.171 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:17.832 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:17.832 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:17.832 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:19.514 [c1] disconnected: ReadError: 
02:28:19.514 [c2] disconnected: ReadError: 
02:28:19.514 [c3] disconnected: ReadError: 
02:28:21.182 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:21.182 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:21.183 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:22.850 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:22.850 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:22.850 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:24.524 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:24.524 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:24.524 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:26.216 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:26.217 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:26.217 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:27.878 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:27.878 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:27.878 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:29.573 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:29.573 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:29.574 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:31.267 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:31.267 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:31.267 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:32.936 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:32.936 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:32.936 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:34.619 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:34.619 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:34.619 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:36.289 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:36.289 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:36.290 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:37.956 [c2] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:37.956 [c3] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:37.956 [c1] disconnected: RemoteProtocolError: Server disconnected without sending a response.
02:28:39.635 [c1] disconnected: ReadError: 
02:28:39.635 [c2] disconnected: ReadError: 
02:28:39.636 [c3] disconnected: ReadError: 
02:28:43.646 [c3] connected (Last-Event-ID=3)
02:28:43.651 [c1] connected (Last-Event-ID=3)
02:28:43.686 [c2] connected (Last-Event-ID=3)
02:28:43.698 [c1] terminal completed after 5 ids
02:28:43.702 [c3] terminal cancelled after 4 ids
02:28:43.704 [c2] terminal cancelled after 4 ids
ALL_OK
```
