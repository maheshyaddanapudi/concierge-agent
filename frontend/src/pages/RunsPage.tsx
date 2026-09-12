/** Runs (spec §8.6): mode badge, step timeline grouped by sub agent, nested
 * native-tool steps, route reasons, cancel / retry / delete. */
import { useState } from 'react'
import { api } from '../api/client'
import { useInvalidate, useRun, useRuns, useSkills, useSubAgents, useTools } from '../api/hooks'
import type { Run, RunStep } from '../api/types'
import { RegistryTable } from '../components/RegistryTable'
import { AnswerTrace, type AnswerUiPayload } from '../components/AnswerPanel'
import {
  Button,
  Chip,
  Drawer,
  ErrorNote,
  Field,
  JsonBlock,
  KindBadge,
  PageHeader,
  StatusPill,
  cx,
  duration,
  timeAgo,
} from '../components/ui'

const STEP_ICONS: Record<string, string> = {
  plan: '🧭',
  route: '↳',
  skill: '⚙',
  hitl: '⏸',
  tool_call: '🛠',
  aggregate: 'Σ',
  format: '🎨',
}

const VERSION_LABEL: Record<string, string> = { tool_call: 'schema', skill: 'def', route: 'def' }

/** One pinned registry entity read against the live registry: the version
 * the run saw vs the version that exists now, or gone entirely. */
interface Pinned {
  kind: 'tool' | 'skill' | 'sub_agent'
  id: string
  name: string
  pinnedVersion: number | null
  pinnedHash: string | null
}

type LiveEntity = {
  id: string
  version: number | null
  hash: string | null
  name: string
  status: string
}

export function pinnedEntities(snapshot: Record<string, unknown>): Pinned[] {
  const seen = new Map<string, Pinned>()
  const add = (p: Pinned) => {
    if (!seen.has(`${p.kind}:${p.id}`)) seen.set(`${p.kind}:${p.id}`, p)
  }
  const asRec = (v: unknown): Record<string, unknown> | null =>
    v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
  const addTool = (t: Record<string, unknown>) =>
    add({
      kind: 'tool',
      id: String(t.id),
      name: String(t.tool_key ?? t.tool_name ?? t.id),
      pinnedVersion: typeof t.schema_version === 'number' ? t.schema_version : null,
      pinnedHash: typeof t.schema_hash === 'string' ? t.schema_hash : null,
    })
  const addSkill = (s: Record<string, unknown>) => {
    add({
      kind: 'skill',
      id: String(s.id),
      name: String(s.name ?? s.id),
      pinnedVersion: typeof s.definition_version === 'number' ? s.definition_version : null,
      pinnedHash: typeof s.definition_hash === 'string' ? s.definition_hash : null,
    })
    for (const t of Array.isArray(s.tools) ? s.tools : []) {
      const rec = asRec(t)
      if (rec) addTool(rec)
    }
  }
  const addAgent = (a: Record<string, unknown>) =>
    add({
      kind: 'sub_agent',
      id: String(a.id),
      name: String(a.name ?? a.id),
      pinnedVersion: typeof a.definition_version === 'number' ? a.definition_version : null,
      pinnedHash: typeof a.definition_hash === 'string' ? a.definition_hash : null,
    })
  // agentic / direct runs: the catalog the loop could see at start
  const catalog = asRec(snapshot.catalog)
  if (catalog) {
    for (const t of Array.isArray(catalog.tools) ? catalog.tools : []) {
      const rec = asRec(t)
      if (rec) addTool(rec)
    }
    for (const s of Array.isArray(catalog.skills) ? catalog.skills : []) {
      const rec = asRec(s)
      if (rec) addSkill(rec)
    }
    for (const a of Array.isArray(catalog.sub_agents) ? catalog.sub_agents : []) {
      const rec = asRec(a)
      if (rec) addAgent(rec)
    }
  }
  // graph mode: one frozen resolution per plan entry (spec §3.6)
  for (const [key, value] of Object.entries(snapshot)) {
    if (['catalog', 'settings', 'prompts', 'build', 'context', 'catalog_calls'].includes(key))
      continue
    const entry = asRec(value)
    const payload = entry ? asRec(entry.payload) : null
    if (!payload) continue
    const snap = asRec(payload.snapshot)
    const agent = snap ? asRec(snap.sub_agent) : null
    if (agent) addAgent(agent)
    const skills = snap ? asRec(snap.skills) : null
    for (const s of skills ? Object.values(skills) : []) {
      const rec = asRec(s)
      if (rec) addSkill(rec)
    }
    const skill = asRec(payload.skill)
    if (skill) addSkill(skill)
    const tool = asRec(payload.tool)
    if (tool) addTool(tool)
    // a native sub agent's card, a direct tool's row, an ephemeral
    // worker's composed skills (rung 4)
    const native = asRec(payload.sub_agent)
    if (native) addAgent(native)
    if (typeof payload.tool_id === 'string' && !tool) addTool({ ...payload, id: payload.tool_id })
    for (const s of Array.isArray(payload.skills) ? payload.skills : []) {
      const rec = asRec(s)
      if (rec) addSkill(rec)
    }
  }
  return [...seen.values()]
}

