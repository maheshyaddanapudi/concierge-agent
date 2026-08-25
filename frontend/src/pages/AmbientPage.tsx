import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useInvalidate, useSettings } from '../api/hooks'
import {
  Button,
  Chip,
  Drawer,
  EmptyState,
  Field,
  JsonBlock,
  MaskedValue,
  PageHeader,
  Select,
  StatusPill,
  TextArea,
  TextInput,
  timeAgo,
} from '../components/ui'

// spec §8.9 — the Ambient page: Routines (CRUD + fire-token lifecycle),
// Watches (standing intents + compiled-rule echo), Inbox (deliveries outbox
// with feedback capture), Ledger (fire/hold audit + intervention precision).

interface RoutineRow {
  id: string
  name: string
  description: string | null
  prompt: string
  source: string
  triggers: Record<string, unknown>[] | null
  allowlist: Record<string, unknown> | null
  autonomy: string
  budgets: Record<string, unknown> | null
  has_fire_token: boolean
  status: string
  status_reason: string | null
  consecutive_failures: number
  last_fired_at: string | null
  created_at: string | null
}

interface WatchRow {
  id: string
  text: string
  condition_type: string
  compiled: Record<string, unknown> | null
  semantic_predicate: string | null
  watermark: string | null
  cadence: {
    base_interval_s: number
    current_interval_s: number
    max_interval_s: number
    consecutive_quiet: number
    last_checked_at: string | null
  }
  expires_at: string | null
  delivery: string
  status: string
  created_at: string | null
}

interface DeliveryRow {
  id: string
  run_id: string | null
  category: string
  tier: number
  urgency: number
  title: string
  body: string | null
  channel: string | null
  delivered_at: string | null
  superseded_by: string | null
  feedback: string | null
  reward: number | null
  created_at: string | null
}

interface LedgerRow {
  id: string
  kind: string
  source: string
  verdict: string | null
  verdict_reason: string | null
  decision: Record<string, unknown> | null
  depth: number
  correlation_id: string | null
  received_at: string | null
}

interface PrecisionRow {
  category: string
  precision: number | null
  judged: number
  tier_override: number | null
  override_reason: string | null
  override_source: string | null
}

const TIER_LABEL = ['interrupt', 'notify', 'digest', 'silent']
const TIER_TONE = [
  'text-rose-300 ring-rose-500/40',
  'text-amber-300 ring-amber-500/40',
  'text-sky-300 ring-sky-500/40',
  'text-slate-400 ring-slate-600',
]

