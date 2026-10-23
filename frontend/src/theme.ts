export type ThemePreference = 'system' | 'dark' | 'light'

const STORAGE_KEY = 'cb_theme'
const THEME_COLORS = { dark: '#000000', light: '#ffffff' }

export function getThemePreference(): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'dark' || stored === 'light' ? stored : 'system'
}

function resolvedTheme(preference: ThemePreference): 'dark' | 'light' {
  if (preference !== 'system') return preference
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

// Con «sistema» no se pone data-theme y manda prefers-color-scheme (design.md §2).
export function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement
  if (preference === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', preference)

  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', THEME_COLORS[resolvedTheme(preference)])
}

export function setThemePreference(preference: ThemePreference): void {
  if (preference === 'system') localStorage.removeItem(STORAGE_KEY)
  else localStorage.setItem(STORAGE_KEY, preference)
  applyTheme(preference)
}

export function initTheme(): void {
  applyTheme(getThemePreference())
  // Si el usuario sigue al sistema, el color de la barra del navegador acompaña al cambio.
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    applyTheme(getThemePreference())
  })
}