/** The name each sub agent had when the run dispatched it: from the route
 * steps (which pin `resolved_to.entity_id` + `entity_name`) — a rename or
 * delete since never rewrites the chip. */
export function pinnedAgentNames(steps: RunStep[]): Map<string, string> {
  const names = new Map<string, string>()
  for (const s of steps) {
    if (s.step_type !== 'route') continue
    const resolved = (s.output?.resolved_to ?? null) as Record<string, unknown> | null
    const id = resolved && typeof resolved.entity_id === 'string' ? resolved.entity_id : null
    const name = resolved && typeof resolved.entity_name === 'string' ? resolved.entity_name : null
    if (id && name && !names.has(id)) names.set(id, name)
  }
  return names
}

export function compareEntity(
  pinned: Pinned,
  live: LiveEntity | undefined,
): { state: 'same' | 'changed' | 'deleted' | 'inactive' | 'unknown'; detail: string } {
  if (!live) return { state: 'deleted', detail: 'not in the registry any more' }
  if (live.status !== 'active') return { state: 'inactive', detail: `now ${live.status}` }
  if (pinned.pinnedVersion == null && pinned.pinnedHash == null)
    return { state: 'unknown', detail: 'pinned before versions were recorded' }
  const hashDiffers =
    pinned.pinnedHash != null && live.hash != null && pinned.pinnedHash !== live.hash
  const versionDiffers =
    pinned.pinnedVersion != null && live.version != null && pinned.pinnedVersion !== live.version
  if (hashDiffers || versionDiffers)
    return {
      state: 'changed',
      detail: `v${pinned.pinnedVersion ?? '?'} then · v${live.version ?? '?'} now${
        live.name !== pinned.name ? ` · renamed to ${live.name}` : ''
      }`,
    }
  return { state: 'same', detail: `v${live.version ?? '?'}` }
}

const DIFF_TONE: Record<string, string> = {
  same: 'text-emerald-400',
  changed: 'text-amber-300',
  deleted: 'text-rose-400',
  inactive: 'text-slate-400',
  unknown: 'text-slate-500',
}

/** Snapshot vs registry (hardening wave): what the run pinned — tools by
 * schema version, skills and sub agents by definition version — read against
 * the live registry, so a trace from last week says which of its inputs has
 * moved since rather than silently reading against today's records. */
