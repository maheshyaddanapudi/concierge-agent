const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = (await resp.json()) as { detail?: unknown }
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* non-json error body */
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export function streamRun(
  runId: string,
  onEvent: (event: { type: string; payload: Record<string, unknown> }) => void,
  onEnd: () => void,
): () => void {
  const source = new EventSource(`${BASE}/chat/stream/${runId}`)
  const forward = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as { type: string; payload: Record<string, unknown> }
      onEvent(data)
      if (data.type === 'done') {
        source.close()
        onEnd()
      }
      if (data.type === 'run_status') {
        const status = data.payload.status as string
        if (status === 'failed' || status === 'cancelled') {
          source.close()
          onEnd()
        }
      }
    } catch {
      /* ignore malformed events */
    }
  }
  for (const type of [
    'plan',
    'route',
    'dispatch_start',
    'dispatch_end',
    'token',
    'answer_ui',
    'hitl_request',
    'run_status',
    'error',
    'done',
  ]) {
    source.addEventListener(type, forward)
  }
  source.onerror = () => {
    // EventSource retries automatically; close only when server ends
  }
  return () => source.close()
}
