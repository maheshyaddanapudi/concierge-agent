import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  CacheStatus,
  Conversation,
  ConversationDetail,
  HitlPending,
  McpServer,
  ProviderInfo,
  RemoteAgent,
  RetentionRow,
  Run,
  Settings,
  Skill,
  SpendReport,
  SubAgent,
  Tool,
} from './types'

export function useServers(params = '') {
  return useQuery({
    queryKey: ['mcp-servers', params],
    queryFn: () => api.get<McpServer[]>(`/mcp-servers${params}`),
    refetchInterval: 5000,
  })
}

export function useRemoteAgents(params = '') {
  return useQuery({
    queryKey: ['remote-agents', params],
    queryFn: () => api.get<RemoteAgent[]>(`/remote-agents${params}`),
    refetchInterval: 5000,
  })
}

export function useTools(params = '') {
  return useQuery({
    queryKey: ['tools', params],
    queryFn: () => api.get<Tool[]>(`/tools${params}`),
    refetchInterval: 5000,
  })
}

export function useSkills(params = '') {
  return useQuery({
    queryKey: ['skills', params],
    queryFn: () => api.get<Skill[]>(`/skills${params}`),
  })
}

export function useSubAgents(params = '') {
  return useQuery({
    queryKey: ['sub-agents', params],
    queryFn: () => api.get<SubAgent[]>(`/sub-agents${params}`),
  })
}

const LIVE_STATUSES = new Set(['running', 'paused_hitl'])

/** M50: polling backs off — 3 s while something is live, 15 s when the
 * page is quiet. Background tabs never poll (TanStack default). */
function runsBackoff(runs: Run[] | undefined): number {
  return runs?.some((r) => LIVE_STATUSES.has(r.status)) ? 3000 : 15000
}

export function useRuns(limit = 100) {
  return useQuery({
    queryKey: ['runs', 'page', limit],
    queryFn: () => api.get<Run[]>(`/runs?limit=${limit}`),
    refetchInterval: (query) => runsBackoff(query.state.data),
  })
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => api.get<Run>(`/runs/${runId}`),
    enabled: runId !== null,
    // a terminal run never changes again — stop polling it
    refetchInterval: (query) =>
      query.state.data && !LIVE_STATUSES.has(query.state.data.status) ? false : 2000,
  })
}

export function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => api.get<Conversation[]>('/conversations'),
  })
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: () => api.get<ConversationDetail>(`/conversations/${id}`),
    enabled: id !== null,
  })
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => api.get<Settings>('/settings') })
}

export function useProviders() {
  return useQuery({ queryKey: ['providers'], queryFn: () => api.get<ProviderInfo[]>('/providers') })
}

export function useHitlPending() {
  return useQuery({
    queryKey: ['hitl-pending'],
    queryFn: () => api.get<HitlPending[]>('/hitl/pending'),
    refetchInterval: 3000,
  })
}

/** M42: delivered-but-never-opened count for the Ambient nav badge. */
export function useUnreadDeliveries(enabled: boolean) {
  return useQuery({
    queryKey: ['deliveries', 'unread-count'],
    queryFn: () => api.get<{ count: number; attention: number }>('/deliveries/unread-count'),
    refetchInterval: 5000,
    enabled,
  })
}

export function useInvalidate() {
  const qc = useQueryClient()
  return (...keys: string[]) => {
    for (const key of keys) void qc.invalidateQueries({ queryKey: [key] })
  }
}

export function useCacheStatus() {
  return useQuery({
    queryKey: ['cache-status'],
    queryFn: () => api.get<CacheStatus>('/cache/status'),
    refetchInterval: 10000,
  })
}

export function useRefreshCache() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (registry: string) =>
      api.post<Record<string, unknown>>(`/cache/refresh/${registry}`, {}),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['cache-status'] }),
  })
}

/** M53: today's priced spend across every run kind + the ceiling state. */
export function useSpend() {
  return useQuery({
    queryKey: ['spend'],
    queryFn: () => api.get<SpendReport>('/spend'),
    refetchInterval: 15000,
  })
}

/** M53: per-table retention gate, window and what a purge would delete now. */
export function useRetention() {
  return useQuery({
    queryKey: ['retention'],
    queryFn: () => api.get<{ tables: RetentionRow[] }>('/retention'),
    refetchInterval: 30000,
  })
}

export function useRunRetention() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ deleted: Record<string, number>; skipped?: string }>('/retention/run'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['retention'] }),
  })
}

export function usePatchSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: Record<string, unknown>) => api.patch<Settings>('/settings', updates),
    onSuccess: (data) => {
      qc.setQueryData(['settings'], data)
      // registry_cache_mode lives in settings — reflect flips immediately
      void qc.invalidateQueries({ queryKey: ['cache-status'] })
      // M53: retention windows and the spend ceiling are settings too
      void qc.invalidateQueries({ queryKey: ['retention'] })
      void qc.invalidateQueries({ queryKey: ['spend'] })
    },
  })
}
