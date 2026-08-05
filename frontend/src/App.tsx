import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NavLink, Route, HashRouter, Routes } from 'react-router-dom'
import { ChatPage } from './pages/ChatPage'
import { McpServersPage } from './pages/McpServersPage'
import { ToolsPage } from './pages/ToolsPage'
import { SkillsPage } from './pages/SkillsPage'
import { SubAgentsPage } from './pages/SubAgentsPage'
import { RunsPage } from './pages/RunsPage'
import { SettingsPage } from './pages/SettingsPage'
import { useSettings } from './api/hooks'
import { cx } from './components/ui'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const NAV = [
  { to: '/', label: 'Chat', glyph: '⌘' },
  { to: '/mcp-servers', label: 'MCP Servers', glyph: '⇌' },
  { to: '/tools', label: 'Tools', glyph: '⚒' },
  { to: '/skills', label: 'Skills', glyph: '§' },
  { to: '/sub-agents', label: 'Sub Agents', glyph: '⬡' },
  { to: '/runs', label: 'Runs', glyph: '≡' },
  { to: '/settings', label: 'Settings', glyph: '◉' },
]

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
              {NAV.map((item) => (
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
                </NavLink>
              ))}
            </nav>
            <ModeIndicator />
            <div className="border-t border-slate-800/60 px-4 py-3 font-mono text-[9px] uppercase tracking-widest text-slate-700">
              tools → skills → agents
            </div>
          </aside>
          <main className="flex-1 overflow-y-auto">
            <Routes>
              <Route path="/" element={<ChatPage />} />
              <Route path="/mcp-servers" element={<McpServersPage />} />
              <Route path="/tools" element={<ToolsPage />} />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/sub-agents" element={<SubAgentsPage />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </main>
        </div>
      </HashRouter>
    </QueryClientProvider>
  )
}
