export type Theme = 'dark' | 'light'

export interface Prefs {
  theme: Theme
  rails: boolean
}

const DEFAULT_PREFS: Prefs = { theme: 'dark', rails: false }
const KEY = 'tr24.prefs'

export function loadPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return DEFAULT_PREFS
  }
}

export function savePrefs(p: Prefs): void {
  localStorage.setItem(KEY, JSON.stringify(p))
}
