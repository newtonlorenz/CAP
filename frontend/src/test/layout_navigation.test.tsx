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

  it('shows Guide & FAQ and Change notes under Help for contributors', () => {
    currentRole = 'contributor'
    renderLayout()

    const desktopSidebar = screen.getByTestId('desktop-sidebar')
    const primaryNav = within(desktopSidebar).getByTestId('primary-nav')

    expect(within(primaryNav).getByLabelText('Dashboard')).toBeInTheDocument()
    expect(within(primaryNav).getByLabelText('Certifications')).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Licence Applications' })).toHaveAttribute('href', '/licence-applications')
    expect(within(primaryNav).queryByRole('link', { name: 'Preparation' })).not.toBeInTheDocument()
    expect(within(primaryNav).getByText('Overview')).toBeInTheDocument()
    expect(within(primaryNav).getByText('Work')).toBeInTheDocument()
    expect(within(primaryNav).getByText('Reporting')).toBeInTheDocument()
    expect(within(primaryNav).queryByText('Library')).not.toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Teams' })).toHaveAttribute('href', '/access-teams')
    expect(within(primaryNav).getByText('Resources')).toBeInTheDocument()
    const work = within(desktopSidebar).getByTestId('nav-section-work')
    expect(within(work).getAllByRole('link').map(link => link.textContent)).toEqual(['Licence Applications', 'Certifications', 'Change Management'])
    expect(within(primaryNav).getByText('Help')).toBeInTheDocument()
    const guideLink = within(primaryNav).getByLabelText('Guide & FAQ')
    expect(guideLink).toBeInTheDocument()

    expect(guideLink).toHaveAttribute('href', '/guide')
    expect(within(primaryNav).getByRole('link', { name: 'Change notes' })).toHaveAttribute('href', '/change-notes')
  })

  it('keeps Guide & FAQ in the list when desktop sidebar is collapsed', () => {
    renderLayout()

    fireEvent.click(screen.getByRole('button', { name: /collapse sidebar/i }))

    const desktopSidebar = screen.getByTestId('desktop-sidebar')
    const primaryNav = within(desktopSidebar).getByTestId('primary-nav')

    expect(screen.getByRole('button', { name: /expand sidebar/i })).toBeInTheDocument()
    expect(within(primaryNav).getByLabelText('Guide & FAQ')).toBeInTheDocument()
    expect(within(primaryNav).getByLabelText('Change notes')).toHaveAttribute('href', '/change-notes')
    expect(within(primaryNav).getByLabelText('Certifications')).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Licence Applications' })).toHaveAttribute('href', '/licence-applications')
    expect(within(primaryNav).queryByText('Overview')).not.toBeInTheDocument()
    expect(within(primaryNav).queryByText('Help')).not.toBeInTheDocument()
  })

  it('shows Guide & FAQ and Change notes in the mobile drawer', () => {
    currentRole = 'contributor'
    renderLayout()

    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))

    const mobileDrawer = screen.getByTestId('mobile-nav-drawer')
    const primaryNav = within(mobileDrawer).getByTestId('primary-nav')

    expect(within(primaryNav).getByLabelText('Dashboard')).toBeInTheDocument()
    expect(within(primaryNav).getByLabelText('Certifications')).toBeInTheDocument()
    expect(within(primaryNav).getByRole('link', { name: 'Licence Applications' })).toHaveAttribute('href', '/licence-applications')
    const guideLink = within(primaryNav).getByLabelText('Guide & FAQ')
    expect(guideLink).toHaveAttribute('href', '/guide')
    expect(within(primaryNav).getByRole('link', { name: 'Change notes' })).toHaveAttribute('href', '/change-notes')
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
  ])('opens Resources and highlights %s on desktop and mobile', (path, label) => {
    currentRole = 'contributor'
    renderLayout(path)
    const sidebar = screen.getByTestId('desktop-sidebar')
    expect(within(sidebar).getByTestId('nav-resources')).toHaveAttribute('open')
    expect(within(sidebar).getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
    expect(within(sidebar).getAllByRole('link').filter((link) => link.getAttribute('aria-current') === 'page')).toHaveLength(1)
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    const drawer = screen.getByTestId('mobile-nav-drawer')
    expect(within(drawer).getByTestId('nav-resources')).toHaveAttribute('open')
    expect(within(drawer).getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
  })

  it('finds the renamed assessment overview through its former name', () => {
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Find a page' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Search pages' }), { target: { value: 'Requirement assessments' } })
    fireEvent.click(screen.getByRole('option', { name: 'Assessment overview Resources' }))
    const sidebar = screen.getByTestId('desktop-sidebar')
    expect(within(sidebar).getByRole('link', { name: 'Assessment overview' })).toHaveAttribute('aria-current', 'page')
  })

  it.each(['Release notes', "What's new", 'Versions', 'Changelog'])('finds Change notes through %s', alias => {
    currentRole = 'contributor'
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Find a page' }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Search pages' }), { target: { value: alias } })
    fireEvent.click(screen.getByRole('option', { name: 'Change notes Help' }))
    expect(within(screen.getByTestId('desktop-sidebar')).getByRole('link', { name: 'Change notes' })).toHaveAttribute('aria-current', 'page')
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

  it('releases the page when an open mobile drawer becomes desktop navigation', () => {
    renderLayout()
    fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.resize(window) // The test viewport is the desktop breakpoint, 1024px.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.querySelector('[inert]')).not.toBeInTheDocument()
    expect(document.body.style.overflow).not.toBe('hidden')
  })
})
