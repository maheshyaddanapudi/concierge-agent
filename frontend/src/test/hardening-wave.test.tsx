import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

// Hardening wave — the run trace reads against the registry AS IT WAS: each
// step carries the entity name it ran against, the formatter is a step of
// its own, and a "Snapshot vs registry" panel says which pinned record has
// moved since (schema version for tools, definition version for skills and
// sub agents). The Skills list flags a bound tool the loop cannot call, and
// Settings gains the registry overlap audit gate, the eval judge's own model
// role, and a hint under the salience judge when it inherits the default.

const RUN = {
  id: 'r1',
  conversation_id: 'c1',
  chat_message: 'echo hi',
  status: 'completed',
  orchestrator_mode: 'graph',
  plan: null,
  snapshot: {
    build: 'abc123',
    settings: { default_model: 'fake:fake' },
    prompts: { planner: 'deadbeef0000' },
    context: [
      { surface: 'planner', exemplar_ids: [] },
      { surface: 'memory:planner', memory_ids: [] },
    ],
    catalog_calls: [],
    catalog: {
      tools: [
        { id: 't-same', tool_key: 'stub.echo', schema_version: 2, schema_hash: 'h2' },
        { id: 't-moved', tool_key: 'stub.add', schema_version: 1, schema_hash: 'h1' },
        { id: 't-gone', tool_key: 'stub.gone', schema_version: 1, schema_hash: 'hx' },
      ],
      skills: [{ id: 's1', name: 'echo-skill', definition_version: 1, definition_hash: 'd1' }],
      sub_agents: [],
    },
    entry1: {
      rung: 'custom_sub_agent',
      payload: {
        snapshot: {
          sub_agent: { id: 'a1', name: 'old-name', definition_version: 3, definition_hash: 'a3' },
          skills: {},
        },
      },
    },
  },
  final_answer: 'hi',
  answer_ui: null,
  error: null,
  started_at: '2026-09-11T00:00:00Z',
  finished_at: '2026-09-11T00:00:05Z',
  total_input_tokens: 10,
  total_output_tokens: 5,
  cost_usd: 0.01,
  cost_priced: true,
  price_snapshot: {
    prices: { 'fake:fake': { input_per_m: 1, output_per_m: 2, source: 'builtin' } },
    unpriced_tokens: 0,
  },
  steps: [
    {
      id: 'st1',
      parent_step_id: null,
      sub_agent_id: 'a1',
      node_id: null,
      step_type: 'route',
      input: null,
      output: {
        rung: 'custom_sub_agent',
        resolved_to: { entity_id: 'a1', entity_name: 'old-name' },
      },
      model: null,
      entity_name: 'old-name',
      entity_version: 3,
      entity_hash: 'a3',
      input_tokens: 0,
      output_tokens: 0,
      status: 'completed',
      started_at: '2026-09-11T00:00:00Z',
      finished_at: '2026-09-11T00:00:01Z',
      error: null,
    },
    {
      id: 'st1b',
      parent_step_id: 'st1',
      sub_agent_id: 'a1',
      node_id: 'work',
      step_type: 'skill',
      input: null,
      output: null,
      model: 'fake:fake',
      entity_name: 'echo-skill',
      entity_version: 1,
      entity_hash: 'd1',
      input_tokens: 1,
      output_tokens: 1,
      status: 'completed',
      started_at: '2026-09-11T00:00:01Z',
      finished_at: '2026-09-11T00:00:02Z',
      error: null,
    },
    {
      id: 'st2',
      parent_step_id: null,
      sub_agent_id: null,
      node_id: null,
      step_type: 'format',
      input: { presentation: 'a2ui_first' },
      output: { attempts: 1 },
      model: 'fake:fake',
      model_params: { temperature: 0 },
      input_tokens: 5,
      output_tokens: 3,
      status: 'completed',
      started_at: '2026-09-11T00:00:03Z',
      finished_at: '2026-09-11T00:00:04Z',
      error: null,
    },
  ],
}