function TierBadge({ tier }: { tier: number }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ring-1 ${TIER_TONE[tier] ?? TIER_TONE[3]}`}
    >
      {tier} · {TIER_LABEL[tier] ?? '?'}
    </span>
  )
}

function RoutinesTab() {
  const invalidate = useInvalidate()
  const { data } = useQuery({
    queryKey: ['routines'],
    queryFn: () => api.get<RoutineRow[]>('/routines'),
    refetchInterval: 10000,
  })
  const [selected, setSelected] = useState<RoutineRow | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [autonomy, setAutonomy] = useState('propose')
  const [triggers, setTriggers] = useState('[{"type": "interval", "seconds": 3600}]')
  const [token, setToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      invalidate('routines')
    } catch (e) {
      setError(String(e))
    }
  }

  const create = () =>
    act(async () => {
      const parsed = triggers.trim() ? (JSON.parse(triggers) as unknown) : null
      await api.post('/routines', { name, prompt, autonomy, triggers: parsed })
      setCreating(false)
      setName('')
      setPrompt('')
    })

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs text-slate-500">
          stored, trusted work definitions — fired by schedule, webhook token, or wakeup
        </div>
        <Button onClick={() => setCreating(true)}>New routine</Button>
      </div>
      {error && <div className="mb-2 text-xs text-rose-300">{error}</div>}
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-void-950/70 font-mono text-[10px] uppercase tracking-widest text-slate-500">
            <tr>
              <th className="px-3 py-2">name</th>
              <th className="px-3 py-2">status</th>
              <th className="px-3 py-2">triggers</th>
              <th className="px-3 py-2">autonomy</th>
              <th className="px-3 py-2">failures</th>
              <th className="px-3 py-2">last fired</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr
                key={r.id}
                onClick={() => setSelected(r)}
                className="cursor-pointer border-t border-slate-800/60 hover:bg-slate-900/60"
              >
                <td className="px-3 py-2 font-medium text-slate-200">{r.name}</td>
                <td className="px-3 py-2">
                  <StatusPill status={r.status} title={r.status_reason ?? undefined} />
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-slate-400">
                  {(r.triggers ?? []).map((t) => String(t.type)).join(', ') || '—'}
                  {r.has_fire_token ? ' +token' : ''}
                </td>
                <td className="px-3 py-2 text-slate-400">{r.autonomy}</td>
                <td className="px-3 py-2 text-slate-400">{r.consecutive_failures}</td>
                <td className="px-3 py-2 text-slate-500">{timeAgo(r.last_fired_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(data ?? []).length === 0 && (
          <EmptyState>no routines yet — create one or POST /api/v1/routines</EmptyState>
        )}
      </div>

      <Drawer open={creating} onClose={() => setCreating(false)} title="New routine">
        <div className="space-y-3">
          <Field label="name">
            <TextInput value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="prompt (trusted instruction)">
            <TextArea rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          </Field>
          <Field label="autonomy">
            <Select value={autonomy} onChange={(e) => setAutonomy(e.target.value)}>
              <option value="propose">propose (default)</option>
              <option value="act_reversible">act_reversible</option>
            </Select>
          </Field>
          <Field label='triggers (JSON — schedule: {"type":"interval","seconds":N} | {"type":"cron","cron":"0 9 * * *"} | {"type":"once","at":"ISO"} | {"type":"webhook","filters":[{"field":"f","op":"equals","value":"v"}]})'>
            <TextArea rows={3} value={triggers} onChange={(e) => setTriggers(e.target.value)} />
          </Field>
          {error && <div className="text-xs text-rose-300">{error}</div>}
          <Button onClick={create} disabled={!name || !prompt}>
            Create
          </Button>
        </div>
      </Drawer>

      <Drawer open={!!selected} onClose={() => { setSelected(null); setToken(null) }} title={selected?.name ?? ''}>
        {selected && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={selected.status} />
              <Chip>{selected.source}</Chip>
              <Chip>{selected.autonomy}</Chip>
              {selected.consecutive_failures > 0 && (
                <Chip tone="direct">{selected.consecutive_failures} failures</Chip>
              )}
            </div>
            {selected.status_reason && (
              <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                {selected.status_reason}
              </div>
            )}
            <Field label="prompt">
              <div className="whitespace-pre-wrap rounded bg-void-950/60 p-3 text-xs text-slate-300">
                {selected.prompt}
              </div>
            </Field>
            <Field label="triggers">
              <JsonBlock value={selected.triggers} />
            </Field>
            {selected.allowlist && (
              <Field label="allowlist (narrowed projection)">
                <JsonBlock value={selected.allowlist} />
              </Field>
            )}
            {token && (
              <Field label="fire token (shown once — store it now)">
                <MaskedValue value={token} />
              </Field>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="ghost"
                onClick={() =>
                  act(async () => {
                    await api.patch(`/routines/${selected.id}`, {
                      status: selected.status === 'active' ? 'paused' : 'active',
                    })
                    setSelected(null)
                  })
                }
              >
                {selected.status === 'active' ? 'Pause' : 'Resume'}
              </Button>
              <Button
                variant="ghost"
                onClick={() =>
                  act(async () => {
                    const out = await api.post<{ fire_token: string }>(
                      `/routines/${selected.id}/token`,
                    )
                    setToken(out.fire_token)
                  })
                }
              >
                {selected.has_fire_token ? 'Rotate token' : 'Issue token'}
              </Button>
              {selected.has_fire_token && (
                <Button
                  variant="ghost"
                  onClick={() =>
                    act(async () => {
                      await api.delete(`/routines/${selected.id}/token`)
                      setToken(null)
                    })
                  }
                >
                  Revoke token
                </Button>
              )}
              <Button
                variant="danger"
                onClick={() =>
                  act(async () => {
                    await api.delete(`/routines/${selected.id}`)
                    setSelected(null)
                  })
                }
              >
                Delete
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}

function WatchesTab() {
  const invalidate = useInvalidate()
  const { data } = useQuery({
    queryKey: ['watches'],
    queryFn: () => api.get<{ items: WatchRow[] }>('/watches'),
    refetchInterval: 10000,
  })
  const [selected, setSelected] = useState<WatchRow | null>(null)

  const setStatus = async (id: string, status: string) => {
    await api.patch(`/watches/${id}`, { status })
    invalidate('watches')
    setSelected(null)
  }

  return (
    <div>
      <div className="mb-3 text-xs text-slate-500">
        standing intents — compiled once from your words, evaluated by the scheduler, never
        remembered in model context
      </div>
      <div className="space-y-2">
        {(data?.items ?? []).map((w) => (
          <div
            key={w.id}
            onClick={() => setSelected(w)}
            className="cursor-pointer rounded-lg border border-slate-800 bg-void-950/50 px-4 py-3 hover:bg-slate-900/60"
          >
            <div className="flex items-center gap-2">
              <StatusPill status={w.status} />
              <Chip>{w.condition_type}</Chip>
              <Chip>{w.delivery}</Chip>
              <span className="ml-auto font-mono text-[10px] text-slate-500">
                every {w.cadence.current_interval_s}s
                {w.cadence.consecutive_quiet > 0 ? ` · quiet ×${w.cadence.consecutive_quiet}` : ''}
              </span>
            </div>
            <div className="mt-1 text-sm text-slate-200">{w.text}</div>
          </div>
        ))}
      </div>
      {(data?.items ?? []).length === 0 && (
        <EmptyState>no watches — say “tell me when…” in chat</EmptyState>
      )}
      <Drawer open={!!selected} onClose={() => setSelected(null)} title="Standing watch">
        {selected && (
          <div className="space-y-4">
            <div className="text-sm text-slate-200">{selected.text}</div>
            <Field label="compiled rule (the echo you confirmed)">
              <JsonBlock value={selected.compiled} />
            </Field>
            {selected.semantic_predicate && (
              <Field label="semantic predicate (judged per candidate event)">
                <div className="rounded bg-void-950/60 p-3 text-xs text-slate-300">
                  {selected.semantic_predicate}
                </div>
              </Field>
            )}
            <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-slate-400">
              <div>watermark: {selected.watermark ?? '—'}</div>
              <div>base {selected.cadence.base_interval_s}s → now {selected.cadence.current_interval_s}s</div>
              <div>last check: {timeAgo(selected.cadence.last_checked_at)}</div>
              <div>expires: {selected.expires_at ? timeAgo(selected.expires_at) : 'never'}</div>
            </div>
            <div className="flex gap-2">
              {selected.status === 'proposed' && (
                <Button onClick={() => void setStatus(selected.id, 'active')}>Confirm</Button>
              )}
              {selected.status === 'active' && (
                <Button variant="ghost" onClick={() => void setStatus(selected.id, 'paused')}>
                  Pause
                </Button>
              )}
              {selected.status === 'paused' && (
                <Button variant="ghost" onClick={() => void setStatus(selected.id, 'active')}>
                  Resume
                </Button>
              )}
              <Button variant="danger" onClick={() => void setStatus(selected.id, 'retired')}>
                Retire
              </Button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}

function FeedbackButtons({ row, onDone }: { row: DeliveryRow; onDone: () => void }) {
  const give = async (feedback: string) => {
    await api.post(`/deliveries/${row.id}/feedback`, { feedback })
    onDone()
  }
  if (row.feedback) {
    return (
      <span className="font-mono text-[10px] text-slate-500">
        {row.feedback}
        {row.reward !== null ? ` · reward ${row.reward.toFixed(2)}` : ''}
      </span>
    )
  }
  return (
    <span className="flex gap-1">
      <Button variant="ghost" onClick={() => void give('accepted')}>✓</Button>
      <Button variant="ghost" onClick={() => void give('dismissed')}>✕</Button>
      <Button variant="ghost" onClick={() => void give('ignored')}>·</Button>
    </span>
  )
}

function DeliveryCard({ row, onDone }: { row: DeliveryRow; onDone: () => void }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-void-950/50 px-4 py-3">
      <div className="flex items-center gap-2">
        <TierBadge tier={row.tier} />
        <Chip>{row.category}</Chip>
        <span className="font-mono text-[10px] text-slate-500">urgency {row.urgency}</span>
        <span className="ml-auto flex items-center gap-2">
          <span className="font-mono text-[10px] text-slate-600">
            {row.delivered_at ? `${row.channel} · ${timeAgo(row.delivered_at)}` : 'pending'}
          </span>
          <FeedbackButtons row={row} onDone={onDone} />
        </span>
      </div>
      <div className="mt-1 text-sm text-slate-200">{row.title}</div>
      {row.body && (
        <div className="mt-1 whitespace-pre-wrap text-xs text-slate-400">{row.body.slice(0, 600)}</div>
      )}
    </div>
  )
}

function InboxTab() {
  const invalidate = useInvalidate()
  const { data: all } = useQuery({
    queryKey: ['deliveries'],
    queryFn: () => api.get<{ items: DeliveryRow[] }>('/deliveries?limit=100'),
    refetchInterval: 8000,
  })
  const { data: preview } = useQuery({
    queryKey: ['deliveries', 'digest-preview'],
    queryFn: () => api.get<{ items: DeliveryRow[] }>('/deliveries/digest-preview'),
    refetchInterval: 8000,
  })
  const refresh = () => invalidate('deliveries')
  const items = all?.items ?? []
  const delivered = items.filter((d) => d.delivered_at && d.channel !== 'silent')
  const silent = items.filter((d) => d.channel === 'silent')

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
          digest preview — what the next flush sends, urgency first
        </div>
        <div className="space-y-2">
          {(preview?.items ?? []).map((d) => (
            <DeliveryCard key={d.id} row={d} onDone={refresh} />
          ))}
        </div>
        {(preview?.items ?? []).length === 0 && <EmptyState>nothing queued for the digest</EmptyState>}
      </div>
      <div>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
          delivered — give feedback: it trains the tiering
        </div>
        <div className="space-y-2">
          {delivered.map((d) => (
            <DeliveryCard key={d.id} row={d} onDone={refresh} />
          ))}
        </div>
        {delivered.length === 0 && <EmptyState>nothing delivered yet</EmptyState>}
      </div>
      {silent.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-600">
            silent ledger — explicit decisions not to bother you
          </div>
          <div className="space-y-2 opacity-60">
            {silent.slice(0, 10).map((d) => (
              <DeliveryCard key={d.id} row={d} onDone={refresh} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface PolicyRow {
  id: string
  category: string
  tier_override: number | null
  reason: string
  source: string
  created_at: string | null
}

function LedgerTab() {
  const invalidate = useInvalidate()
  const [verdict, setVerdict] = useState('all')
  const { data } = useQuery({
    queryKey: ['ambient-ledger', verdict],
    queryFn: () => api.get<{ items: LedgerRow[] }>(`/ambient/ledger?verdict=${verdict}`),
    refetchInterval: 10000,
  })
  const { data: precision } = useQuery({
    queryKey: ['ambient-precision'],
    queryFn: () => api.get<{ items: PrecisionRow[] }>('/ambient/precision'),
    refetchInterval: 15000,
  })
  const { data: policies } = useQuery({
    queryKey: ['ambient-policies'],
    queryFn: () => api.get<{ items: PolicyRow[] }>('/ambient/policies'),
    refetchInterval: 15000,
  })
  const proposals = (policies?.items ?? []).filter((p) => p.source === 'learner_proposal')

  const revert = async (category: string) => {
    await api.post('/ambient/policies/revert', { category })
    invalidate('ambient-precision', 'ambient-policies')
  }
  const approve = async (id: string) => {
    await api.post(`/ambient/policies/${id}/approve`)
    invalidate('ambient-precision', 'ambient-policies')
  }

  return (
    <div className="space-y-6">
      {proposals.length > 0 && (
        <div>
          <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-amber-400">
            learning proposals — nothing applies until you approve
          </div>
          <div className="space-y-2">
            {proposals.map((p) => (
              <div
                key={p.id}
                className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2"
              >
                <Chip>{p.category}</Chip>
                <span className="flex-1 text-xs text-slate-300">{p.reason}</span>
                <Button onClick={() => void approve(p.id)}>Approve</Button>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
          intervention precision per category — low precision auto-downgrades one tier
        </div>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {(precision?.items ?? []).map((p) => (
            <div
              key={p.category}
              className="flex items-center gap-2 rounded-lg border border-slate-800 bg-void-950/50 px-3 py-2"
            >
              <Chip>{p.category}</Chip>
              <span className="font-mono text-xs text-slate-300">
                {p.precision === null ? '—' : `${(p.precision * 100).toFixed(0)}%`}
              </span>
              <span className="font-mono text-[10px] text-slate-600">{p.judged} judged</span>
              {p.tier_override !== null && (
                <>
                  <span
                    className="font-mono text-[10px] text-amber-300"
                    title={p.override_reason ?? undefined}
                  >
                    → tier {p.tier_override} ({p.override_source})
                  </span>
                  <Button variant="ghost" onClick={() => void revert(p.category)}>
                    revert
                  </Button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
            fire / hold audit
          </span>
          <Select value={verdict} onChange={(e) => setVerdict(e.target.value)} className="max-w-32">
            {['all', 'fired', 'held', 'dropped', 'expired', 'pending'].map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </div>
        <div className="overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-void-950/70 font-mono text-[10px] uppercase tracking-widest text-slate-500">
              <tr>
                <th className="px-3 py-2">kind</th>
                <th className="px-3 py-2">source</th>
                <th className="px-3 py-2">verdict</th>
                <th className="px-3 py-2">reason</th>
                <th className="px-3 py-2">depth</th>
                <th className="px-3 py-2">when</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((e) => (
                <tr key={e.id} className="border-t border-slate-800/60">
                  <td className="px-3 py-2 font-mono text-xs text-slate-300">{e.kind}</td>
                  <td className="px-3 py-2 text-slate-400">{e.source}</td>
                  <td className="px-3 py-2">
                    <StatusPill status={e.verdict ?? 'pending'} />
                  </td>
                  <td className="max-w-md truncate px-3 py-2 text-xs text-slate-400" title={e.verdict_reason ?? ''}>
                    {e.verdict_reason ?? '—'}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-500">
                    {e.depth > 0 ? `↳${e.depth}` : '·'}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">{timeAgo(e.received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data?.items ?? []).length === 0 && <EmptyState>no events yet</EmptyState>}
        </div>
      </div>
    </div>
  )
}

export function AmbientPage() {
  const { data: settings } = useSettings()
  const [tab, setTab] = useState<'routines' | 'watches' | 'inbox' | 'ledger'>('inbox')
  const enabled = Boolean(settings?.ambient_enabled)

  return (
    <div className="p-6">
      <PageHeader
        title="Ambient"
        subtitle="proactive work while you're away — every fire and every silence is a ledgered decision"
      />
      {!enabled ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          ambient mode is off (`ambient_enabled` false) — nothing observes, fires, or delivers.
          Enable it in Settings → Ambient.
        </div>
      ) : (
        <>
          <div className="mb-4 flex items-center gap-2">
            {(
              [
                ['inbox', 'Inbox'],
                ['routines', 'Routines'],
                ['watches', 'Watches'],
                ['ledger', 'Ledger'],
              ] as const
            ).map(([key, label]) => (
              <Button
                key={key}
                variant={tab === key ? 'primary' : 'ghost'}
                onClick={() => setTab(key)}
              >
                {label}
              </Button>
            ))}
          </div>
          {tab === 'routines' && <RoutinesTab />}
          {tab === 'watches' && <WatchesTab />}
          {tab === 'inbox' && <InboxTab />}
          {tab === 'ledger' && <LedgerTab />}
        </>
      )}
    </div>
  )
}