function SnapshotPanel({ snapshot }: { snapshot: Record<string, unknown> }) {
  const { data: tools = [] } = useTools()
  const { data: skills = [] } = useSkills()
  const { data: agents = [] } = useSubAgents()
  const pinned = pinnedEntities(snapshot)
  const live: Record<Pinned['kind'], Map<string, LiveEntity>> = {
    tool: new Map(
      tools.map((t) => [
        t.id,
        {
          id: t.id,
          version: t.schema_version ?? null,
          hash: t.schema_hash ?? null,
          name: t.tool_key,
          status: t.deleted_at ? 'deleted' : t.status,
        },
      ]),
    ),
    skill: new Map(
      skills.map((s) => [
        s.id,
        {
          id: s.id,
          version: s.definition_version ?? null,
          hash: s.definition_hash ?? null,
          name: s.name,
          status: s.deleted_at ? 'deleted' : s.status,
        },
      ]),
    ),
    sub_agent: new Map(
      agents.map((a) => [
        a.id,
        {
          id: a.id,
          version: a.definition_version ?? null,
          hash: a.definition_hash ?? null,
          name: a.name,
          status: a.deleted_at ? 'deleted' : a.status,
        },
      ]),
    ),
  }
  const rows = pinned.map((p) => ({ p, cmp: compareEntity(p, live[p.kind].get(p.id)) }))
  const moved = rows.filter((r) => r.cmp.state !== 'same' && r.cmp.state !== 'unknown').length
  const settings = snapshot.settings as Record<string, unknown> | undefined
  const prompts = snapshot.prompts as Record<string, string> | undefined
  const context = Array.isArray(snapshot.context)
    ? (snapshot.context as { surface?: string }[])
    : undefined
  const catalogCalls = snapshot.catalog_calls as unknown[] | undefined
  const resumes = Array.isArray(snapshot.resumes) ? (snapshot.resumes as unknown[]) : undefined
  const [showSettings, setShowSettings] = useState(false)
  const [showContext, setShowContext] = useState(false)
  return (
    <div className="space-y-2" data-testid="snapshot-panel">
      <div className="text-[11px] text-slate-500" role="status">
        {rows.length === 0
          ? 'Nothing pinned by version on this run.'
          : moved === 0
            ? `All ${rows.length} pinned records still match the registry.`
            : `${moved} of ${rows.length} pinned records moved since this run.`}
        {typeof snapshot.build === 'string' ? ` Build ${snapshot.build}.` : ''}
      </div>
      {rows.length > 0 && (
        <table className="w-full text-[11px]">
          <tbody>
            {rows.map(({ p, cmp }) => (
              <tr key={`${p.kind}:${p.id}`} className="border-t border-slate-800/60">
                <td className="py-1 pr-2 text-slate-500">{p.kind.replace('_', ' ')}</td>
                <td className="py-1 pr-2">
                  <code className="text-slate-300">{p.name}</code>
                </td>
                <td className={cx('py-1 pr-2 font-medium', DIFF_TONE[cmp.state])}>{cmp.state}</td>
                <td className="py-1 text-slate-500">{cmp.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex flex-wrap gap-3 text-[11px]">
        {settings && (
          <button
            className="text-indigo-400 hover:underline"
            onClick={() => setShowSettings(!showSettings)}
          >
            {showSettings ? 'hide' : 'show'} settings as the run saw them
          </button>
        )}
        {prompts && (
          <span className="text-slate-500">
            {Object.keys(prompts).length} prompt files pinned by hash
          </span>
        )}
        {context && (
          <button
            className="text-indigo-400 hover:underline"
            onClick={() => setShowContext(!showContext)}
          >
            {showContext ? 'hide' : 'show'} injected context (
            {new Set(context.map((c) => c.surface ?? '?')).size} surfaces
            {catalogCalls ? `, ${catalogCalls.length} catalog calls` : ''})
          </button>
        )}
        {resumes && resumes.length > 0 && (
          <span className="text-amber-300/80">
            resumed {resumes.length}× under the settings of that moment (see settings)
          </span>
        )}
      </div>
      {showSettings && <JsonBlock value={{ settings, prompts, resumes }} />}
      {showContext && <JsonBlock value={{ context, catalog_calls: catalogCalls }} />}
    </div>
  )
}

function StepRow({ step, depth }: { step: RunStep; depth: number }) {
  const [open, setOpen] = useState(false)
  const rung = step.step_type === 'route' ? (step.output?.rung as string | undefined) : undefined
  return (
    <div style={{ marginLeft: depth * 20 }}>
      <button
        onClick={() => setOpen(!open)}
        className={cx(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-900',
          step.status === 'failed' && 'bg-rose-500/5',
        )}
      >
        <span className="w-5 text-center">{STEP_ICONS[step.step_type] ?? '·'}</span>
        <span className="font-medium text-slate-300">{step.step_type}</span>
        {step.entity_name && (
          // the entity's name as it was when the step ran — pinned on the
          // record, so a rename or delete since does not rewrite the trace
          <code className="text-[10px] text-slate-300">{step.entity_name}</code>
        )}
        {step.node_id && <code className="text-[10px] text-slate-500">{step.node_id}</code>}
        {rung && <Chip tone={rung === 'fallback' ? 'direct' : 'default'}>rung: {rung}</Chip>}
        {step.model && (
          <code
            className="text-[10px] text-indigo-400"
            title={step.model_params ? JSON.stringify(step.model_params) : undefined}
          >
            {step.model}
          </code>
        )}
        {step.entity_version != null && (
          // the schema / definition version the step ran against, pinned into
          // the record — a renamed parameter since then shows as a higher
          // version on the Tools page, not as a silently different trace
          <code
            className="text-[10px] text-amber-300/80"
            title={step.entity_hash ? `hash ${step.entity_hash}` : undefined}
          >
            {VERSION_LABEL[step.step_type] ?? 'v'} v{step.entity_version}
            {step.entity_hash ? ` · ${step.entity_hash.slice(0, 8)}` : ''}
          </code>
        )}
        <span className="ml-auto flex items-center gap-2 text-[10px] text-slate-500">
          {step.input_tokens + step.output_tokens > 0 && (
            <span>
              {step.input_tokens}→{step.output_tokens} tok
            </span>
          )}
          <span>{duration(step.started_at, step.finished_at)}</span>
          <StatusPill status={step.status} />
        </span>
      </button>
      {open && (
        <div className="ml-7 space-y-2 border-l border-slate-800 py-2 pl-3">
          {step.error && (
            <div className="rounded bg-rose-500/10 px-2 py-1 font-mono text-[11px] text-rose-300">
              {step.error}
            </div>
          )}
          {step.input != null && (
            <div>
              <div className="mb-1 text-[10px] uppercase text-slate-600">input</div>
              <JsonBlock value={step.input} />
            </div>
          )}
          {step.output != null && (
            <div>
              <div className="mb-1 text-[10px] uppercase text-slate-600">output</div>
              <JsonBlock value={step.output} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function StepTree({ steps }: { steps: RunStep[] }) {
  const byParent = new Map<string | null, RunStep[]>()
  for (const s of steps) {
    const key = s.parent_step_id
    byParent.set(key, [...(byParent.get(key) ?? []), s])
  }
  const render = (parent: string | null, depth: number): React.ReactNode =>
    (byParent.get(parent) ?? []).map((s) => (
      <div key={s.id}>
        <StepRow step={s} depth={depth} />
        {render(s.id, depth + 1)}
      </div>
    ))
  return <div className="space-y-0.5">{render(null, 0)}</div>
}

function RunDetail({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data: run } = useRun(runId)
  const { data: agents = [] } = useSubAgents()
  const invalidate = useInvalidate()
  const [error, setError] = useState<unknown>(null)
  if (!run) return <div className="text-sm text-slate-500">Loading…</div>

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      invalidate('runs')
    } catch (e) {
      setError(e)
    }
  }
  // the name pinned by the route step wins: a sub agent renamed or deleted
  // since the run still reads as it was, not as 'ephemeral' (worker node
  // steps share the sub_agent_id but name the SKILL, so they never feed this)
  const pinnedNames = pinnedAgentNames(run.steps ?? [])
  const agentsInvolved = [
    ...new Set(
      (run.steps ?? [])
        .filter((s) => s.sub_agent_id)
        .map(
          (s) =>
            pinnedNames.get(s.sub_agent_id as string) ??
            agents.find((a) => a.id === s.sub_agent_id)?.name ??
            'ephemeral',
        ),
    ),
  ]
  const pausedStep = (run.steps ?? []).find((s) => s.step_type === 'hitl' && s.status === 'running')
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill status={run.status} />
        <KindBadge kind={run.orchestrator_mode} />
        <span className="text-[11px] text-slate-500">
          {run.total_input_tokens}→{run.total_output_tokens} tokens ·{' '}
          {duration(run.started_at, run.finished_at)} · {timeAgo(run.started_at)}
          {run.cost_usd != null
            ? ` · $${run.cost_usd.toFixed(4)}${run.cost_priced ? '' : ' (partly unpriced)'}`
            : run.cost_priced === false
              ? ' · unpriced'
              : ''}
          {run.owner_replica ? ` · on ${run.owner_replica}` : ''}
          {run.cancel_requested_at && run.status === 'running' ? ' · cancel requested' : ''}
        </span>
      </div>
      <Field label="Message">
        <p className="text-sm text-slate-300">{run.chat_message}</p>
      </Field>
      {run.error && (
        <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {run.error}
        </div>
      )}
      {run.status === 'paused_hitl' && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
          <div className="mb-2 text-xs font-medium text-amber-300">
            ⏸ Paused for human approval
            {pausedStep ? ` — ${JSON.stringify(pausedStep.input)}` : ''}
          </div>
          <div className="flex gap-2">
            <Button
              variant="primary"
              onClick={() =>
                act(() => api.post(`/runs/${run.id}/hitl`, { decision: 'approve', note: '' }))
              }
            >
              Approve
            </Button>
            <Button
              variant="danger"
              onClick={() =>
                act(() => api.post(`/runs/${run.id}/hitl`, { decision: 'deny', note: '' }))
              }
            >
              Deny
            </Button>
          </div>
        </div>
      )}
      {run.final_answer && (
        <Field label="Answer">
          <AnswerTrace
            markdown={run.final_answer}
            payload={run.answer_ui as AnswerUiPayload | null}
            toolCharts={run.charts}
          />
        </Field>
      )}
      {agentsInvolved.length > 0 && (
        <Field label="Sub agents involved">
          <div className="flex flex-wrap gap-1">
            {agentsInvolved.map((n) => (
              <Chip key={n}>{n}</Chip>
            ))}
          </div>
        </Field>
      )}
      <Field label="Step timeline">
        <StepTree steps={run.steps ?? []} />
      </Field>
      {run.plan != null && (
        <Field label="Plan JSON">
          <JsonBlock value={run.plan} />
        </Field>
      )}
      {run.price_snapshot?.prices && Object.keys(run.price_snapshot.prices).length > 0 && (
        <Field label="Prices at finish (stamped — later price changes never rewrite this run)">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
            {Object.entries(run.price_snapshot.prices).map(([ref, p]) => (
              <span
                key={ref}
                className={p.input_per_m == null ? 'text-slate-500' : 'text-slate-300'}
              >
                <code className="text-indigo-400">{ref}</code>{' '}
                {p.input_per_m == null
                  ? 'unpriced'
                  : `$${p.input_per_m} in / $${p.output_per_m} out per M tokens`}{' '}
                <span className="text-slate-500">· {p.source ?? 'no price'}</span>
              </span>
            ))}
          </div>
        </Field>
      )}
      {run.snapshot != null && (
        <Field label="Snapshot vs registry">
          <SnapshotPanel snapshot={run.snapshot} />
        </Field>
      )}
      {run.snapshot != null && (
        <Field label="Config snapshot (frozen at dispatch)">
          <JsonBlock value={run.snapshot} />
        </Field>
      )}
      <ErrorNote error={error} />
      <div className="flex gap-2 border-t border-slate-800 pt-3">
        {run.status === 'running' && (
          <Button variant="danger" onClick={() => act(() => api.post(`/runs/${run.id}/cancel`))}>
            Cancel run
          </Button>
        )}
        {run.status === 'failed' && (
          <Button variant="primary" onClick={() => act(() => api.post(`/runs/${run.id}/retry`))}>
            Retry (re-plan)
          </Button>
        )}
        {run.status !== 'running' && (
          <Button
            variant="danger"
            onClick={() =>
              act(async () => {
                await api.delete(`/runs/${run.id}`)
                onClose()
              })
            }
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  )
}

const PAGE = 100

export function RunsPage() {
  // M50: the list is paged (newest first) and polls with backoff — the
  // M49 baseline measured the unpaged list at 9.5 MB for 10k runs
  const [limit, setLimit] = useState(PAGE)
  const { data: runs = [], isLoading } = useRuns(limit)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  return (
    <div className="p-6">
      <PageHeader
        title="Runs"
        subtitle="Every run fully traced: plan, route reasons, per-step tokens, nested tool calls."
      />
      <RegistryTable
        rows={runs}
        loading={isLoading}
        onRowClick={(r) => setSelectedId(r.id)}
        filterRow={(r: Run, q) =>
          !q ||
          r.chat_message.toLowerCase().includes(q) ||
          r.status.includes(q) ||
          r.orchestrator_mode.includes(q)
        }
        columns={[
          {
            header: 'Time',
            render: (r) => <span className="text-xs text-slate-500">{timeAgo(r.started_at)}</span>,
          },
          {
            header: 'Message',
            render: (r) => (
              <span className="line-clamp-1 max-w-md text-xs text-slate-300">{r.chat_message}</span>
            ),
          },
          { header: 'Status', render: (r) => <StatusPill status={r.status} /> },
          { header: 'Mode', render: (r) => <KindBadge kind={r.orchestrator_mode} /> },
          {
            header: 'Duration',
            render: (r) => (
              <span className="text-xs text-slate-500">
                {duration(r.started_at, r.finished_at)}
              </span>
            ),
          },
          {
            header: 'Tokens',
            render: (r) => (
              <span className="text-xs text-slate-500">
                {r.total_input_tokens}→{r.total_output_tokens}
              </span>
            ),
          },
          {
            header: 'Cost',
            render: (r) => (
              <span
                className="font-mono text-xs text-slate-500"
                title={
                  r.cost_priced === false
                    ? 'a model in play has no price — see Settings → Cost'
                    : undefined
                }
              >
                {r.cost_usd != null
                  ? `$${r.cost_usd.toFixed(4)}`
                  : r.cost_priced === false
                    ? '—'
                    : ''}
                {r.cost_usd != null && r.cost_priced === false ? '+' : ''}
              </span>
            ),
          },
        ]}
      />
      {runs.length >= limit && (
        <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
          <span>Showing the newest {runs.length} runs.</span>
          <Button onClick={() => setLimit(Math.min(limit + PAGE, 500))} disabled={limit >= 500}>
            Show more
          </Button>
        </div>
      )}
      <Drawer open={selectedId !== null} onClose={() => setSelectedId(null)} title="Run trace" wide>
        {selectedId && <RunDetail runId={selectedId} onClose={() => setSelectedId(null)} />}
      </Drawer>
    </div>
  )
}
