/** Client-side theme switching (spec §8.7): four palettes over the same
 * token names — default is the mission-control theme baked into @theme.
 *
 * Every localStorage touch is guarded the way `api/client.ts` guards the
 * auth token: a browser with site data blocked (private window, a strict
 * enterprise policy) THROWS on the accessor rather than returning null, and
 * `initTheme()` runs at module scope before `createRoot` — an unguarded
 * throw there takes the whole application down to a blank page before React
 * ever mounts. The theme simply does not persist; nothing else changes. */
export const THEMES = ['default', 'anthropic', 'openai', 'google'] as const
export type Theme = (typeof THEMES)[number]

const KEY = 'concierge-theme'

function readStored(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null // storage unavailable — fall back to the default theme
  }
}

function writeStored(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage unavailable — the theme applies for this page, it just does
       not survive a reload */
  }
}

export function applyTheme(theme: Theme) {
  if (theme === 'default') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', theme)
  writeStored(theme)
}

export function currentTheme(): Theme {
  const stored = readStored()
  return stored && (THEMES as readonly string[]).includes(stored) ? (stored as Theme) : 'default'
}

export function initTheme(): Theme {
  const theme = currentTheme()
  applyTheme(theme)
  return theme
}
