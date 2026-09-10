# Load baseline — v1

Captured 2026-09-10T22:32:02+00:00 at commit `770593c` against `http://localhost:5174`, model `fake:scripted`.
Postgres `max_connections` = 100; connections at rest = 11.

## Read path at rest

| endpoint | p50 ms | p95 ms | max ms | bytes | errors |
|---|---|---|---|---|---|
| GET /runs | 58.22 | 191.13 | 215.53 | 21707 | {} |
| GET /conversations | 42.2 | 164.44 | 204.14 | 2352 | {} |
| GET /skills | 62.36 | 154.8 | 167.51 | 13502 | {} |
| GET /tools | 40.69 | 150.42 | 162.48 | 27891 | {} |
| GET /settings | 27.66 | 144.13 | 155.86 | 3345 | {} |
| GET /memories/recall | 37.38 | 173.67 | 183.34 | 2 | {} |

Peak connections during the sweep: 17

## Run-table growth

| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |
|---|---|---|---|---|---|
| 1012 | 12.49 | 15.87 | 51636 | 7.6 | 8.34 |
| 10012 | 13.34 | 17.71 | 51636 | 9.44 | 10.63 |

## SSE subscribers

## chat: error

`RuntimeError: PATCH settings {'default_model': 'fake:scripted'} -> 422 {"detail":"default_model: provider 'fake' is not configured (API key env var missing)"}`

## sse: error

`RuntimeError: PATCH settings {'default_model': 'fake:scripted'} -> 422 {"detail":"default_model: provider 'fake' is not configured (API key env var missing)"}`

