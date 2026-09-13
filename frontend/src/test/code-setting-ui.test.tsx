import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

// Code-setting UI hardening wave — the controls the spec promises and the
// page never rendered (§8: "static records: definition fields disabled, but
// status/exposure toggles remain live"), the settings an operator must be
// able to reach BEFORE the feature that uses them runs, the run statuses the
// backend writes but the client's union never named, a theme that survives a
// browser with site data blocked, a render error that does not take the whole
// application down, and a refused message that says so instead of vanishing.

// ── fixtures (mutable: each describe points them where it needs) ──

const SETTINGS: Record<string, unknown> = {
  orchestrator_mode: 'graph',
  formatter_enabled: false,
  registry_cache_mode: 'bypass',
  embedding_model: null,
  log_level: 'INFO',
  langsmith_endpoint: '',
  langsmith_project: '',
  otlp_endpoint: '',
  // ambient OFF: the anticipation toggle must still be reachable
  ambient_enabled: false,
  ambient_anticipation_enabled: true,
  a2a_enabled: false,
  evals_enabled: false,
  memory_enabled: false,
  memory_quarantine_kinds: [],
  memory_community_budget_tokens: 2000,
  model_prices: {},
  max_plan_steps: 5,
  max_parallel_dispatch: 3,
  overlap_threshold_percent: 70,
  registry_overlap_audit_enabled: false,
  formatter_coverage_flag_threshold: 60,
}

const registryBase = {
  description: '',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  deleted_at: null,
}

const SKILLS = [
  {
    ...registryBase,
    id: 's-static',
    name: 'seeded-skill',
    // a STATIC record: the definition is locked, the status is not
    source: 'static',
    status: 'active',
    kind: 'native',
    persona: 'p',
    instructions: 'i',
    direct_exposure: false,
    model: null,
    model_params: null,
    max_tool_iterations: null,
    tools: [],
  },
]

const AGENTS = [
  {
    ...registryBase,
    id: 'a-custom',
    name: 'custom-agent',
    source: 'static',
    status: 'active',
    kind: 'custom',
    persona: 'p',
    model: null,
    model_params: null,
    workflow: { nodes: [], edges: [] },
    native_ref: null,
    covers_skill_ids: null,
    direct_exposure: false,
    skills: [],
  },
  {
    ...registryBase,
    id: 'a-native',
    name: 'native-agent',
    source: 'static',
    status: 'active',
    kind: 'native',
    persona: '',
    model: null,
    model_params: null,
    workflow: null,
    native_ref: 'app.native.research',
    covers_skill_ids: [],
    direct_exposure: true,
    skills: [],
  },
]

const REMOTE_AGENTS = [
  {
    ...registryBase,
    id: 'ra1',
    name: 'remote-one',
    source: 'dynamic',
    status: 'active',
    card_url: 'https://agent.example.com',
    card: null,
    card_fetched_at: null,
    last_error: null,
    tool_count: 2,
    auth: {},
    auth_status: 'open',
  },
]

const run = (over: Record<string, unknown>) => ({
  id: 'r-queued',
  conversation_id: 'c1',
  chat_message: 'waiting for a slot',
  status: 'queued',
  orchestrator_mode: 'graph',
  plan: null,
  final_answer: null,
  answer_ui: null,
  error: null,
  started_at: '2026-09-11T00:00:00Z',
  finished_at: null,
  total_input_tokens: 0,
  total_output_tokens: 0,
  steps: [],
  ...over,
})

let CURRENT_RUN: Record<string, unknown> = run({})
let CONV_DETAIL: Record<string, unknown> | undefined
let CONVERSATIONS: Record<string, unknown>[] = []

const patchMutate = vi.fn()
const invalidate = vi.fn()

vi.mock('@xyflow/react', () => ({
  // the DAG preview needs a real layout engine; this suite is about the
  // status control beside it
  ReactFlow: () => null,
  Background: () => null,
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom' },
}))

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual, // the REAL ApiError — the composer test throws one
    api: {
      get: vi.fn(async () => []),
      post: vi.fn(async () => ({ run_id: 'r-new', conversation_id: 'c1' })),
      patch: vi.fn(async () => ({})),
      delete: vi.fn(async () => ({})),
      upload: vi.fn(async () => ({})),
    },
    streamRun: vi.fn(() => () => undefined),
  }
})

vi.mock('../api/hooks', () => ({
  useServers: () => ({ data: [] }),
  useRemoteAgents: () => ({ data: REMOTE_AGENTS, isLoading: false }),
  useTools: () => ({ data: [], isLoading: false }),
  useSkills: () => ({ data: SKILLS, isLoading: false }),
  useSubAgents: () => ({ data: AGENTS, isLoading: false }),
  useRuns: () => ({ data: [CURRENT_RUN], isLoading: false }),
  useRun: () => ({ data: CURRENT_RUN }),
  useConversations: () => ({ data: CONVERSATIONS }),
  useConversation: () => ({ data: CONV_DETAIL }),
  useSettings: () => ({ data: SETTINGS }),
  useProviders: () => ({ data: [] }),
  useHitlPending: () => ({ data: [] }),
  useCacheStatus: () => ({ data: null }),
  useRefreshCache: () => ({ mutate: vi.fn(), isPending: false }),
  usePatchSettings: () => ({ mutate: patchMutate, error: null }),
  useInvalidate: () => invalidate,
  useSpend: () => ({ data: null }),
  useRetention: () => ({ data: null }),
  useRunRetention: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useUnreadDeliveries: () => ({ data: null }),
}))