const tool = (over: Record<string, unknown>) => ({
  id: 't',
  name: 'x',
  description: '',
  source: 'dynamic',
  status: 'active',
  kind: 'mcp',
  mcp_server_id: 's1',
  remote_agent_id: null,
  tool_name: 'x',
  native_ref: null,
  tool_key: 'stub.x',
  direct_exposure: false,
  input_schema: {},
  ingest_state: 'present',
  schema_hash: 'h',
  schema_version: 1,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  deleted_at: null,
  ...over,
})

const TOOLS = [
  tool({ id: 't-same', tool_key: 'stub.echo', schema_version: 2, schema_hash: 'h2' }),
  tool({ id: 't-moved', tool_key: 'stub.add', schema_version: 2, schema_hash: 'h1b' }),
  tool({
    id: 't-quarantined',
    tool_key: 'stub.q',
    status: 'inactive',
    ingest_state: 'changed',
    schema_version: 3,
  }),
]

const SKILLS = [
  {
    id: 's1',
    name: 'echo-skill',
    description: 'echoes',
    source: 'dynamic',
    status: 'active',
    kind: 'custom',
    persona: 'p',
    instructions: 'i',
    direct_exposure: false,
    model: null,
    model_params: null,
    max_tool_iterations: null,
    definition_version: 2,
    definition_hash: 'd2',
    tools: [TOOLS[0], TOOLS[2]],
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    deleted_at: null,
  },
  {
    id: 's2',
    name: 'clean-skill',
    description: 'fine',
    source: 'dynamic',
    status: 'active',
    kind: 'custom',
    persona: 'p',
    instructions: 'i',
    direct_exposure: false,
    model: null,
    model_params: null,
    max_tool_iterations: null,
    definition_version: 1,
    definition_hash: 'd1',
    tools: [TOOLS[0]],
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    deleted_at: null,
  },
]

const AGENTS = [
  {
    id: 'a1',
    name: 'new-name',
    description: '',
    source: 'dynamic',
    status: 'active',
    kind: 'custom',
    persona: '',
    model: null,
    model_params: null,
    workflow: null,
    native_ref: null,
    covers_skill_ids: null,
    direct_exposure: false,
    definition_version: 4,
    definition_hash: 'a4',
    skills: [],
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    deleted_at: null,
  },
]

const SETTINGS: Record<string, unknown> = {
  orchestrator_mode: 'graph',
  formatter_enabled: false,
  registry_cache_mode: 'bypass',
  embedding_model: null,
  log_level: 'INFO',
  langsmith_endpoint: '',
  langsmith_project: '',
  otlp_endpoint: '',
  ambient_enabled: true,
  ambient_salience_model: null,
  ambient_salience_learning: 'off',
  ambient_pursuit: 'off',
  ambient_digest_times: [],
  ambient_quiet_hours: [],
  ambient_channels: {},
  a2a_enabled: false,
  memory_enabled: false,
  memory_quarantine_kinds: [],
  model_prices: {},
  evals_enabled: true,
  eval_judge_model: null,
  eval_judge_model_params: null,
  registry_overlap_audit_enabled: false,
  overlap_threshold_percent: 70,
}
const patchMutate = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    get: vi.fn(async () => []),
    post: vi.fn(async () => ({})),
    patch: vi.fn(async () => ({})),
    delete: vi.fn(async () => ({})),
  },
}))

vi.mock('../api/hooks', () => ({
  useRuns: () => ({ data: [RUN], isLoading: false }),
  useRun: () => ({ data: RUN }),
  useTools: () => ({ data: TOOLS, isLoading: false }),
  useSkills: () => ({ data: SKILLS, isLoading: false }),
  useSubAgents: () => ({ data: AGENTS }),
  useServers: () => ({ data: [] }),
  useSettings: () => ({ data: SETTINGS }),
  useProviders: () => ({ data: [] }),
  useHitlPending: () => ({ data: [] }),
  useCacheStatus: () => ({ data: null }),
  useRefreshCache: () => ({ mutate: vi.fn(), isPending: false }),
  usePatchSettings: () => ({ mutate: patchMutate, error: null }),
  useInvalidate: () => vi.fn(),
  useSpend: () => ({ data: null }),
  useRetention: () => ({ data: null }),
  useRunRetention: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
}))

