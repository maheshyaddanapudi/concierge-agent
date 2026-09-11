import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

// Tool schema drift (spec §3.2): a tool whose input schema changed under a
// re-ingest is loud on the Tools page — a badge in the table, a banner with
// the new version in the drawer, and one acknowledge action (which also
// re-enables a quarantined tool). Settings gains the change policy and the
// overlap judge's own model role.

const tools = [
  {
    id: 't-changed',
    name: 'echo',
    description: 'echo text back',
    source: 'dynamic',
    status: 'active',
    kind: 'mcp',
    mcp_server_id: 's1',
    remote_agent_id: null,
    tool_name: 'echo',
    native_ref: null,
    tool_key: 'stub.echo',
    direct_exposure: false,
    input_schema: { type: 'object', properties: { message: { type: 'string' } } },
    ingest_state: 'present',
    schema_hash: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
    schema_version: 2,
    schema_changed_at: '2026-09-11T00:00:00Z',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-11T00:00:00Z',
    deleted_at: null,
  },
  {
    id: 't-quarantined',
    name: 'add',
    description: 'add numbers',
    source: 'dynamic',
    status: 'inactive',
    kind: 'mcp',
    mcp_server_id: 's1',
    remote_agent_id: null,
    tool_name: 'add',
    native_ref: null,
    tool_key: 'stub.add',
    direct_exposure: false,
    input_schema: { type: 'object', properties: {} },
    ingest_state: 'changed',
    schema_hash: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    schema_version: 3,
    schema_changed_at: '2026-09-11T00:00:00Z',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-11T00:00:00Z',
    deleted_at: null,
  },
  {
    id: 't-quiet',
    name: 'render_chart',
    description: 'chart',
    source: 'static',
    status: 'active',
    kind: 'native',
    mcp_server_id: null,
    remote_agent_id: null,
    tool_name: 'render_chart',
    native_ref: 'app.native.chart',
    tool_key: 'render_chart',
    direct_exposure: true,
    input_schema: { type: 'object', properties: {} },
    ingest_state: null,
    schema_hash: 'ffff',
    schema_version: 1,
    schema_changed_at: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    deleted_at: null,
  },
]

const post = vi.fn(async () => ({}))
const patchMutate = vi.fn()

vi.mock('../api/client', () => ({
  api: {
    get: vi.fn(async () => []),
    post: (...args: unknown[]) => post(...(args as [])),
    patch: vi.fn(async () => ({})),
    delete: vi.fn(async () => ({})),
  },
}))

vi.mock('../api/hooks', () => ({
  useTools: () => ({ data: tools, isLoading: false }),
  useServers: () => ({ data: [{ id: 's1', name: 'stub', status: 'active' }] }),
  useSkills: () => ({ data: [] }),
  useSettings: () => ({
    data: {
      direct_exposure_cap_warning: 10,
      formatter_enabled: false,
      registry_cache_mode: 'bypass',
      embedding_model: null,
      log_level: 'INFO',
      langsmith_endpoint: '',
      langsmith_project: '',
      otlp_endpoint: '',
      ambient_enabled: false,
      a2a_enabled: false,
      memory_enabled: false,
      ambient_digest_times: [],
      ambient_quiet_hours: [],
      ambient_channels: {},
      memory_quarantine_kinds: [],
      model_prices: {},
      mcp_schema_change_policy: 'warn',
      overlap_judge_model: null,
      overlap_judge_model_params: null,
    },
  }),
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

import { SettingsPage } from '../pages/SettingsPage'
import { ToolsPage } from '../pages/ToolsPage'

function renderTools() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ToolsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Tools — schema drift (spec §3.2)', () => {
  it('badges a changed tool with its new version in the table, and only that tool', () => {
    renderTools()
    expect(screen.getByText('schema changed · v2')).toBeInTheDocument()
    expect(screen.getByText('schema changed · v3')).toBeInTheDocument()
    expect(screen.queryByText(/schema changed · v1/)).not.toBeInTheDocument()
  })

  it('opens the drawer with the banner and acknowledges through the API', async () => {
    renderTools()
    fireEvent.click(screen.getByText('stub.echo'))
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent(/Input schema changed — now v2/)
    expect(screen.getByText(/^v2/)).toBeInTheDocument()
    fireEvent.click(within(banner).getByRole('button', { name: 'Acknowledge' }))
    expect(post).toHaveBeenCalledWith('/tools/t-changed/acknowledge-schema')
  })

  it('offers re-enable for a quarantined tool', async () => {
    renderTools()
    fireEvent.click(screen.getByText('stub.add'))
    const banner = await screen.findByRole('status')
    expect(banner).toHaveTextContent(/Quarantined: out of service until acknowledged/)
    expect(
      within(banner).getByRole('button', { name: 'Acknowledge & re-enable' }),
    ).toBeInTheDocument()
  })
})

describe('Settings — schema change policy and the overlap judge model', () => {
  it('has the policy toggle and patches the setting', () => {
    render(<SettingsPage />)
    const group = screen.getByRole('group', { name: /schema change policy/i })
    expect(within(group).getByRole('button', { name: 'warn' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    fireEvent.click(within(group).getByRole('button', { name: 'quarantine' }))
    expect(patchMutate).toHaveBeenCalledWith({ mcp_schema_change_policy: 'quarantine' })
  })

  it('offers the overlap judge its own model role, inheriting the default', () => {
    render(<SettingsPage />)
    const select = screen.getByRole('combobox', { name: 'Overlap judge model' })
    expect(select).toHaveValue('')
    expect(within(select).getByText('(use default)')).toBeInTheDocument()
  })
})