import { RouteErrorBoundary } from '../App'
import { api } from '../api/client'
import { ApiError } from '../api/client'
import { LIVE_RUN_STATUSES, isLiveRunStatus, type RunStatus } from '../api/types'
import { ChatPage } from '../pages/ChatPage'
import { RemoteAgentsPage } from '../pages/RemoteAgentsPage'
import { RunsPage } from '../pages/RunsPage'
import { SettingsPage } from '../pages/SettingsPage'
import { SkillsPage } from '../pages/SkillsPage'
import { SubAgentsPage } from '../pages/SubAgentsPage'
import { applyTheme, currentTheme, initTheme } from '../theme'

function wrap(node: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeAll(() => {
  // jsdom implements no scrolling at all; the chat transcript scrolls itself
  Element.prototype.scrollIntoView = vi.fn()
})

beforeEach(() => {
  vi.mocked(api.patch).mockClear()
  vi.mocked(api.post).mockClear()
  vi.mocked(api.post).mockImplementation(async () => ({
    run_id: 'r-new',
    conversation_id: 'c1',
  }))
  patchMutate.mockClear()
  CURRENT_RUN = run({})
  CONV_DETAIL = undefined
  CONVERSATIONS = []
})

// ── 1. status toggles, live on static records (spec §8) ──────────

describe('Status toggles exist wherever the spec says they stay live', () => {
  it('Skills: a static skill can be taken out of service from its editor', async () => {
    wrap(<SkillsPage />)
    fireEvent.click(screen.getByText('seeded-skill'))
    const toggle = await screen.findByRole('switch', { name: 'Status' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/skills/s-static', {
        status: 'inactive',
      }),
    )
  })

  it('Sub Agents: the custom editor toggles status, static record and all', async () => {
    wrap(<SubAgentsPage />)
    fireEvent.click(screen.getByText('custom-agent'))
    const toggle = await screen.findByRole('switch', { name: 'Status' })
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/sub-agents/a-custom', {
        status: 'inactive',
      }),
    )
  })

  it('Sub Agents: the native card offers the status it claims to be editable', async () => {
    wrap(<SubAgentsPage />)
    fireEvent.click(screen.getByText('native-agent'))
    // the card's own copy says "read-only except status and direct exposure"
    expect(await screen.findByText(/read-only except\s+status and direct exposure/i)).toBeVisible()
    fireEvent.click(await screen.findByRole('switch', { name: 'Status' }))
    await waitFor(() =>
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/sub-agents/a-native', {
        status: 'inactive',
      }),
    )
  })

  it('Remote Agents: the drawer sets status, it does not only report it', async () => {
    wrap(<RemoteAgentsPage />)
    fireEvent.click(screen.getByText('remote-one'))
    fireEvent.click(await screen.findByRole('switch', { name: 'Status' }))
    await waitFor(() =>
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/remote-agents/ra1', {
        status: 'inactive',
      }),
    )
  })
})

// ── 2. anticipation is settable before ambient is turned on ──────

describe('Anticipation briefings sit outside the ambient master gate', () => {
  it('renders with ambient_enabled false and patches from there', () => {
    expect(SETTINGS.ambient_enabled).toBe(false)
    render(<SettingsPage />)
    const toggle = screen.getByRole('switch', { name: 'Anticipation briefings' })
    expect(toggle).toHaveAttribute('aria-checked', 'true') // default untouched
    fireEvent.click(toggle)
    expect(patchMutate).toHaveBeenCalledWith({ ambient_anticipation_enabled: false })
  })

  it('still keeps the ambient-only controls behind the gate', () => {
    render(<SettingsPage />)
    expect(screen.queryByLabelText('Interrupt threshold')).toBeNull()
  })
})

// ── 3. the run status union the backend actually writes ──────────

