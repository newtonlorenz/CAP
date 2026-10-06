import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Preparation from '../pages/Preparation'
import api from '../api/client'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let role = 'manager'
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { role } }) }))
vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'dk',
    jurisdictions: [{ id: 'dk', name: 'Denmark', active: true }],
    jurisdictionById: { dk: { name: 'Denmark' } },
  }),
}))
const field = { key: 'company', label: 'Company', section: 'General', type: 'text', required: true, options: [], help_text: null, reuse_key: null }
const applicationTemplate = { id: 'licence-template', name: 'Operator licence', kind: 'licence_application', active: true, fields: [field], revision: 1 }
const auditTemplate = { ...applicationTemplate, id: 'audit-template', name: 'Audit checklist', kind: 'audit' }
const application = {
  id: 'application-1', name: 'Danish application', kind: 'licence_application', jurisdiction_id: 'dk',
  status: 'active', revision: 1, template_id: applicationTemplate.id, template_name: applicationTemplate.name,
  template_revision: 1, fields: [field], responses: [], owner_id: null, project_id: null, due_date: null,
  readiness: { required_count: 1, answered_count: 0, accepted_count: 0, blockers: [], ready: false },
}
const renderPage = (query = '') => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/licence-applications${query}`]}>
      <Preparation licenceApplications />
    </MemoryRouter>
  </QueryClientProvider>,
)

beforeEach(() => {
  role = 'manager'
  vi.resetAllMocks()
  vi.mocked(api.get).mockImplementation(async (url) => {
    if (url === '/preparation/templates?limit=500') return { data: { items: [applicationTemplate, auditTemplate], total: 2 } }
    if (url === '/preparation/starters') return { data: { items: [applicationTemplate, auditTemplate].map(({ name, kind, fields }) => ({ name, kind, fields, description: '' })) } }
    if (url === '/preparation/cases/application-1') return { data: application }
    if (url?.startsWith('/preparation/cases?')) return { data: { items: [], total: 0 } }
    if (url?.startsWith('/users/mentions') || url?.startsWith('/certification-projects')) return { data: { items: [], total: 0 } }
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('Licence Applications section', () => {
  it('scopes filtering and creation to applications and returns to the application list', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: application })
    renderPage()
    await screen.findByRole('option', { name: /Operator licence/ })
    expect(screen.queryByRole('option', { name: /Audit checklist/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Kind' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search name' }), { target: { value: 'Danish' } })
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/preparation/cases?skip=0&limit=100&q=Danish&kind=licence_application&jurisdiction_id=dk'))
    fireEvent.change(screen.getByRole('combobox', { name: 'Saved blank form' }), { target: { value: 'licence-template' } })
    expect(screen.queryByRole('combobox', { name: 'Jurisdiction' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Application name' }), { target: { value: 'Danish application' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create application' }))
    await screen.findByRole('heading', { name: 'Danish application' })
    expect(api.post).toHaveBeenCalledWith('/preparation/cases', { template_id: 'licence-template', jurisdiction_id: 'dk', name: 'Danish application', visibility: 'secret' })
    fireEvent.click(screen.getByRole('button', { name: /All applications/ }))
    expect(await screen.findByRole('heading', { name: 'Applications' })).toBeInTheDocument()
  })

  it('limits templates and starters to licences and creates the correct template kind', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: applicationTemplate })
    renderPage('?tab=templates')
    fireEvent.click(await screen.findByRole('button', { name: 'New blank form' }))
    const starter = await screen.findByRole('combobox', { name: 'Illustrative starter' })
    await waitFor(() => expect(within(starter).getByRole('option', { name: 'Operator licence' })).toBeInTheDocument())
    expect(screen.queryByText('Audit checklist')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Kind' })).toBeDisabled()
    fireEvent.change(starter, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create blank form' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/preparation/templates', expect.objectContaining({ kind: 'licence_application', name: 'Operator licence', fields: [field] })))
  })

  it('keeps non-application deep links out of this section', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...application, kind: 'audit', items: [] } })
    renderPage('?case=application-1')
    expect(await screen.findByRole('link', { name: 'Open form' })).toHaveAttribute('href', '/preparation?case=application-1')
    expect(screen.queryByRole('button', { name: 'Export preparation ZIP' })).not.toBeInTheDocument()
  })

  it('lets readers browse applications without offering creation', async () => {
    role = 'approver'
    renderPage()
    await screen.findByText(/No applications match/)
    expect(screen.queryByRole('button', { name: 'Create application' })).not.toBeInTheDocument()
  })
})
