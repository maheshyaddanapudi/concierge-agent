const BASE = '/api/v1'

// §18.8 auth (dark by default): a stored session token rides every request;
// any 401 raises the login gate. With auth off the token is simply absent.
export function getToken(): string | null {
  try {
    return localStorage.getItem('auth_token')
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem('auth_token', token)
    else localStorage.removeItem('auth_token')
  } catch {
    /* storage unavailable */
  }
}

export function sseUrl(path: string): string {
  const token = getToken()
  return `${BASE}${path}${token ? `${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : ''}`
}

export class ApiError extends Error {
  status: number
  detail: string
  /** seconds the server asked us to wait, from its `Retry-After` header —
   * a 429 over the spend ceiling and a 503 from a full run queue both send
   * one, and a surface that swallows it leaves the user guessing */
  retryAfter: string | null
  constructor(status: number, detail: string, retryAfter: string | null = null) {
    super(detail)
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  // a multipart body carries its own content-type (with the boundary the
  // browser generates) — setting ours would make the upload unparseable
  const isForm = typeof FormData !== 'undefined' && init?.body instanceof FormData
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { 'content-type': 'application/json' }),
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
  if (resp.status === 401) {
    window.dispatchEvent(new CustomEvent('auth:required'))
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = (await resp.json()) as { detail?: unknown }
      if (body.detail)
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-json error body */
    }
    let retryAfter: string | null = null
    try {
      retryAfter = resp.headers?.get('retry-after') ?? null
    } catch {
      /* a stubbed response without headers */
    }
    throw new ApiError(resp.status, detail, retryAfter)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  /** A multipart POST (dataset upload, §15) through the same client as every
   * other call: same auth header, same 401 gate, same ApiError on failure —
   * a raw `fetch` carried none of them. */
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form }),
}

export const RUN_EVENT_TYPES = [
  'plan',
  'route',
  'dispatch_start',
  'dispatch_end',
  'activity',
  'token',
  'thinking',
  'answer_ui',
  'charts',
  'hitl_request',
  'run_status',
  'error',
  'done',
] as const

/** How long the client keeps reopening a stream the browser gave up on
 * (an HTTP error from the proxy while the backend is being recreated)
 * before it reports the run as lost: 5 s × 36 ≈ 3 minutes, longer than a
 * `deploy.sh` roll with the M51 drain window. */
export const STREAM_REOPEN_LIMIT = 36
export const STREAM_REOPEN_MS = 5000

/** Subscribe to a run's event stream (docs/api/sse-events.md).
 *
 * M53 wire format: every run event carries a monotonic `seq` (also the SSE
 * `id:`), so the browser's automatic reconnect resumes with Last-Event-ID
 * and the server replays only what was missed. Folding is idempotent by
 * sequence here as well — a replayed event is dropped, never re-applied —
 * which is what keeps answer text from duplicating across a deploy. A
 * `reconnect` hint means the server is draining and is about to close the
 * stream politely; EventSource reconnects by itself after the hinted delay.
 *
 * What EventSource does NOT do by itself: survive an HTTP error. While the
 * backend is being recreated the proxy answers 502, the browser marks the
 * source CLOSED and never retries — the M53 browser drill caught a run
 * stuck "running" for exactly this reason. So on a CLOSED source the client
 * opens a new one itself, resuming from the last folded sequence with
 * `?after=` (a fresh EventSource carries no Last-Event-ID), until a
 * terminal event arrives or STREAM_REOPEN_LIMIT attempts are spent.
 *
 * Resume precedence: the reopen position is the LARGER of the last folded
 * `seq` and the largest `Last-Event-ID` the browser has seen. They can
 * diverge — an event with an SSE id but no `seq` in its payload advances
 * only the latter — and resuming from the smaller of the two asks the
 * server to replay history the client already has, which on a stream that
 * keeps erroring is an endless reconnect loop rather than progress. */
export function streamRun(
  runId: string,
  onEvent: (event: { type: string; payload: Record<string, unknown> }) => void,
  onEnd: () => void,
): () => void {
  let source: EventSource | null = null
  let lastSeq = 0
  let lastEventId = 0
  let ended = false
  /** where a reopen resumes from: never behind either position we hold */
  const resumeFrom = () => Math.max(lastSeq, lastEventId)
  let retryMs = STREAM_REOPEN_MS
  let reopens = 0
  let reopenTimer: ReturnType<typeof setTimeout> | null = null
  const end = () => {
    if (ended) return
    ended = true
    if (reopenTimer !== null) clearTimeout(reopenTimer)
    source?.close()
    onEnd()
  }
  const forward = (e: MessageEvent) => {
    // the SSE id the browser will resume from, tracked even for events whose
    // payload carries no `seq` — a reopen must never go backwards from it
    const eventId = Number(e.lastEventId)
    if (Number.isFinite(eventId) && eventId > lastEventId) lastEventId = eventId
    try {
      const data = JSON.parse(e.data as string) as {
        type: string
        seq?: number
        payload: Record<string, unknown>
      }
      const seq = typeof data.seq === 'number' ? data.seq : null
      if (seq !== null) {
        if (seq <= lastSeq) return // already folded — a replay after reconnect
        lastSeq = seq
      }
      onEvent(data)
      if (data.type === 'done') end()
      if (data.type === 'run_status') {
        const status = data.payload.status as string
        // terminal statuses: nothing more will be streamed for this run
        if (status === 'failed' || status === 'cancelled' || status === 'stalled') end()
      }
    } catch {
      /* ignore malformed events */
    }
  }
  const open = () => {
    if (ended) return
    reopenTimer = null
    const after = resumeFrom()
    const path = `/chat/stream/${runId}${after > 0 ? `?after=${after}` : ''}`
    const es = new EventSource(sseUrl(path))
    source = es
    for (const type of RUN_EVENT_TYPES) {
      es.addEventListener(type, forward)
    }
    es.addEventListener('reconnect', (e: MessageEvent) => {
      // the server is draining and will close; EventSource reconnects with
      // Last-Event-ID after the hinted delay — remember it for our own reopen
      try {
        const hint = JSON.parse(e.data as string) as { retry_after_ms?: number }
        if (typeof hint.retry_after_ms === 'number' && hint.retry_after_ms > 0) {
          retryMs = hint.retry_after_ms
        }
      } catch {
        /* a hint without data changes nothing */
      }
    })
    es.onerror = () => {
      // CONNECTING: a dropped connection — the browser retries by itself.
      // CLOSED: an HTTP error — the browser has given up; reopen ourselves.
      if (ended || es.readyState !== EventSource.CLOSED) return
      es.close()
      if (reopens >= STREAM_REOPEN_LIMIT) {
        onEvent({
          type: 'error',
          payload: {
            message:
              'stream lost: the server did not come back — reload to see the recorded result',
          },
        })
        end()
        return
      }
      reopens += 1
      reopenTimer = setTimeout(open, retryMs)
    }
  }
  open()
  return () => {
    ended = true
    if (reopenTimer !== null) clearTimeout(reopenTimer)
    source?.close()
  }
}