describe('RunStatus covers queued and stalled', () => {
  it('names both in the union and sorts them live vs terminal', () => {
    const statuses: RunStatus[] = ['queued', 'stalled']
    expect(statuses).toHaveLength(2)
    expect(isLiveRunStatus('queued')).toBe(true)
    expect(isLiveRunStatus('running')).toBe(true)
    expect(isLiveRunStatus('paused_hitl')).toBe(true)
    // stalled is the reaper's verdict — terminal, like failed
    expect(isLiveRunStatus('stalled')).toBe(false)
    expect(isLiveRunStatus('completed')).toBe(false)
    expect([...LIVE_RUN_STATUSES]).toEqual(['queued', 'running', 'paused_hitl'])
  })

  it('Runs: a queued run offers Cancel and refuses Delete', async () => {
    CURRENT_RUN = run({ status: 'queued' })
    wrap(<RunsPage />)
    fireEvent.click(screen.getByText('waiting for a slot'))
    expect(await screen.findByText('Cancel run')).toBeInTheDocument()
    expect(screen.queryByText('Delete')).toBeNull()
  })

  it('Runs: a stalled run is terminal — Delete, no Cancel', async () => {
    CURRENT_RUN = run({ id: 'r-stalled', status: 'stalled', chat_message: 'went quiet' })
    wrap(<RunsPage />)
    fireEvent.click(screen.getByText('went quiet'))
    expect(await screen.findByText('Delete')).toBeInTheDocument()
    expect(screen.queryByText('Cancel run')).toBeNull()
  })

  it('Chat: a queued run is live — the composer queues instead of firing a second run', async () => {
    CONVERSATIONS = [
      { id: 'c1', title: 'a chat with a queued run', created_at: '', updated_at: '', run_count: 1 },
    ]
    CONV_DETAIL = {
      id: 'c1',
      title: 'a chat with a queued run',
      messages: [],
      runs: [run({ id: 'r-queued', status: 'queued' })],
    }
    wrap(<ChatPage />)
    fireEvent.click(screen.getByText('a chat with a queued run'))
    const box = await screen.findByPlaceholderText(/queue it/i)
    fireEvent.change(box, { target: { value: 'second question' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await screen.findByText(/1 message queued in this chat/i)
    expect(vi.mocked(api.post)).not.toHaveBeenCalledWith('/chat', expect.anything())
  })
})

// ── 5. theme storage survives a browser with site data blocked ───

describe('Theme storage is guarded like every other localStorage touch', () => {
  const blocked = () => {
    throw new DOMException('storage is disabled', 'SecurityError')
  }

  it('currentTheme falls back to default when the read throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)
    expect(() => currentTheme()).not.toThrow()
    expect(currentTheme()).toBe('default')
    spy.mockRestore()
  })

  it('applyTheme still paints the palette when the write throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)
    expect(() => applyTheme('openai')).not.toThrow()
    expect(document.documentElement.getAttribute('data-theme')).toBe('openai')
    applyTheme('default')
    spy.mockRestore()
  })

  it('initTheme never throws, so main.tsx reaches createRoot', () => {
    const read = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)
    expect(initTheme()).toBe('default')
    read.mockRestore()
    write.mockRestore()
  })
})

// ── 6. an error boundary around the routed content ───────────────

describe('RouteErrorBoundary keeps one bad page from taking down the app', () => {
  function Boom(): React.ReactElement {
    throw new Error('render exploded')
  }

  it('renders a recoverable message with a reload affordance', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    render(
      <RouteErrorBoundary>
        <Boom />
      </RouteErrorBoundary>,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent(/This page hit an error/)
    expect(alert).toHaveTextContent('render exploded')
    expect(screen.getByText('↻ Reload the app')).toBeInTheDocument()
    expect(screen.getByText('Try again')).toBeInTheDocument()
    quiet.mockRestore()
  })

  it('passes healthy children straight through', () => {
    render(
      <RouteErrorBoundary>
        <div>the page</div>
      </RouteErrorBoundary>,
    )
    expect(screen.getByText('the page')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

// ── 8. a refused message says so and keeps the draft ─────────────

describe('Chat composer reports a refused send', () => {
  it('renders the ApiError detail with its Retry-After and keeps the draft', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(
      new ApiError(429, 'daily spend ceiling reached', '3600'),
    )
    wrap(<ChatPage />)
    const box = await screen.findByPlaceholderText(/Ask the concierge/i)
    fireEvent.change(box, { target: { value: 'how much did we spend?' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    const note = await screen.findByTestId('send-error')
    expect(note).toHaveTextContent('daily spend ceiling reached')
    expect(note).toHaveTextContent('retry in 3600s')
    expect(note).toHaveTextContent('429')
    // the draft is the user's work — a refusal must never eat it
    expect(box).toHaveValue('how much did we spend?')
  })

  it('clears the note as soon as the draft is edited again', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new ApiError(503, 'run queue full'))
    wrap(<ChatPage />)
    const box = await screen.findByPlaceholderText(/Ask the concierge/i)
    fireEvent.change(box, { target: { value: 'hi' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await screen.findByTestId('send-error')
    fireEvent.change(box, { target: { value: 'hi again' } })
    expect(screen.queryByTestId('send-error')).toBeNull()
  })
})

// ── 9. a numeric field whose documented "off" is 0 ───────────────

describe('IntSetting reaches 0 where 0 is the documented off value', () => {
  it('accepts 0 for the community budget', () => {
    render(<SettingsPage />)
    const input = screen.getByLabelText('Community budget (tokens)')
    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.blur(input)
    expect(patchMutate).toHaveBeenCalledWith({ memory_community_budget_tokens: 0 })
  })

  it('says so when it discards a value below the minimum, instead of reverting silently', () => {
    render(<SettingsPage />)
    const input = screen.getByLabelText('Max plan steps')
    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.blur(input)
    expect(patchMutate).not.toHaveBeenCalledWith({ max_plan_steps: 0 })
    expect(screen.getByText(/below the minimum of 1 — kept 5/)).toBeInTheDocument()
    expect(input).toHaveValue(5)
  })
})
