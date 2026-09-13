import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Component, Suspense, lazy, type ErrorInfo, type ReactNode } from 'react'
import { NavLink, Route, HashRouter, Routes } from 'react-router-dom'
// Routed pages load on demand: bundled statically they were one ~1.06 MB
// chunk, so opening Chat also paid for react-flow, the A2UI renderer and the
// chart library. Only ROUTES are lazy — shared components stay static, since
// splitting them would trade one waterfall for many.
const AmbientPage = lazy(() =>
  import('./pages/AmbientPage').then((m) => ({ default: m.AmbientPage })),
)
const ChatPage = lazy(() => import('./pages/ChatPage').then((m) => ({ default: m.ChatPage })))
const EvalsPage = lazy(() => import('./pages/EvalsPage').then((m) => ({ default: m.EvalsPage })))
const McpServersPage = lazy(() =>
  import('./pages/McpServersPage').then((m) => ({ default: m.McpServersPage })),
)
const RemoteAgentsPage = lazy(() =>
  import('./pages/RemoteAgentsPage').then((m) => ({ default: m.RemoteAgentsPage })),
)
const ToolsPage = lazy(() => import('./pages/ToolsPage').then((m) => ({ default: m.ToolsPage })))
const SkillsPage = lazy(() => import('./pages/SkillsPage').then((m) => ({ default: m.SkillsPage })))
const SubAgentsPage = lazy(() =>
  import('./pages/SubAgentsPage').then((m) => ({ default: m.SubAgentsPage })),
)
const MemoryPage = lazy(() => import('./pages/MemoryPage').then((m) => ({ default: m.MemoryPage })))
const RunsPage = lazy(() => import('./pages/RunsPage').then((m) => ({ default: m.RunsPage })))
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
import { useSettings, useUnreadDeliveries } from './api/hooks'
import { AmbientToaster } from './components/AmbientToaster'
import { LoginGate } from './components/LoginGate'
import { Button, cx } from './components/ui'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const NAV: {
  to: string
  label: string
  glyph: string
  ambientOnly?: boolean
  a2aOnly?: boolean
}[] = [
  { to: '/', label: 'Chat', glyph: '⌘' },
  { to: '/mcp-servers', label: 'MCP Servers', glyph: '⇌' },
  // Remote Agents (spec §8.10) appears only while a2a_enabled — see NavItems
  { to: '/remote-agents', label: 'Remote Agents', glyph: '⇄', a2aOnly: true },
  { to: '/tools', label: 'Tools', glyph: '⚒' },
  { to: '/skills', label: 'Skills', glyph: '§' },
  { to: '/sub-agents', label: 'Sub Agents', glyph: '⬡' },
  { to: '/runs', label: 'Runs', glyph: '≡' },
  { to: '/evals', label: 'Evals', glyph: '✓' },
  { to: '/memory', label: 'Memory', glyph: '◈' },
  // Ambient (spec §8.9) appears only while ambient_enabled — see NavItems
  { to: '/ambient', label: 'Ambient', glyph: '◎', ambientOnly: true },
  { to: '/settings', label: 'Settings', glyph: '◉' },
]

function NavItems() {
  const { data: settings } = useSettings()
  const ambientOn = Boolean(settings?.ambient_enabled)
  const a2aOn = Boolean(settings?.a2a_enabled)
  // M42 §18.4: unread = delivered but never opened. Attention-tier items
  // (0/1) tint the badge — those are the ones that were meant to be seen live
  const { data: unread } = useUnreadDeliveries(ambientOn)
  return (
    <>
      {NAV.filter((item) => (!item.ambientOnly || ambientOn) && (!item.a2aOnly || a2aOn)).map(
        (item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cx(
                'group flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-[13px] font-medium transition-all',
                isActive
                  ? 'border-accent-400 bg-accent-500/10 text-accent-300'
                  : 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-200',
              )
            }
          >
            <span className="w-4 text-center font-mono text-xs opacity-70">{item.glyph}</span>
            {item.label}
            {item.ambientOnly && unread && unread.count > 0 && (
              <span
                data-testid="unread-badge"
                title={`${unread.count} delivered, never opened${unread.attention ? ` · ${unread.attention} were meant to be seen live` : ''}`}
                className={cx(
                  'ml-auto rounded-full px-1.5 py-0.5 font-mono text-[9px] font-bold',
                  unread.attention > 0
                    ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40'
                    : 'bg-slate-700/60 text-slate-300',
                )}
              >
                {unread.count}
              </span>
            )}
          </NavLink>
        ),
      )}
    </>
  )
}