import { RunsPage, compareEntity, pinnedAgentNames, pinnedEntities } from '../pages/RunsPage'
import { SettingsPage } from '../pages/SettingsPage'
import { SkillsPage, unavailableBoundTools } from '../pages/SkillsPage'

function wrap(node: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Runs — the trace reads against the registry as it was', () => {
  it('collects every pinned record from catalog and per-entry snapshots, once', () => {
    const pinned = pinnedEntities(RUN.snapshot)
    expect(pinned.map((p) => `${p.kind}:${p.name}`).sort()).toEqual([
      'skill:echo-skill',
      'sub_agent:old-name',
      'tool:stub.add',
      'tool:stub.echo',
      'tool:stub.gone',
    ])
    expect(pinned.find((p) => p.id === 'a1')?.pinnedVersion).toBe(3)
  })

  it('compares a pinned record against the live one: same, changed, deleted, inactive', () => {
    const p = { kind: 'tool' as const, id: 't', name: 'x', pinnedVersion: 1, pinnedHash: 'h1' }
    const live = (
      over: Partial<{ version: number; hash: string; status: string; name: string }>,
    ) => ({
      id: 't',
      version: 1,
      hash: 'h1',
      name: 'x',
      status: 'active',
      ...over,
    })
    expect(compareEntity(p, live({})).state).toBe('same')
    expect(compareEntity(p, live({ version: 2, hash: 'h2' })).state).toBe('changed')
    expect(compareEntity(p, live({ version: 2, hash: 'h2', name: 'y' })).detail).toMatch(
      /renamed to y/,
    )
    expect(compareEntity(p, undefined).state).toBe('deleted')
    expect(compareEntity(p, live({ status: 'inactive' })).state).toBe('inactive')
    expect(compareEntity({ ...p, pinnedVersion: null, pinnedHash: null }, live({})).state).toBe(
      'unknown',
    )
  })

  it('shows the pinned entity name on steps, the format step, and the moved count', () => {
    wrap(<RunsPage />)
    fireEvent.click(screen.getByText('echo hi'))
    // the sub agent was renamed since: the step and the chip say old-name
    expect(screen.getAllByText('old-name').length).toBeGreaterThan(0)
    expect(screen.queryByText('ephemeral')).not.toBeInTheDocument()
    // the worker node step names the skill, not a second "sub agent"
    expect(pinnedAgentNames(RUN.steps as never)).toEqual(new Map([['a1', 'old-name']]))
    const chips = screen.getByText('Sub agents involved').parentElement as HTMLElement
    expect(within(chips).queryByText('echo-skill')).toBeNull()
    expect(screen.getByText('format')).toBeInTheDocument()
    expect(screen.getByText('def v3 · a3')).toBeInTheDocument()
    const panel = screen.getByTestId('snapshot-panel')
    expect(within(panel).getByRole('status')).toHaveTextContent(
      '4 of 5 pinned records moved since this run. Build abc123.',
    )
    const rows = within(panel).getAllByRole('row')
    const text = rows.map((r) => r.textContent ?? '')
    expect(text.find((t) => t.includes('stub.echo'))).toMatch(/same/)
    expect(text.find((t) => t.includes('stub.add'))).toMatch(/changed.*v1 then · v2 now/)
    expect(text.find((t) => t.includes('stub.gone'))).toMatch(/deleted/)
    expect(text.find((t) => t.includes('old-name'))).toMatch(/changed.*renamed to new-name/)
    expect(text.find((t) => t.includes('echo-skill'))).toMatch(/changed/)
    // the prices the run was costed with, stamped at finish
    expect(screen.getByText(/\$1 in \/ \$2 out per M tokens/)).toBeInTheDocument()
    fireEvent.click(within(panel).getByText(/show settings as the run saw them/))
    expect(within(panel).getByText(/"default_model": "fake:fake"/)).toBeInTheDocument()
  })
})

