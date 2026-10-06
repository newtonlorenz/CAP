import type { ReactNode } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Outlet } from 'react-router-dom'
import App from '../App'
import { setThemePreference } from '../hooks/useTheme'

// Leave the application lifecycle in place without unrelated auth/data loading.
vi.mock('../contexts/AuthContext', () => ({ AuthProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('../contexts/JurisdictionContext', () => ({ JurisdictionProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('../components/ProtectedRoute', () => ({ default: () => <Outlet /> }))
vi.mock('../components/Layout', () => ({ default: () => <Outlet /> }))
vi.mock('../pages/Dashboard', () => ({ default: () => <p>Dashboard</p> }))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  setThemePreference('system')
})

it('applies and maintains appearance when the profile menu is closed', async () => {
  let dark = true
  const changes = new Set<() => void>()
  vi.stubGlobal('matchMedia', () => ({
    get matches() { return dark },
    addEventListener: (_: string, listener: () => void) => changes.add(listener),
    removeEventListener: (_: string, listener: () => void) => changes.delete(listener),
  }))
  setThemePreference('system')
  document.documentElement.dataset.theme = 'light'
  document.documentElement.classList.remove('dark')
  render(<MemoryRouter><App /></MemoryRouter>)
  await waitFor(() => expect(document.documentElement).toHaveAttribute('data-theme', 'dark'))
  expect(document.documentElement).toHaveClass('dark')

  act(() => { dark = false; changes.forEach(listener => listener()) })
  expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  act(() => {
    localStorage.setItem('cap:theme', 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: 'cap:theme', newValue: 'dark' }))
  })
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
})
