import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Layout from '../components/Layout'

// The independently tested feedback integration is not part of navigation behaviour.
vi.mock('../components/ProductFeedback', () => ({ default: () => null }))

let currentRole: 'admin' | 'approver' | 'contributor' = 'admin'
let noJurisdictions = false

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'user@example.com',
      full_name: 'Test User',
      role: currentRole,
      active: true,
      created_at: new Date().toISOString(),
    },
    logout: vi.fn(),
  }),
}))

vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'jur-1',
    jurisdictions: noJurisdictions ? [] : [
      {
        id: 'jur-1',
        code: 'global',
        name: 'Global',
      },
    ],
    jurisdictionById: {
      'jur-1': {
        id: 'jur-1',
        code: 'global',
        name: 'Global',
      },
    },
    isLoading: false,
    setJurisdictionId: vi.fn(),
  }),
}))

function renderLayout(path = '/') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>Dashboard Content</div>} />
          <Route path="*" element={<div>Page Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout navigation', () => {
  beforeEach(() => {
    currentRole = 'admin'
    noJurisdictions = false
    window.localStorage.clear()
  })

  it('keeps primary work routes visible and secondary resources discoverable for contributors', () => {
    currentRole = 'contributor'
    renderLayout()
    const primaryNav = screen.getByTestId('primary-nav')
    expect(within(primaryNav).getAllByRole('link').map(link => link.textContent)).toEqual(['Overview', 'Licence Applications', 'Certifications', 'Change Management'])
    expect(within(primaryNav).getByRole('link', { name: 'Licence Applications' })).toHaveAttribute('href', '/licence-applications')
    fireEvent.click(screen.getByRole('button', { name: 'Resources' }))
    const resources = screen.getByTestId('nav-resources')
    expect(within(resources).getByRole('link', { name: 'Teams' })).toHaveAttribute('href', '/access-teams')
    expect(within(resources).getByRole('link', { name: 'Guide & FAQ' })).toHaveAttribute('href', '/guide')
    expect(within(resources).getByRole('link', { name: 'Change notes' })).toHaveAttribute('href', '/change-notes')
    expect(within(resources).queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument()
    expect(within(resources).queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument()
  })

  it('exposes administration only to admins and dismisses Resources on Escape', () => {
    renderLayout()
    const trigger = screen.getByRole('button', { name: 'Resources' })
    fireEvent.click(trigger)
    expect(screen.getByRole('link', { name: 'User Management' })).toHaveAttribute('href', '/admin/users')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(trigger).toHaveFocus()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('nav-resources')).not.toBeInTheDocument()
  })

  it('shows every secondary destination in the mobile drawer', () => {
    currentRole = 'contributor'
    renderLayout()
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    const primaryNav = within(screen.getByTestId('mobile-nav-drawer')).getByRole('navigation', { name: 'Primary navigation' })
    expect(within(primaryNav).getByRole('link', { name: 'Overview' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Certifications' })).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Licence Applications' })).toHaveAttribute('href', '/licence-applications')
    expect(within(primaryNav).getByRole('link', { name: 'Guide & FAQ' })).toHaveAttribute('href', '/guide')
    expect(within(primaryNav).getByRole('link', { name: 'Change notes' })).toHaveAttribute('href', '/change-notes')
    expect(within(primaryNav).getByRole('link', { name: 'My account' })).toHaveAttribute('href', '/account')
  })

  it.each([
    ['/library?section=templates', 'Form templates'],
    ['/library?section=evidence', 'Evidence'],
    ['/library?section=forms', 'Existing forms'],
    ['/library?section=invalid', 'Form templates'],
    ['/preparation?case=form-1', 'Existing forms'],
    ['/requirements/sets/source-1', 'Requirements'],
    ['/library?section=requirements', 'Requirements'],
    ['/program-workspace', 'Certification overview'],
    ['/review-cycles/assessment-1', 'Assessment overview'],
  ])('highlights the resource %s on desktop and mobile', (path, label) => {
    currentRole = 'contributor'
    renderLayout(path)
    const resources = screen.getByRole('button', { name: 'Resources' })
    expect(resources).toHaveAttribute('data-active', 'true')
    fireEvent.click(resources)
    const sidebar = screen.getByTestId('nav-resources')
    expect(within(sidebar).getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
    expect(within(sidebar).getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page')).toHaveLength(1)
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    const drawer = screen.getByTestId('mobile-nav-drawer')
    expect(within(drawer).getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
  })

  it('finds the renamed assessment overview through its former name', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Find a page' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Search pages' }), { target: { value: 'Requirement assessments' } })
    fireEvent.click(screen.getByRole('option', { name: 'Assessment overview Resources' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resources' }))
    const sidebar = screen.getByTestId('nav-resources')
    expect(within(sidebar).getByRole('link', { name: 'Assessment overview' })).toHaveAttribute('aria-current', 'page')
  })

  it.each(['Release notes', "What's new", 'Versions', 'Changelog'])('finds Change notes through %s', alias => {
    currentRole = 'contributor'
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Find a page' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Search pages' }), { target: { value: alias } })
    fireEvent.click(screen.getByRole('option', { name: 'Change notes Help' }))
    fireEvent.click(screen.getByRole('button', { name: 'Resources' }))
    expect(within(screen.getByTestId('nav-resources')).getByRole('link', { name: 'Change notes' })).toHaveAttribute('aria-current', 'page')
    expect(document.title).toMatch(/^Change notes · /)
  })

  it('opens Change notes before a jurisdiction is configured', () => {
    currentRole = 'contributor'
    noJurisdictions = true
    renderLayout('/change-notes')
    expect(screen.getByText('Page Content')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Set up a jurisdiction' })).not.toBeInTheDocument()
  })

  it('traps mobile drawer focus, closes on Escape and restores the trigger', () => {
    renderLayout()
    const trigger = screen.getByTestId('mobile-nav-toggle')
    trigger.focus()
    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Navigation' })
    const close = within(dialog).getByRole('button', { name: 'Close' })
    expect(close).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    const links = within(dialog).getAllByRole('link')
    expect(links[links.length - 1]).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  it('lets an unsaved-changes dialog own keyboard focus above the mobile drawer', () => {
    renderLayout()
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    const confirmation = document.createElement('div')
    confirmation.setAttribute('role', 'dialog')
    confirmation.setAttribute('aria-label', 'Changes are not saved yet')
    document.body.appendChild(confirmation)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByRole('dialog', { name: 'Navigation' })).toBeInTheDocument()
    confirmation.remove()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Navigation' })).not.toBeInTheDocument()
  })

  it('releases the page when an open mobile drawer becomes desktop navigation', () => {
    renderLayout()
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    const previousWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
    fireEvent.resize(window)
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.querySelector('[inert]')).not.toBeInTheDocument()
    expect(document.body.style.overflow).not.toBe('hidden')
  })
})
