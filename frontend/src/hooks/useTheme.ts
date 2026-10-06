import { useSyncExternalStore } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
const STORAGE_KEY = 'cap:theme'
const listeners = new Set<() => void>()
const valid = (value: unknown): value is ThemePreference =>
  value === 'light' || value === 'dark' || value === 'system'

function readPreference(fallback: ThemePreference = 'system'): ThemePreference {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return valid(value) ? value : 'system'
  } catch { return fallback }
}

let preference = readPreference()
const systemIsDark = () => typeof window !== 'undefined'
  && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
const resolvedTheme = () => preference === 'system' ? (systemIsDark() ? 'dark' : 'light') : preference

function applyTheme() {
  if (typeof document === 'undefined') return
  const resolved = resolvedTheme()
  document.documentElement.dataset.theme = resolved
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  document.documentElement.style.colorScheme = resolved
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#14171c' : '#f5f7fa')
}

function publish() {
  applyTheme()
  listeners.forEach((listener) => listener())
}

export function setThemePreference(next: ThemePreference) {
  preference = next
  try { window.localStorage.setItem(STORAGE_KEY, next) } catch { /* Keep the in-memory choice. */ }
  publish()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY || event.key === null) {
      preference = readPreference(preference)
      publish()
    }
  }
  media?.addEventListener('change', publish)
  window.addEventListener('storage', onStorage)
  applyTheme()
  return () => {
    listeners.delete(listener)
    media?.removeEventListener('change', publish)
    window.removeEventListener('storage', onStorage)
  }
}

const snapshot = () => `${preference}:${resolvedTheme()}`

export function useTheme() {
  const value = useSyncExternalStore(subscribe, snapshot, () => 'system:light')
  const [selected, resolved] = value.split(':')
  return { preference: selected as ThemePreference, resolved: resolved as 'light' | 'dark', setPreference: setThemePreference }
}
