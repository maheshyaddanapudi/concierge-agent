import { vi } from 'vitest'
import { STREAM_REOPEN_LIMIT, streamRun } from '../api/client'

// M53 SSE wire format (docs/api/sse-events.md): every run event carries a
// monotonic id; the client folds each sequence number at most once, so a
// reconnect that replays overlapping history (or the same event twice) never
// duplicates answer text. A `reconnect` hint closes nothing on the client —
// EventSource reconnects on its own with Last-Event-ID. What EventSource does
// not do on its own — retry after an HTTP error, the proxy's 502 while the
// backend is recreated — the client does itself, resuming with `?after=`.

type Listener = (e: MessageEvent) => void

class FakeEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static instances: FakeEventSource[] = []
  listeners: Record<string, Listener[]> = {}
  onerror: ((e: Event) => void) | null = null
  readyState = 1
  closed = false
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: Listener) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  close() {
    this.closed = true
    this.readyState = 2
  }
  emit(type: string, data: unknown, id?: string) {
    for (const fn of this.listeners[type] ?? []) {
      fn({ data: JSON.stringify(data), lastEventId: id ?? '' } as MessageEvent)
    }
  }
  /** the browser's reaction to a dropped connection (it retries itself) */
  drop() {
    this.readyState = 0
    this.onerror?.(new Event('error'))
  }
  /** the browser's reaction to an HTTP error (it gives up for good) */
  fail() {
    this.readyState = 2
    this.onerror?.(new Event('error'))
  }
}

describe('streamRun (M53: idempotent by sequence)', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('drops an event whose sequence it has already folded', () => {
    const seen: string[] = []
    streamRun(
      'run-1',
      (e) => seen.push(`${e.type}:${String(e.payload.text ?? e.payload.status ?? '')}`),
      () => undefined,
    )
    const source = FakeEventSource.instances[0]
    source.emit('token', { type: 'token', seq: 1, payload: { text: 'Hel' } }, '1')
    source.emit('token', { type: 'token', seq: 2, payload: { text: 'lo' } }, '2')
    // a reconnect replays overlapping history: same seq, same text
    source.emit('token', { type: 'token', seq: 1, payload: { text: 'Hel' } }, '1')
    source.emit('token', { type: 'token', seq: 2, payload: { text: 'lo' } }, '2')
    source.emit('token', { type: 'token', seq: 3, payload: { text: '!' } }, '3')
    expect(seen).toEqual(['token:Hel', 'token:lo', 'token:!'])
  })

  it('still folds legacy events without a sequence', () => {
    const seen: string[] = []
    streamRun(
      'run-2',
      (e) => seen.push(e.type),
      () => undefined,
    )
    const source = FakeEventSource.instances[0]
    source.emit('activity', { type: 'activity', payload: { status: 'running' } })
    source.emit('activity', { type: 'activity', payload: { status: 'completed' } })
    expect(seen).toEqual(['activity', 'activity'])
  })

  it('keeps the source open on a reconnect hint and closes on done', () => {
    const ended = vi.fn()
    streamRun('run-3', () => undefined, ended)
    const source = FakeEventSource.instances[0]
    source.emit('reconnect', { reason: 'draining', retry_after_ms: 5000 })
    expect(source.closed).toBe(false)
    expect(ended).not.toHaveBeenCalled()
    source.emit('done', { type: 'done', seq: 9, payload: { answer: 'x' } }, '9')
    expect(source.closed).toBe(true)
    expect(ended).toHaveBeenCalledTimes(1)
  })

  it('a replayed terminal event after reconnect does not end the run twice', () => {
    const ended = vi.fn()
    streamRun('run-4', () => undefined, ended)
    const source = FakeEventSource.instances[0]
    source.emit('done', { type: 'done', seq: 4, payload: { answer: 'x' } }, '4')
    source.emit('done', { type: 'done', seq: 4, payload: { answer: 'x' } }, '4')
    expect(ended).toHaveBeenCalledTimes(1)
  })

  it('leaves a dropped connection to the browser (it retries with Last-Event-ID)', () => {
    vi.useFakeTimers()
    streamRun(
      'run-5',
      () => undefined,
      () => undefined,
    )
    const source = FakeEventSource.instances[0]
    source.emit('token', { type: 'token', seq: 2, payload: { text: 'a' } }, '2')
    source.drop()
    vi.advanceTimersByTime(30_000)
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(source.closed).toBe(false)
  })

  it('reopens from the last folded sequence when the browser gives up on an HTTP error', () => {
    vi.useFakeTimers()
    const seen: string[] = []
    const ended = vi.fn()
    streamRun(
      'run-6',
      (e) => seen.push(`${e.type}:${String(e.payload.text ?? e.payload.status ?? '')}`),
      ended,
    )
    const first = FakeEventSource.instances[0]
    expect(first.url).not.toContain('after=')
    first.emit('token', { type: 'token', seq: 3, payload: { text: 'Lis' } }, '3')
    // the proxy answers 502 while the backend is recreated: the browser closes for good
    first.fail()
    expect(first.closed).toBe(true)
    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(4_999)
    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeEventSource.instances).toHaveLength(2)
    const second = FakeEventSource.instances[1]
    expect(second.url).toContain('/chat/stream/run-6?after=3')
    // the new process serves the record: a replayed 3 is dropped, 4/5 fold once
    second.emit('token', { type: 'token', seq: 3, payload: { text: 'Lis' } }, '3')
    second.emit('run_status', { type: 'run_status', seq: 4, payload: { status: 'completed' } }, '4')
    second.emit('done', { type: 'done', seq: 5, payload: { answer: 'Lisbon' } }, '5')
    expect(seen).toEqual(['token:Lis', 'run_status:completed', 'done:'])
    expect(ended).toHaveBeenCalledTimes(1)
    expect(second.closed).toBe(true)
  })

  it('honours the reconnect hint delay for its own reopen and keeps `?after=` off a fresh run', () => {
    vi.useFakeTimers()
    streamRun(
      'run-7',
      () => undefined,
      () => undefined,
    )
    const first = FakeEventSource.instances[0]
    first.emit('reconnect', { reason: 'draining', retry_after_ms: 1000 })
    first.fail()
    vi.advanceTimersByTime(999)
    expect(FakeEventSource.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[1].url).not.toContain('after=')
  })

  it('reports the run as lost after the reopen budget, never silently', () => {
    vi.useFakeTimers()
    const seen: string[] = []
    const ended = vi.fn()
    streamRun('run-8', (e) => seen.push(e.type), ended)
    for (let i = 0; i < STREAM_REOPEN_LIMIT; i++) {
      FakeEventSource.instances[FakeEventSource.instances.length - 1].fail()
      vi.advanceTimersByTime(5_000)
    }
    expect(FakeEventSource.instances).toHaveLength(STREAM_REOPEN_LIMIT + 1)
    expect(ended).not.toHaveBeenCalled()
    FakeEventSource.instances[FakeEventSource.instances.length - 1].fail()
    expect(seen).toEqual(['error'])
    expect(ended).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(60_000)
    expect(FakeEventSource.instances).toHaveLength(STREAM_REOPEN_LIMIT + 1)
  })

  it('unsubscribing cancels a pending reopen', () => {
    vi.useFakeTimers()
    const stop = streamRun(
      'run-9',
      () => undefined,
      () => undefined,
    )
    FakeEventSource.instances[0].fail()
    stop()
    vi.advanceTimersByTime(10_000)
    expect(FakeEventSource.instances).toHaveLength(1)
  })
})
