import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import api from '../api/client'
import Layout from '../components/Layout'
import Applications from '../pages/Applications'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'
import type { LicenceApplication } from '../types/applications'
import type { PreparationCase } from '../types/preparation'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'owner', role: 'manager', full_name: 'Example User' }, isAuthenticated: true, isLoading: false }) }))
vi.mock('../components/ProductFeedback', () => ({ default: () => null }))

const application: LicenceApplication = {
  id: 'pack-1', name: 'Example operating pack', scope: 'full_pack', jurisdiction_id: 'dk', applicant: 'Example Ltd', authority: '', description: null,
  owner_id: null, due_date: null, status: 'draft', revision: 1, outcome: null,
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  components: [{ id: 'component-1', name: 'Example form', kind: 'form', required: true, included: true, owner_id: null, due_date: null, case_id: 'form-1', evidence_id: null, case_name: 'Example form', ready: true, blockers: [] }],
  followups: [], snapshots: [], history: [], readiness: { required_count: 1, ready_count: 1, ready: true, blockers: [] },
}
const form: PreparationCase = {
  id: 'form-1', name: 'Example form', kind: 'licence_application', jurisdiction_id: 'dk', project_id: null, owner_id: null, due_date: null,
  status: 'active', revision: 1, template_id: null, template_name: '', template_revision: 1,
  fields: [], responses: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  readiness: { required_count: 0, answered_count: 0, accepted_count: 0, ready: true, blockers: [] },
}

function setup(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const router = createMemoryRouter([{ element: <DraftNavigationProvider><JurisdictionProvider><Outlet /></JurisdictionProvider></DraftNavigationProvider>, children: [
    { element: <Layout />, children: [
      { path: 'licence-applications', element: <Applications /> },
      { path: '*', element: <h1>Collection</h1> },
    ] },
  ] }], { basename: '/cap', initialEntries: [`/cap${path}`] })
  const view = render(<StrictMode><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></StrictMode>)
  return { router, close: () => { view.unmount(); router.dispose(); client.clear() } }
}

