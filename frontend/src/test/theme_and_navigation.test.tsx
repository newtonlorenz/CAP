import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ThemeSwitcher from '../components/ThemeSwitcher'
import NavigationSearch from '../components/NavigationSearch'
import { setThemePreference } from '../hooks/useTheme'

let dark = false
const changes = new Set<() => void>()
const media = {
  get matches() { return dark },
  addEventListener: (_: string, fn: () => void) => changes.add(fn),
  removeEventListener: (_: string, fn: () => void) => changes.delete(fn),
}
const changeSystem = (next: boolean) => act(() => { dark = next; changes.forEach((fn) => fn()) })

beforeEach(() => {
  dark = false
  vi.stubGlobal('matchMedia', vi.fn(() => media))
  window.localStorage.clear()
  setThemePreference('system')
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); changes.clear() })

describe('Application appearance', () => {
  it('remembers an explicit choice across screens and sets native browser colour scheme', () => {
    const first = render(<ThemeSwitcher />)
    fireEvent.click(screen.getByRole('button', { name: 'Use dark theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
    expect(localStorage.getItem('cap:theme')).toBe('dark')
    first.unmount()
    render(<ThemeSwitcher />)
    expect(screen.getByRole('button', { name: 'Use dark theme' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Use light theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })
  it('follows system changes only while system appearance is selected', () => {
    render(<ThemeSwitcher />)
    changeSystem(true)
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    fireEvent.click(screen.getByRole('button', { name: 'Use light theme' }))
    changeSystem(false); changeSystem(true)
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    fireEvent.click(screen.getByRole('button', { name: 'Use system theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })
  it('updates when the preference changes in another tab', () => {
    render(<ThemeSwitcher />)
    localStorage.setItem('cap:theme', 'dark')
    fireEvent(window, new StorageEvent('storage', { key: 'cap:theme', newValue: 'dark' }))
    expect(screen.getByRole('button', { name: 'Use dark theme' })).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })
  it('keeps theme switching usable when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
    render(<ThemeSwitcher />)
    fireEvent.click(screen.getByRole('button', { name: 'Use dark theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(screen.getByRole('button', { name: 'Use dark theme' })).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('Page finder', () => {
  const items = [{ path: '/reviews', label: 'Assessment overview', section: 'Workspace', aliases: ['Reviews'] }, { path: '/requirements', label: 'Requirements', section: 'Work' }]
  function setup() {
    return render(<MemoryRouter><NavigationSearch items={items} /><Routes><Route path="/" element={<p>Start page</p>} /><Route path="/requirements" element={<p>Requirements destination</p>} /><Route path="/reviews" element={<p>Assessment destination</p>} /></Routes></MemoryRouter>)
  }
  it('filters pages and navigates with the keyboard', () => {
    setup()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = screen.getByRole('dialog', { name: 'Go to a page' })
    const input = within(dialog).getByRole('combobox')
    expect(input).toHaveFocus()
    fireEvent.change(input, { target: { value: 'require' } })
    expect(within(dialog).getAllByRole('option')).toHaveLength(1)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByText('Requirements destination')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('finds a renamed page through its previous name', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Find a page' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Reviews' } })
    expect(screen.getByRole('option')).toHaveTextContent('Assessment overview')
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    expect(screen.getByText('Assessment destination')).toBeInTheDocument()
  })
  it('handles no results and restores focus when dismissed', () => {
    setup()
    const trigger = screen.getByRole('button', { name: 'Find a page' })
    trigger.focus(); fireEvent.click(trigger)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'not a page' } })
    expect(screen.getByRole('status')).toHaveTextContent('No pages match')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(trigger).toHaveFocus()
  })
})
