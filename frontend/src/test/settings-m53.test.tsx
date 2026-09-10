import { render, screen, within } from '@testing-library/react'
import { vi } from 'vitest'

// M53 — the Settings page gains Retention (one gate + window per unbounded
// table, with what a purge would delete right now), Cost (today's spend, the
// shared ceiling behind its gate, price overrides) and the MCP reconnection
// controls; and every control is reachable by its accessible name.

const SETTINGS: Record<string, unknown> = {
  orchestrator_mode: 'graph',
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
  ambient_digest_times: ['09:00', '17:00'],
  ambient_quiet_hours: ['22:00', '07:00'],
  ambient_channels: {},
  memory_quarantine_kinds: [],
  retention_ambient_events_enabled: false,
  retention_ambient_events_days: 30,
  retention_deliveries_enabled: false,
  retention_deliveries_days: 90,
  retention_ambient_policies_enabled: false,
  retention_ambient_policies_days: 365,
  retention_pattern_instances_enabled: false,
  retention_pattern_instances_days: 7,
  retention_a2a_tasks_enabled: false,
  retention_a2a_tasks_days: 90,
  retention_auth_sessions_enabled: true,
  retention_auth_sessions_days: 7,
  mcp_auto_reconnect_enabled: true,
  mcp_reconnect_max_attempts: 8,
  model_prices: {},
  spend_ceiling_enabled: false,
  spend_ceiling_usd_per_day: 10,
}
const patchMutate = vi.fn()
const retentionRun = vi.fn()

vi.mock('../api/hooks', () => ({
  useSettings: () => ({ data: SETTINGS }),
  useProviders: () => ({ data: [] }),
  useServers: () => ({ data: [] }),
  useHitlPending: () => ({ data: [] }),
  useCacheStatus: () => ({ data: null }),
  useRefreshCache: () => ({ mutate: vi.fn(), isPending: false }),
  usePatchSettings: () => ({ mutate: patchMutate, error: null }),
  useInvalidate: () => vi.fn(),
  useSpend: () => ({
    data: {
      day: '2026-09-02',
      usd_today: 1.2345,
      runs_today: 3,
      unpriced_tokens: 0,
      by_kind: { chat: 1.0, ambient: 0.2345 },
      ceiling: { enabled: false, usd_per_day: 10, remaining: null, reached: false },
    },
  }),
  useRetention: () => ({
    data: {
      tables: [
        { table: 'ambient_events', enabled: false, days: 30, eligible: 12 },
        { table: 'deliveries', enabled: false, days: 90, eligible: 0 },
        { table: 'ambient_policies', enabled: false, days: 365, eligible: 0 },
        { table: 'pattern_instances', enabled: false, days: 7, eligible: 0 },
        { table: 'a2a_tasks', enabled: false, days: 90, eligible: 0 },
        { table: 'auth_sessions', enabled: true, days: 7, eligible: 2 },
      ],
    },
  }),
  useRunRetention: () => ({ mutate: retentionRun, isPending: false, data: undefined }),
}))

import { SettingsPage } from '../pages/SettingsPage'

describe('Settings — Retention (M53)', () => {
  it('renders one gate and one window per unbounded table, with the eligible count', () => {
    render(<SettingsPage />)
    const section = screen.getByRole('region', { name: /retention/i })
    for (const table of [
      'ambient_events',
      'deliveries',
      'ambient_policies',
      'pattern_instances',
      'a2a_tasks',
      'auth_sessions',
    ]) {
      expect(within(section).getByRole('switch', { name: new RegExp(table) })).toBeInTheDocument()
      expect(
        within(section).getByRole('spinbutton', { name: new RegExp(`${table}.*days`, 'i') }),
      ).toBeInTheDocument()
    }
    expect(within(section).getByText(/12 rows eligible/)).toBeInTheDocument()
    expect(within(section).getByRole('switch', { name: /auth_sessions/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('has a run-now control that calls the retention endpoint', () => {
    render(<SettingsPage />)
    const section = screen.getByRole('region', { name: /retention/i })
    within(section)
      .getByRole('button', { name: /run retention now/i })
      .click()
    expect(retentionRun).toHaveBeenCalled()
  })
})

describe('Settings — Cost (M53)', () => {
  it("shows today's spend by kind and the ceiling behind its gate", () => {
    render(<SettingsPage />)
    const section = screen.getByRole('region', { name: /cost/i })
    expect(within(section).getByText(/\$1\.2345/)).toBeInTheDocument()
    expect(within(section).getByText(/chat/)).toBeInTheDocument()
    expect(within(section).getByRole('switch', { name: /spend ceiling/i })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(
      within(section).getByRole('spinbutton', { name: /ceiling.*usd.*day/i }),
    ).toBeInTheDocument()
    expect(within(section).getByRole('textbox', { name: /price overrides/i })).toBeInTheDocument()
  })
})

describe('Settings — MCP reconnection (M53)', () => {
  it('exposes the auto-reconnect gate and the attempt budget', () => {
    render(<SettingsPage />)
    expect(screen.getByRole('switch', { name: /auto-reconnect/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('spinbutton', { name: /reconnect attempts/i })).toBeInTheDocument()
  })
})

describe('Settings — accessibility pass (M53)', () => {
  it('every switch on the page has an accessible name', () => {
    render(<SettingsPage />)
    for (const toggle of screen.getAllByRole('switch')) {
      expect(toggle).toHaveAccessibleName()
    }
  })
  it('every text and number input is labelled', () => {
    render(<SettingsPage />)
    const unnamed = [...screen.getAllByRole('textbox'), ...screen.getAllByRole('spinbutton')]
      .filter((el) => {
        const byLabel = el.id && document.querySelector(`label[for="${el.id}"]`)
        return !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') && !byLabel
      })
      .map((el) => el.outerHTML)
    expect(unnamed).toEqual([])
  })
})