const selector = () => screen.getAllByRole('combobox', { name: 'Jurisdiction selector' })[0]

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  localStorage.setItem('cap:jurisdictionId', 'fi')
  vi.mocked(api.get).mockImplementation(async (url) => {
    if (url === '/jurisdictions?limit=1000') return { data: { items: [{ id: 'dk', name: 'Denmark', code: 'DK' }, { id: 'fi', name: 'Finland', code: 'FI' }], total: 2 } }
    if (url === '/applications/pack-1') return { data: application }
    if (url === '/preparation/cases/form-1') return { data: form }
    if (url?.startsWith('/applications?') || url?.startsWith('/users/mentions?') || url?.startsWith('/certification-projects?')) return { data: { items: [], total: 0 } }
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('global jurisdiction navigation', () => {
  it.each([
    ['/certification-projects?project=project-1&jurisdiction=dk&section=history', '/certification-projects'],
    ['/change-management?change=change-1&tab=reports', '/change-management'],
    ['/requirements/item-1', '/requirements'],
    ['/requirements/sets/source-1', '/requirements'],
    ['/requirements/sets/source-1/edit', '/requirements'],
    ['/requirements/sets/source-1/import', '/requirements'],
    ['/review-cycles/review-1', '/review-cycles'],
    ['/preparation?case=form-1', '/preparation'],
  ])('returns %s to its collection when changing market', async (path, collection) => {
    const { router, close } = setup(path)
    await waitFor(() => expect(selector()).toBeEnabled())
    fireEvent.change(selector(), { target: { value: 'dk' } })
    await waitFor(() => expect(router.state.location.pathname).toBe(`/cap${collection}`))
    expect(router.state.location.search).toBe('')
    await waitFor(() => expect(selector()).toHaveValue('dk'))
    close()
  })

  it.each([
    ['?application=pack-1&tab=approval#pack-readiness', 'Example operating pack', false],
    ['?application=pack-1&case=form-1&field=answer', 'Example form', true],
  ])('switches from a linked resource to the selected market list: %s', async (query, heading, mobile) => {
    const { router, close } = setup(`/licence-applications${query}`)
    await screen.findByRole('heading', { name: heading, level: mobile ? 2 : 1 })
    // A direct link must still align the global market with the opened resource.
    await waitFor(() => expect(selector()).toHaveValue('dk'))
    if (mobile) fireEvent.click(screen.getByTestId('mobile-nav-toggle'))
    const control = mobile ? within(screen.getByRole('dialog', { name: 'Navigation' })).getByRole('combobox', { name: 'Jurisdiction selector' }) : selector()
    fireEvent.change(control, { target: { value: 'fi' } })
    await waitFor(() => expect(router.state.location.search).toBe(''))
    await waitFor(() => expect(selector()).toHaveValue('fi'))
    expect(router.state.location.pathname).toBe('/cap/licence-applications')
    expect(router.state.location.hash).toBe('')
    expect(await screen.findByRole('heading', { name: 'Licence packs' })).toBeVisible()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining('jurisdiction_id=fi')))
    expect(localStorage.getItem('cap:jurisdictionId')).toBe('fi')
    // Cached details reopened through Back still align, and can be switched again.
    await act(async () => { await router.navigate(-1) })
    await screen.findByRole('heading', { name: heading, level: mobile ? 2 : 1 })
    await waitFor(() => expect(selector()).toHaveValue('dk'))
    fireEvent.change(selector(), { target: { value: 'fi' } })
    await screen.findByRole('heading', { name: 'Licence packs' })
    await waitFor(() => expect(selector()).toHaveValue('fi'))
    expect(api.patch).not.toHaveBeenCalled()
    close()
  })

  it('keeps the resource, country and draft on Cancel, and changes country after leaving is confirmed', async () => {
    const { router, close } = setup('/licence-applications?application=pack-1')
    await screen.findByRole('heading', { name: application.name, level: 1 })
    await waitFor(() => expect(selector()).toHaveValue('dk'))
    fireEvent.click(screen.getByText(/Application details/, { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Applicant' }), { target: { value: 'Unsaved example' } })
    fireEvent.change(selector(), { target: { value: 'fi' } })
    await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(selector()).toHaveValue('dk')
    expect(screen.getByRole('textbox', { name: 'Applicant' })).toHaveValue('Unsaved example')
    expect(router.state.location.search).toBe('?application=pack-1')
    expect(localStorage.getItem('cap:jurisdictionId')).toBe('dk')
    // A later unrelated navigation must not apply the cancelled country request.
    await act(async () => { await router.navigate('/cap/other') })
    await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    fireEvent.click(screen.getByRole('button', { name: 'Leave with unsaved changes' }))
    await screen.findByRole('heading', { name: 'Collection' })
    expect(selector()).toHaveValue('dk')
    await act(async () => { await router.navigate(-1) })
    await screen.findByRole('heading', { name: application.name, level: 1 })
    fireEvent.click(screen.getByText(/Application details/, { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Applicant' }), { target: { value: 'Another unsaved example' } })
    fireEvent.change(selector(), { target: { value: 'fi' } })
    await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    fireEvent.click(screen.getByRole('button', { name: 'Leave with unsaved changes' }))
    await screen.findByRole('heading', { name: 'Licence packs' })
    await waitFor(() => expect(selector()).toHaveValue('fi'))
    close()
  })

  it('keeps the chosen market when a previous detail request finishes late', async () => {
    localStorage.setItem('cap:jurisdictionId', 'dk')
    let finish!: (response: { data: LicenceApplication }) => void
    const get = vi.mocked(api.get).getMockImplementation()!
    vi.mocked(api.get).mockImplementation((url, config) => url === '/applications/pack-1'
      ? new Promise(resolve => { finish = resolve }) : get(url, config))
    const { close } = setup('/licence-applications?application=pack-1')
    await waitFor(() => expect(selector()).toBeEnabled())
    fireEvent.change(selector(), { target: { value: 'fi' } })
    await screen.findByRole('heading', { name: 'Licence packs' })
    await act(async () => { finish({ data: application }) })
    expect(selector()).toHaveValue('fi')
    expect(screen.queryByRole('heading', { name: application.name })).not.toBeInTheDocument()
    close()
  })
})
