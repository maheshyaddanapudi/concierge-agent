# §14p-83 — a stream survives a deploy, as the browser sees it

Stack: compose, single replica, images rebuilt with M53 (backend and frontend), `default_model=openrouter:qwen/qwen3.8-max`, ambient on. A Playwright-driven Chromium opens the Chat page through the frontend's nginx proxy, sends a research message (web tools — longer than the drain), lets tokens stream for 9 s, then `DEPLOY_SKIP_BUILD=1 DEPLOY_FORCE_RECREATE=1 DRAIN_WAIT_S=10 ./deploy.sh` rolls the backend under the open `EventSource`. The script then waits for a truthful terminal state in the DOM (never a Stop button that stays), and sends a follow-up in the same conversation on the new process. Every `/chat/stream/` request the browser made is listed with its `Last-Event-ID` header and any HTTP error the proxy answered. Screenshots: `08-chat-stream-before-deploy.png`, `09-chat-stream-after-deploy.png`, `10-chat-follow-up-after-deploy.png`. Transcript verbatim (UTC clock; the sandbox path shortened to `$SCRATCH`).

What it shows: the browser's own reconnect (`last-event-id=3`, 7 s after `SIGUSR1`) meets the proxy's 502 while the container is recreated and `EventSource` gives up; the client then reopens every 5 s with `?after=3` — six more 502s — until the seventh attempt reaches the new process, which serves the run's record: `run_status: cancelled` (the run died with the old process; the 10 s drain is shorter than a research run). The cancelled card is rendered 2 s after `deploy.sh` returned, the Stop button is gone, and the follow-up is answered 8 s later.

The first pass of this drill, on the client as it was before the fix, ended with the run stuck "running" (Stop button up) two and a half minutes after the roll and only one reconnect attempt in the log — the defect recorded in `README.md`.

```
03:13:03.446 sent the research message (live model, web tools — longer than the 10 s drain)
03:13:12.559 shot 08-chat-stream-before-deploy
03:13:12.708 deploy: == drain (SIGUSR1: readiness first) ==
03:13:12.843 deploy!  Container concierge-agent-backend-1 Killing 
03:13:12.860 deploy!  Container concierge-agent-backend-1 Killed 
03:13:12.933 deploy: backend reports draining (/ready 503); settling 3s for the balancer
03:13:15.935 deploy: == roll ==
03:13:16.146 deploy!  Container concierge-agent-backend-1 Recreate 
03:13:43.629 deploy!  Container concierge-agent-backend-1 Recreated 
03:13:43.686 deploy!  Container concierge-agent-backend-1 Starting 
03:13:43.935 deploy!  Container concierge-agent-backend-1 Started 
03:13:51.998 deploy: backend ready (/ready 200)
03:13:52.266 deploy!  Container concierge-agent-frontend-1 Recreate 
03:13:52.602 deploy!  Container concierge-agent-frontend-1 Recreated 
03:13:52.635 deploy!  Container concierge-agent-frontend-1 Starting 
03:13:52.810 deploy!  Container concierge-agent-frontend-1 Started 
03:13:52.814 deploy: == deployed ==
03:13:52.878 deploy: {"status": "ready", "db": "ok", "accepting": true, "running": 0, "queued": 0, "max_concurrent": 0, "draining_since": null}03:13:52.883 deploy: 
03:13:52.885 deploy.sh done in 40.3 s
03:13:54.905 after the roll: cancelled pill, Stop gone (42.3 s after deploy start)
03:13:56.505 shot 09-chat-stream-after-deploy
03:13:56.535 sent the follow-up on the new process
03:14:04.600 follow-up answered
03:14:06.209 shot 10-chat-follow-up-after-deploy
SSE requests seen by the browser (proxy path, Last-Event-ID header, HTTP errors):
  03:13:03.489 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65 last-event-id=-
  03:13:19.861 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65 last-event-id=3
  03:13:19.867   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65)
  03:13:24.868 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:24.870   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3)
  03:13:29.871 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:29.875   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3)
  03:13:34.876 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:34.879   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3)
  03:13:39.880 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:39.884   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3)
  03:13:44.888 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:44.892   ↳ HTTP 502 (/api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3)
  03:13:49.891 /api/v1/chat/stream/ab35dd52-ce24-43a4-b5b8-7f9aeca3af65?after=3 last-event-id=-
  03:13:56.559 /api/v1/chat/stream/7107d3f7-bcfa-49c1-909b-babdb68d466a last-event-id=-
page (conversation pane, tail): "53-wake\n[ambient] m51-soak\n[ambient] m51-soak\nlate\nm53 rate limited\nWhat is the capital of Portugal? One word.\none more, please\n[ambient] m51-soak\n[ambient] m51-soak\n[ambient] m51-soak\n[ambient] m51-soak\n[ambient] m51-soak\n[ambient] m51-soak\nlate\nm53 rate limited\nWhat is the capital of Portugal? One word.\nUse the web tools to research what the IETF QUIC working group shipped in 2025 and write a five-bullet brief with sources.\n✕ cancelled by shutdown: the process stopped before this run finished (drain grace 25s, SHUTDOWN_GRACE_S) — retry it\nIn one sentence, what is QUIC?\n\nQUIC is a modern transport protocol built on UDP that underpins HTTP/3, offering multiplexed streams, built-in encryption, and faster connection establishment with reduced latency compared to traditional TCP+TLS setups.\n\nRUN TRACE ↗\nTARGET\nOrchestrator (auto)\nresearch-concierge\nworkspace-reporter\nworkspace-warden\nSend ⏎"
```