describe('Skills — a bound tool the loop cannot call is flagged on the list', () => {
  it('classifies deleted, quarantined, missing and inactive tools', () => {
    const rows = unavailableBoundTools([
      TOOLS[0],
      TOOLS[2],
      tool({ id: 'd', tool_key: 'stub.d', deleted_at: '2026-09-02T00:00:00Z' }),
      tool({ id: 'm', tool_key: 'stub.m', ingest_state: 'missing' }),
      tool({ id: 'i', tool_key: 'stub.i', status: 'inactive' }),
      // third reading: an A2A tool taken out with its disabled remote agent
      tool({ id: 'a', tool_key: 'agent.a', status: 'inactive', ingest_state: 'agentoff' }),
    ] as never)
    expect(rows.map((r) => `${r.tool.tool_key}:${r.reason}`)).toEqual([
      'stub.q:quarantined',
      'stub.d:deleted',
      'stub.m:missing from server',
      'stub.i:inactive',
      'agent.a:remote agent disabled',
    ])
  })

  it('badges only the skill whose bound tool is quarantined', () => {
    wrap(<SkillsPage />)
    const badges = screen.getAllByRole('status')
    expect(badges.map((b) => b.textContent)).toContain('stub.q unavailable · quarantined')
    const clean = screen.getByText('clean-skill').closest('tr')
    expect(clean && within(clean).queryByRole('status')).toBeNull()
  })
})

describe('Settings — the judges get their own roles', () => {
  it('has the registry overlap audit gate and patches it', () => {
    render(<SettingsPage />)
    const toggle = screen.getByRole('switch', { name: 'Registry overlap audit' })
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)
    expect(patchMutate).toHaveBeenCalledWith({ registry_overlap_audit_enabled: true })
  })

  it('offers the eval judge its own model role, inheriting by default', () => {
    render(<SettingsPage />)
    const select = screen.getByRole('combobox', { name: 'Eval judge model' })
    expect(select).toHaveValue('')
    expect(screen.getByText(/the model under test grading itself/)).toBeInTheDocument()
  })

  it('warns when the salience judge inherits the answering model', () => {
    render(<SettingsPage />)
    expect(
      screen.getByText(/Inheriting the default: the model that writes the answers/),
    ).toBeInTheDocument()
  })
})

describe('Skills — a save with the overlap judge down is reported, not silent', () => {
  it('saves and shows the unjudged notice when judge_available is false', async () => {
    const { api } = await import('../api/client')
    vi.mocked(api.post).mockImplementation(async (path: string) =>
      path.endsWith('/check-overlap')
        ? {
            overlap: false,
            threshold: 70,
            overlap_percent: 0,
            match_type: 'none',
            match_id: null,
            match_name: null,
            reasoning: 'judge unavailable: provider exploded',
            judge_available: false,
          }
        : {},
    )
    wrap(<SkillsPage />)
    fireEvent.click(screen.getByText('clean-skill'))
    fireEvent.click(await screen.findByRole('button', { name: 'Save skill' }))
    const notice = await screen.findByRole('status', { name: '' })
    expect(notice.textContent).toContain('Saved unjudged')
    expect(notice.textContent).toContain('provider exploded')
    expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/skills/s2', expect.anything())
    fireEvent.click(within(notice).getByText('dismiss'))
    expect(screen.queryByText(/Saved unjudged/)).toBeNull()
  })

  it('stays silent when the judge ran and found nothing', async () => {
    const { api } = await import('../api/client')
    vi.mocked(api.post).mockImplementation(async () => ({
      overlap: false,
      threshold: 70,
      overlap_percent: 0,
      match_type: 'none',
      match_id: null,
      match_name: null,
      reasoning: 'distinct',
      judge_available: true,
    }))
    wrap(<SkillsPage />)
    fireEvent.click(screen.getByText('clean-skill'))
    fireEvent.click(await screen.findByRole('button', { name: 'Save skill' }))
    await vi.waitFor(() => expect(vi.mocked(api.patch)).toHaveBeenCalled())
    expect(screen.queryByText(/Saved unjudged/)).toBeNull()
  })
})
