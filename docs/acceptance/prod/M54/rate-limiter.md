# §14q-94 (limiter half) — one rate-limit budget across replicas

Auth on (`AUTH_ENABLED=1`), the bootstrap admin logged in through the balancer, `rate_limit_burst=20 / rate_limit_per_s=1`; then 60 requests through the balancer and 60 pinned one replica at a time.

```
# §14q-94 (limiter) — one rate-limit budget across replicas, auth on — 2026-09-03T00:50:30Z

$ AUTH_ENABLED=1 docker compose up -d --scale backend=3 --force-recreate backend
 Container concierge-agent-backend-3 Started 
 Container concierge-agent-backend-1 Starting 
 Container concierge-agent-backend-1 Started 
backend-1 ready after 7s on host port 8002
backend-2 ready after 1s on host port 8000
backend-3 ready after 1s on host port 8001
bootstrap admin password printed once, on backend-2

$ POST /auth/login through the balancer (:5174)

$ PATCH /settings rate_limit_burst=20 rate_limit_per_s=1
{'rate_limit_burst': 20, 'rate_limit_per_s': 1}

$ 60 GET /tools as fast as curl can, through the balancer (round-robin over the three replicas)
in 1297 ms:      21 200      39 429 
sequence: ....................XXXXXXXXXXXXXXXXXXXXXXXXXX.XXXXXXXXXXXXX

$ the bucket row in Postgres (one row for the user, shared by the three)
user:<admin-id>|0.27|00:50:44.226

$ the same 60 requests pinned one replica at a time (20 each, replica 1 → 2 → 3): the budget is one, not three
 backend-1:[....................] backend-2:[.XXXXXXXXXXXXXXXXXXX] backend-3:[XXXX.XXXXXXXXXXXXXXX]

$ auth back off: docker compose up -d --scale backend=3 --force-recreate backend
 Container concierge-agent-backend-1 Starting 
 Container concierge-agent-backend-1 Started 
backend-1 ready after 7s on host port 8005
backend-2 ready after 1s on host port 8004
backend-3 ready after 1s on host port 8003
# end §94 limiter — 2026-09-03T00:51:22Z
```