/** The page-loading treatment, shared by the lazy-route Suspense fallback
 * and the Settings page's own loading state. */
function PageLoading() {
  return <div className="p-6 text-sm text-slate-500">Loading…</div>
}

/** A render error in one page must not take down the application. React has
 * no hook form of this — an error boundary is a class or it is nothing. The
 * navigation stays mounted outside it, so the operator can walk to another
 * page instead of staring at a white screen. */
export class RouteErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // the console is the only sink the browser build has; the server never
    // hears about a render error
    console.error('page crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="p-6" role="alert">
        <div className="max-w-xl rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
          <h1 className="font-display text-sm font-semibold text-rose-300">
            This page hit an error
          </h1>
          <p className="mt-1 text-xs leading-relaxed text-rose-200/80">
            The rest of the application is still running — pick another page from the nav, or try
            this one again. Nothing was lost on the server; runs and registry records are
            unaffected.
          </p>
          <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-rose-500/20 bg-void-950/60 p-2 font-mono text-[11px] text-rose-200/70">
            {this.state.error.message}
          </pre>
          <div className="mt-3 flex gap-2">
            <Button variant="secondary" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button variant="ghost" onClick={() => window.location.reload()}>
              ↻ Reload the app
            </Button>
          </div>
        </div>
      </div>
    )
  }
}

function ModeIndicator() {
  const { data: settings } = useSettings()
  if (!settings) return null
  return (
    <div className="mx-2 mb-2 rounded-md border border-slate-800 bg-void-900/80 px-3 py-2">
      <div className="text-[9px] uppercase tracking-[0.2em] text-slate-600">orchestrator</div>
      <div className="font-display mt-0.5 flex items-center gap-1.5 text-xs font-semibold text-accent-300">
        <span className="size-1.5 animate-pulse rounded-full bg-accent-400" />
        {settings.orchestrator_mode} mode
      </div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <div className="flex h-screen overflow-hidden">
          <aside className="flex w-56 shrink-0 flex-col border-r border-slate-800/80 bg-void-950/70 backdrop-blur">
            <div className="px-4 pb-3 pt-5">
              <div className="font-display text-[15px] font-bold uppercase tracking-[0.08em] text-slate-100">
                Concierge<span className="text-accent-400">▮</span>
              </div>
              <div className="mt-0.5 text-[9px] uppercase tracking-[0.3em] text-slate-600">
                agent command center
              </div>
            </div>
            <nav className="mt-2 flex-1 space-y-0.5 px-2">
              <NavItems />
            </nav>
            <ModeIndicator />
            <div className="border-t border-slate-800/60 px-4 py-3 font-mono text-[9px] uppercase tracking-widest text-slate-700">
              tools → skills → agents
            </div>
          </aside>
          <main className="flex-1 overflow-y-auto">
            <RouteErrorBoundary>
              <Suspense fallback={<PageLoading />}>
                <Routes>
                  <Route path="/" element={<ChatPage />} />
                  <Route path="/mcp-servers" element={<McpServersPage />} />
                  <Route path="/remote-agents" element={<RemoteAgentsPage />} />
                  <Route path="/tools" element={<ToolsPage />} />
                  <Route path="/skills" element={<SkillsPage />} />
                  <Route path="/sub-agents" element={<SubAgentsPage />} />
                  <Route path="/runs" element={<RunsPage />} />
                  <Route path="/evals" element={<EvalsPage />} />
                  <Route path="/memory" element={<MemoryPage />} />
                  <Route path="/ambient" element={<AmbientPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Routes>
              </Suspense>
            </RouteErrorBoundary>
          </main>
          <AmbientToaster />
          <LoginGate />
        </div>
      </HashRouter>
    </QueryClientProvider>
  )
}
