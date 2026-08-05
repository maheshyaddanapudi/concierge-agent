/** Settings — the command center (spec §8.7): models + params, orchestrator
 * mode, limits, MCP controls, observability, HITL queue, data ops. Every
 * control maps to app_settings or an endpoint; nothing needs a restart. */
import { useState } from 'react'
import { api } from '../api/client'
import {
  useHitlPending,
  useInvalidate,
  usePatchSettings,
  useProviders,
  useServers,
  useSettings,
} from '../api/hooks'
import type { ModelParams } from '../api/types'
import {
  Button,
  ErrorNote,
  Field,
  PageHeader,
  Select,
  StatusPill,
  TextInput,
  Toggle,
  cx,
  timeAgo,
} from '../components/ui'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/30 p-4">
      <h2 className="mb-3 text-[11px] font-bold uppercase tracking-widest text-slate-500">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function ModelSelect({
  label,
  refKey,
  paramsKey,
  allowInherit,
}: {
  label: string
  refKey: string
  paramsKey: string
  allowInherit?: boolean
}) {
  const { data: settings } = useSettings()
  const { data: providers = [] } = useProviders()
  const patch = usePatchSettings()
  if (!settings) return null
  const current = (settings[refKey] as string | null) ?? null
  const params = (settings[paramsKey] as ModelParams | null) ?? null
  const options = providers
    .filter((p) => p.configured)
    .flatMap((p) => p.models.map((m) => ({ ref: `${p.provider_id}:${m.id}`, supports: m })))
  const selected = options.find((o) => o.ref === current)
  const setParams = (patchObj: Partial<ModelParams>) => {
    const next: ModelParams = { ...(params ?? {}), ...patchObj }
    const clean: ModelParams = {}
    if (next.effort) clean.effort = next.effort
    if (next.temperature !== null && next.temperature !== undefined)
      clean.temperature = next.temperature
    if (next.max_output_tokens) clean.max_output_tokens = next.max_output_tokens
    patch.mutate({ [paramsKey]: Object.keys(clean).length ? clean : null })
  }
  return (
    <div className="grid grid-cols-4 items-end gap-2">
      <Field label={label}>
        <Select
          value={current ?? ''}
          onChange={(e) =>
            patch.mutate({
              [refKey]: e.target.value || null,
              ...(e.target.value ? {} : { [paramsKey]: null }),
            })
          }
        >
          {allowInherit && <option value="">(use default)</option>}
          {current && !options.some((o) => o.ref === current) && (
            <option value={current}>{current} (unconfigured)</option>
          )}
          {options.map((o) => (
            <option key={o.ref} value={o.ref}>
              {o.ref}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="effort">
        <Select
          disabled={!current || !selected?.supports.supports_effort}
          value={params?.effort ?? ''}
          onChange={(e) =>
            setParams({ effort: (e.target.value || undefined) as ModelParams['effort'] })
          }
        >
          <option value="">default</option>
          {['none', 'low', 'medium', 'high'].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </Select>
      </Field>
      <Field label="temp">
        <TextInput
          type="number"
          step="0.1"
          disabled={!current || !selected?.supports.supports_temperature}
          defaultValue={params?.temperature ?? ''}
          onBlur={(e) =>
            setParams({ temperature: e.target.value === '' ? undefined : Number(e.target.value) })
          }
        />
      </Field>
      <Field label="max out">
        <TextInput
          type="number"
          disabled={!current || !selected?.supports.supports_max_output_tokens}
          defaultValue={params?.max_output_tokens ?? ''}
          onBlur={(e) =>
            setParams({
              max_output_tokens: e.target.value === '' ? undefined : Number(e.target.value),
            })
          }
        />
      </Field>
    </div>
  )
}

function IntSetting({ label, k, hint }: { label: string; k: string; hint?: string }) {
  const { data: settings } = useSettings()
  const patch = usePatchSettings()
  if (!settings) return null
  return (
    <Field label={label} hint={hint}>
      <TextInput
        type="number"
        defaultValue={Number(settings[k])}
        className="max-w-28"
        onBlur={(e) => {
          const v = Number(e.target.value)
          if (v >= 1 && v !== Number(settings[k])) patch.mutate({ [k]: v })
        }}
      />
    </Field>
  )
}

function BoolSetting({ label, k, hint }: { label: string; k: string; hint?: string }) {
  const { data: settings } = useSettings()
  const patch = usePatchSettings()
  if (!settings) return null
  return (
    <Field label={label} hint={hint}>
      <Toggle checked={Boolean(settings[k])} onChange={(v) => patch.mutate({ [k]: v })} />
    </Field>
  )
}

export function SettingsPage() {
  const { data: settings } = useSettings()
  const { data: providers = [] } = useProviders()
  const { data: servers = [] } = useServers()
  const { data: pending = [] } = useHitlPending()
  const patch = usePatchSettings()
  const invalidate = useInvalidate()
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    setError(null)
    try {
      await fn()
      invalidate('mcp-servers', 'tools', 'runs', 'skills', 'sub-agents')
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  if (!settings) return <div className="p-6 text-sm text-slate-500">Loading…</div>

  return (
    <div className="space-y-4 p-6 pb-16">
      <PageHeader
        title="Settings"
        subtitle="Every runtime control, live — changes apply to the next run. API keys stay env-only, never here."
      />
      <ErrorNote error={patch.error ?? error} />

      <Section title="Models">
        <ModelSelect label="Default model" refKey="default_model" paramsKey="default_model_params" />
        <ModelSelect
          label="Planner model"
          refKey="planner_model"
          paramsKey="planner_model_params"
          allowInherit
        />
        <ModelSelect
          label="Aggregator model"
          refKey="aggregator_model"
          paramsKey="aggregator_model_params"
          allowInherit
        />
        <div className="mt-2 rounded-md border border-slate-800 p-3">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-600">
            Provider adapters (code-registered, read-only)
          </div>
          <div className="grid grid-cols-2 gap-2">
            {providers.map((p) => (
              <div
                key={p.provider_id}
                className={cx(
                  'rounded-md border px-3 py-2',
                  p.configured ? 'border-emerald-500/30' : 'border-slate-800 opacity-60',
                )}
              >
                <div className="flex items-center justify-between">
                  <code className="text-xs font-semibold text-slate-200">{p.provider_id}</code>
                  <span
                    className={cx(
                      'text-[10px] font-semibold uppercase',
                      p.configured ? 'text-emerald-400' : 'text-slate-500',
                    )}
                  >
                    {p.configured ? 'configured' : 'no api key'}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-slate-500">
                  {p.models.map((m) => m.id).join(' · ')}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Orchestrator">
        <Field label="Mode" hint="switch per run — next chat message uses the new orchestrator">
          <div className="flex gap-2">
            {(['graph', 'agentic'] as const).map((m) => (
              <Button
                key={m}
                variant={settings.orchestrator_mode === m ? 'primary' : 'secondary'}
                onClick={() => patch.mutate({ orchestrator_mode: m })}
              >
                {m === 'graph' ? '🗺 graph (explicit planner)' : '🤖 agentic (todo-driven)'}
              </Button>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <BoolSetting
            label="Full-catalog fallback"
            k="orchestrator_full_fallback_enabled"
            hint="when routing fails, the orchestrator handles it itself with ALL tools+skills"
          />
          <BoolSetting
            label="Dynamic worker fallback"
            k="dynamic_worker_fallback_enabled"
            hint="rung 4: build ephemeral workers on the fly"
          />
          <BoolSetting
            label="Declarative answer UI"
            k="answer_ui_enabled"
            hint="model-generated A2UI panel under each answer"
          />
          <IntSetting label="Max parallel dispatch" k="max_parallel_dispatch" />
          <IntSetting label="Max plan steps" k="max_plan_steps" />
          <IntSetting
            label="Max tool iterations"
            k="max_tool_iterations"
            hint="per skill-node loop; exceeding fails the node (error-edge semantics)"
          />
          <IntSetting
            label="Direct-exposure cap warning"
            k="direct_exposure_cap_warning"
            hint="Tools/Skills pages warn above this"
          />
        </div>
      </Section>

      <Section title="MCP">
        <div className="flex items-end gap-4">
          <IntSetting label="Health-check interval (s)" k="mcp_health_interval_s" />
          <Button
            disabled={busy !== null}
            onClick={() =>
              act('reconnect-all', async () => {
                for (const s of servers) await api.post(`/mcp-servers/${s.id}/reconnect`)
              })
            }
          >
            {busy === 'reconnect-all' ? 'Reconnecting…' : 'Reconnect all'}
          </Button>
          <Button
            disabled={busy !== null}
            onClick={() =>
              act('refresh-all', async () => {
                for (const s of servers.filter((x) => x.status === 'active'))
                  await api.post(`/mcp-servers/${s.id}/refresh-tools`)
              })
            }
          >
            {busy === 'refresh-all' ? 'Refreshing…' : 'Refresh all tools'}
          </Button>
        </div>
      </Section>

      <Section title="Observability">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Log level">
            <Select
              value={String(settings.log_level)}
              onChange={(e) => patch.mutate({ log_level: e.target.value })}
              className="max-w-36"
            >
              {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((l) => (
                <option key={l}>{l}</option>
              ))}
            </Select>
          </Field>
          <BoolSetting
            label="LangSmith tracing"
            k="langsmith_enabled"
            hint="per-run tracer from these settings; LANGSMITH_API_KEY stays env-only"
          />
          <Field label="LangSmith endpoint" hint="empty = SaaS; point at a local instance to self-host">
            <TextInput
              defaultValue={String(settings.langsmith_endpoint)}
              onBlur={(e) => patch.mutate({ langsmith_endpoint: e.target.value })}
            />
          </Field>
          <Field label="LangSmith project">
            <TextInput
              defaultValue={String(settings.langsmith_project)}
              onBlur={(e) => patch.mutate({ langsmith_project: e.target.value })}
            />
          </Field>
          <Field label="OTLP endpoint" hint="runtime override of the env bootstrap default">
            <TextInput
              defaultValue={String(settings.otlp_endpoint)}
              onBlur={(e) => patch.mutate({ otlp_endpoint: e.target.value })}
            />
          </Field>
        </div>
      </Section>

      <Section title="HITL queue">
        {pending.length === 0 ? (
          <p className="text-xs text-slate-500">No runs waiting for approval.</p>
        ) : (
          <div className="space-y-2">
            {pending.map((p) => (
              <div
                key={p.run_id}
                className="flex items-center gap-3 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2"
              >
                <StatusPill status="paused_hitl" />
                <span className="flex-1 truncate text-xs text-slate-300">{p.chat_message}</span>
                <span className="text-[10px] text-slate-500">{timeAgo(p.started_at)}</span>
                <Button
                  variant="primary"
                  onClick={() =>
                    act('hitl', () =>
                      api.post(`/runs/${p.run_id}/hitl`, { decision: 'approve', note: '' }),
                    )
                  }
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  onClick={() =>
                    act('hitl', () =>
                      api.post(`/runs/${p.run_id}/hitl`, { decision: 'deny', note: '' }),
                    )
                  }
                >
                  Deny
                </Button>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Data">
        <div className="flex gap-2">
          <Button
            disabled={busy !== null}
            onClick={() => act('seed', () => api.post('/seed/reload'))}
          >
            {busy === 'seed' ? 'Reloading…' : 'Reload seed (idempotent)'}
          </Button>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (window.confirm('Purge ALL run history? This cannot be undone.'))
                void act('purge', () => api.delete('/runs'))
            }}
          >
            {busy === 'purge' ? 'Purging…' : 'Purge run history'}
          </Button>
        </div>
      </Section>
    </div>
  )
}
