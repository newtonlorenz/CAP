import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, createMemoryRouter, RouterProvider, Link } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

let mockJurisdictionCode = 'dk'

let mockRole: 'admin' | 'manager' | 'approver' | 'contributor' | 'assigned_reviewer' = 'manager'

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
    toasts: [],
  }),
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u-1',
      organization_id: null,
      email: 'user@example.com',
      full_name: 'Test User',
      role: mockRole,
      active: true,
      created_at: new Date().toISOString(),
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'jur-1',
    jurisdictions: [
      {
        id: 'jur-1',
        code: mockJurisdictionCode,
        name: mockJurisdictionCode === 'dk' ? 'Denmark' : 'Example jurisdiction',
      },
    ],
    jurisdictionById: {
      'jur-1': {
        id: 'jur-1',
        code: mockJurisdictionCode,
        name: mockJurisdictionCode === 'dk' ? 'Denmark' : 'Example jurisdiction',
      },
    },
    isLoading: false,
    setJurisdictionId: vi.fn(),
  }),
}))

import api from '../api/client'
import ChangeManagement from '../pages/ChangeManagement'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'

function makeAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {} as AxiosResponse<T>['headers'],
    config: {} as unknown as InternalAxiosRequestConfig,
  }
}

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

function setupApiMocks(options?: {
  registers?: unknown[]
  components?: unknown[]
  changes?: unknown[]
  baselines?: unknown[]
}) {
  const registers = options?.registers ?? []
  const components = options?.components ?? []
  const changes = options?.changes ?? []
  const baselines = options?.baselines ?? []

  vi.mocked(api.get).mockImplementation((url: unknown) => {
    if (typeof url === 'string' && url.startsWith('/change-management/registers?')) {
      return Promise.resolve(makeAxiosResponse({ items: registers, total: registers.length }))
    }
    if (typeof url === 'string' && url.includes('/change-management/registers/reg-1/components')) {
      return Promise.resolve(makeAxiosResponse({ items: components, total: components.length }))
    }
    if (typeof url === 'string' && url.includes('/change-management/registers/reg-1/changes')) {
      return Promise.resolve(makeAxiosResponse({ items: changes, total: changes.length }))
    }
    if (typeof url === 'string' && url.includes('/change-management/registers/reg-1/baselines')) {
      return Promise.resolve(makeAxiosResponse({ items: baselines, total: baselines.length }))
    }
    if (typeof url === 'string' && /^\/change-management\/changes\/[^/]+$/.test(url)) {
      const change = changes.find(item => (item as { id: string }).id === url.split('/').slice(-1)[0])
      if (change) return Promise.resolve(makeAxiosResponse(change))
    }
    return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
  })
}

function renderPage() {
  const queryClient = createQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ChangeManagement />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => { mockJurisdictionCode = 'dk' })

describe('ChangeManagement page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({ id: 'reg-new' }))
    vi.mocked(api.delete).mockResolvedValue(makeAxiosResponse({}))
    mockRole = 'manager'
  })

  it('renders tabs and loaded component rows', async () => {
    setupApiMocks({
      registers: [
        {
          id: 'reg-1',
          organization_id: null,
          jurisdiction_id: 'jur-1',
          name: 'DK Register',
          status: 'active',
          created_by: 'u-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      components: [
        {
          id: 'comp-1',
          register_id: 'reg-1',
          component_uid: 'COMP-1',
          definition: 'Service',
          version: '1.0.0',
          identifying_characteristics: 'svc',
          change_owner_id: null,
          change_owner_name: 'Ops',
          confidentiality_code: 2,
          integrity_code: 3,
          availability_code: 2,
          accountability_code: 2,
          classification_code: 3,
          checksum_hash: 'hash',
          is_hardware: false,
          geographic_location: null,
          hosting_model: 'on_prem',
          virtualized: false,
          public_cloud_provider: null,
          public_cloud_certification: null,
          public_cloud_independent: false,
          public_cloud_redundancy: false,
          status: 'active',
          created_by: 'u-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /change management/i })).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /components/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /change register/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /baselines/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reports/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', {name:'Components'}))
    await waitFor(() => {
      expect(screen.getByText('COMP-1')).toBeInTheDocument()
    })
  })

  it('submits create register form on click', async () => {
    setupApiMocks({ registers: [] })

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create register/i })).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: /create register/i }))
    fireEvent.click(screen.getByRole('button', { name: /save register/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/change-management/registers',
        expect.objectContaining({
          jurisdiction_id: 'jur-1',
          name: 'Component register',
          status: 'active',
        })
      )
    })
  })

  it('shows role guidance for contributor when no register exists', async () => {
    mockRole = 'contributor'
    setupApiMocks({ registers: [] })

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /change management/i })).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /create register/i })).not.toBeInTheDocument()
    expect(
      screen.getByText(/Register setup is restricted to manager and admin roles/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/Ask a manager or admin to create the component register/i)).toBeInTheDocument()
  })

  it('shows reports tab content even without selected register', async () => {
    setupApiMocks({ registers: [] })

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /reports/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /reports/i }))

    expect(screen.getByText(/Change reports/i)).toBeInTheDocument()
    expect(screen.getByText(/Export CSV reports/i)).toBeInTheDocument()
    expect(screen.getByText(/Components Report/i)).toBeInTheDocument()
  })

  it('uses submit buttons for register, component, change, and baseline forms', async () => {
    setupApiMocks({
      registers: [
        {
          id: 'reg-1',
          organization_id: null,
          jurisdiction_id: 'jur-1',
          name: 'DK Register',
          status: 'active',
          created_by: 'u-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/DK Register/i)).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /create register/i })).toHaveAttribute('type', 'button')
    fireEvent.click(screen.getByRole('button', { name: /create register/i }))
    expect(screen.getByRole('button', { name: /save register/i })).toHaveAttribute('type', 'submit')
    fireEvent.click(screen.getByRole('button', {name:'Components'}))
    expect(screen.getByRole('button', { name: /add component/i })).toHaveAttribute('type', 'submit')

    fireEvent.click(screen.getByRole('button', { name: /change register/i }))
    fireEvent.click(screen.getByRole('button', {name:'New change'}))
    expect(screen.getByRole('button', { name: 'Save draft' })).toHaveAttribute('type', 'submit')
    fireEvent.click(within(screen.getByRole('dialog', {name:'New change'})).getByRole('button',{name:'Cancel'}))

    fireEvent.click(screen.getByRole('button', { name: /baselines/i }))
    expect(screen.getByRole('button', { name: /freeze baseline/i })).toHaveAttribute('type', 'submit')
  })

  it('saves a minimal draft without invented planned dates or approval details', async () => {
    setupApiMocks({ registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Draft register', status: 'active' }] })
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({ id: 'chg-new' }))
    renderPage()
    await screen.findByText('Draft register')
    fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
    fireEvent.click(screen.getByRole('button', { name: 'New change' }))
    const submit = screen.getByRole('button', { name: 'Save draft' })
    const form = submit.closest('form')!
    const fields = within(form)

    expect(form.checkValidity()).toBe(false)
    expect(fields.getByLabelText('Planned Start')).toHaveValue('')
    expect(fields.getByLabelText('Planned End')).toHaveValue('')
    expect(fields.getByText('Planning and justification').closest('details')).not.toHaveAttribute('open')
    expect(fields.getByText('Impact evaluation').closest('details')).not.toHaveAttribute('open')
    fireEvent.change(fields.getByLabelText('Change title'), { target: { value: 'Replace signing service' } })
    expect(form.checkValidity()).toBe(true)
    fireEvent.click(submit)

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/change-management/registers/reg-1/changes', expect.objectContaining({
      title: 'Replace signing service',
      change_type: 'normal',
      description: null,
      complexity_classification: null,
      resource_assessment: null,
      scheduling_assessment: null,
      justification: null,
      planned_start_at: null,
      planned_end_at: null,
      evaluation_effect: null,
      evaluation_risk: null,
      evaluation_regulatory_impact: null,
      evaluation_ciaa_impact: null,
      components: [],
      testing_org_required: true,
      testing_org_status: 'pending',
      testing_org_cycle: 'annual',
    })))
  })

  it('preserves optional draft details across disclosures and a failed save', async () => {
    setupApiMocks({ registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Draft register', status: 'active' }] })
    vi.mocked(api.post).mockRejectedValue(new Error('Save unavailable'))
    renderPage()
    await screen.findByText('Draft register')
    fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
    fireEvent.click(screen.getByRole('button', { name: 'New change' }))
    const submit = screen.getByRole('button', { name: 'Save draft' })
    const form = submit.closest('form')!
    const fields = within(form)
    fireEvent.change(fields.getByLabelText('Change title'), { target: { value: 'Keep this draft' } })
    const planningSummary = fields.getByText('Planning and justification')
    fireEvent.click(planningSummary)
    expect(planningSummary.closest('details')).toHaveAttribute('open')
    fireEvent.change(fields.getByLabelText('Resource assessment'), { target: { value: 'Two engineers' } })
    expect(fields.getByText('1 of 6 details recorded')).toBeInTheDocument()
    fireEvent.click(planningSummary)
    expect(planningSummary.closest('details')).not.toHaveAttribute('open')
    fireEvent.click(fields.getByText('Impact evaluation'))
    fireEvent.change(fields.getByLabelText('Evaluation: risk'), { target: { value: 'Low risk' } })
    expect(fields.getByText('1 of 4 evaluations recorded')).toBeInTheDocument()
    fireEvent.click(submit)

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    await waitFor(() => expect(submit).toBeEnabled())
    expect(fields.getByLabelText('Change title')).toHaveValue('Keep this draft')
    fireEvent.click(planningSummary)
    expect(fields.getByLabelText('Resource assessment')).toHaveValue('Two engineers')
    expect(fields.getByLabelText('Evaluation: risk')).toHaveValue('Low risk')
  })

  it('reveals invalid optional dates without requiring dates for an unscheduled draft', async () => {
    mockJurisdictionCode = 'example'
    setupApiMocks({ registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Draft register', status: 'active' }] })
    renderPage()
    await screen.findByText('Draft register')
    fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
    fireEvent.click(screen.getByRole('button', { name: 'New change' }))
    const form = screen.getByRole('button', { name: 'Save draft' }).closest('form')!
    const fields = within(form)
    fireEvent.change(fields.getByLabelText('Change title'), { target: { value: 'Scheduled draft' } })
    fireEvent.change(fields.getByLabelText('Planned Start'), { target: { value: '2026-10-10T14:00' } })
    fireEvent.change(fields.getByLabelText('Planned End'), { target: { value: '2026-10-10T13:00' } })
    expect(form.checkValidity()).toBe(false)
    expect(fields.getByText('Planning and justification').closest('details')).toHaveAttribute('open')
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.change(fields.getByLabelText('Planned End'), { target: { value: '2026-10-10T15:00' } })
    expect(form.checkValidity()).toBe(true)

    fireEvent.change(fields.getByLabelText('Testing organization approval date'), { target: { value: '2999-01-01T12:00' } })
    expect(form.checkValidity()).toBe(false)
    expect(fields.getByText('Testing organization', { exact: true }).closest('details')).toHaveAttribute('open')
    fireEvent.change(fields.getByLabelText('Testing organization approval date'), { target: { value: '' } })
    fireEvent.change(fields.getByLabelText('Planned Start'), { target: { value: '' } })
    fireEvent.change(fields.getByLabelText('Planned End'), { target: { value: '' } })
    expect(form.checkValidity()).toBe(true)
  })

  it.each([
    { action: 'Approve', status: 'draft', payloadField: 'approval_decision' },
    { action: 'Reject', status: 'draft', payloadField: 'rejection_reason' },
    { action: 'Implement', status: 'approved', payloadField: 'implementation_notes' },
    { action: 'Verify', status: 'implemented', payloadField: 'verification_notes' },
  ])('identifies and selects the target when opening $action', async ({ action, status, payloadField }) => {
    const base = { register_id: 'reg-1', change_type: 'normal', description: 'Replace the service', complexity_classification: 'Low', resource_assessment: 'Two engineers', scheduling_assessment: 'Maintenance window', planned_start_at: '2026-09-20T10:00:00Z', planned_end_at: '2026-09-20T11:00:00Z', justification: 'Supported service', evaluation_effect: 'Improved availability', evaluation_risk: 'Low', evaluation_regulatory_impact: 'None', evaluation_ciaa_impact: 'Availability improves', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z', components: [{ component_id: 'comp-1', planned_version: '1.1' }], events: [], integration_checks: [], readiness: { approval: {ready: true, reasons: []}, implementation: {ready: true, reasons: []}, verification: {ready: true, reasons: []} } }
    setupApiMocks({
      registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Action register', status: 'active' }],
      changes: [
        { ...base, id: 'chg-1', title: 'Previously selected change', status: 'draft' },
        { ...base, id: 'chg-2', title: 'Target change', status },
      ],
    })
    renderPage()
    await screen.findByText('Action register')
    fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
    const firstRow = (await screen.findByText('Previously selected change')).closest('li')!
    fireEvent.click(within(firstRow).getByRole('button', { name: 'Details' }))
    await screen.findByRole('heading', { name: 'Previously selected change', level: 2 })
    expect(screen.queryByRole('textbox', { name: 'Search changes' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Component Register' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '← Back to changes' }))
    expect(screen.getByRole('textbox', { name: 'Search changes' })).toBeVisible()
    const targetRow = screen.getByText('Target change').closest('li')!
    fireEvent.click(within(targetRow).getByRole('button', { name: 'Details' }))
    await screen.findByRole('heading', { name: 'Target change', level: 2 })
    expect(screen.queryByRole('heading', { name: 'Previously selected change', level: 2 })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: action === 'Implement' ? 'Record implementation' : action === 'Approve' ? 'Approve change' : action }))

    const workflowForm = await screen.findByRole('form', { name: `${action} Change: Target change` })
    const heading = screen.getByRole('heading', { name: `${action} Change: Target change` })
    expect(within(heading.parentElement!).getByText(status[0].toUpperCase() + status.slice(1))).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Target change', level: 2, hidden: true })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Previously selected change', level: 2 })).not.toBeInTheDocument()
    fireEvent.change(within(workflowForm).getByLabelText('Enter required rationale'), { target: { value: 'Reviewed the target change' } })
    if (action === 'Implement') {
      expect(within(workflowForm).getByLabelText('Implemented Start')).toHaveValue('')
      expect(within(workflowForm).getByLabelText('Implemented End')).toHaveValue('')
      fireEvent.change(within(workflowForm).getByLabelText('Implemented Start'), { target: { value: '2026-09-20T10:00' } })
      fireEvent.change(within(workflowForm).getByLabelText('Implemented End'), { target: { value: '2026-09-20T11:00' } })
    }
    fireEvent.click(within(workflowForm).getByRole('button', { name: `${action} Change` }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/change-management/changes/chg-2/${action.toLowerCase()}`, expect.objectContaining({
      [payloadField]: 'Reviewed the target change',
    })))
  })

  it('takes an incomplete draft to its proposal details before asking for approval rationale', async () => {
    mockJurisdictionCode = 'example'
    setupApiMocks({
      registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Approval register', status: 'active' }],
      changes: [{ id: 'chg-1', register_id: 'reg-1', title: 'Early draft', change_type: 'normal', status: 'draft', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z', components: [], events: [], integration_checks: [] }],
    })
    renderPage()
    await screen.findByText('Approval register')
    fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
    const row = (await screen.findByText('Early draft')).closest('li')!
    fireEvent.click(within(row).getByRole('button', { name: 'Details' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Review proposal' }))
    await screen.findByText('Finish these proposal details before approval:')
    expect(screen.getByText('At least one linked component')).toBeVisible()
    expect(screen.getByText('Planning: complexity, resources, scheduling, planned start, planned end, justification')).toBeVisible()
    expect(screen.queryByRole('textbox', { name: 'Enter required rationale' })).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Complete proposal details' }))
    const editDialog = await screen.findByRole('dialog', { name: 'Edit: Early draft' })
    const editor = within(editDialog)
    expect(editor.getByLabelText('Change title')).toHaveValue('Early draft')
    fireEvent.change(editor.getByLabelText('Description'), { target: { value: 'Unsaved proposal description' } })
    fireEvent.click(editor.getByRole('button', { name: 'Cancel' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Discard unsaved changes?' })).getByRole('button', { name: 'Cancel' }))
    expect(editor.getByLabelText('Description')).toHaveValue('Unsaved proposal description')
  })

  it('requires rationale before deleting a timeline event', async () => {
    setupApiMocks({
      registers: [
        {
          id: 'reg-1',
          organization_id: null,
          jurisdiction_id: 'jur-1',
          name: 'DK Register',
          status: 'active',
          created_by: 'u-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      changes: [
        {
          id: 'chg-1',
          register_id: 'reg-1',
          title: 'Rotate encryption key',
          description: 'Routine key rollover',
          category: 'security',
          status: 'draft',
          change_type: 'normal',
          complexity_classification: 'medium',
          resource_assessment: null,
          scheduling_assessment: null,
          affected_components_summary: null,
          affected_docs_summary: null,
          planned_start_at: null,
          planned_end_at: null,
          justification: 'Quarterly practice',
          affected_documentation: null,
          evaluation_effect: null,
          evaluation_risk: null,
          evaluation_regulatory_impact: null,
          evaluation_ciaa_impact: null,
          testing_org_required: true,
          testing_org_status: null,
          testing_org_cycle: 'annual',
          testing_org_next_due_at: null,
          testing_org_approved_at: null,
          integration_related: true,
          proposed_by: 'u-1',
          proposed_at: new Date().toISOString(),
          approved_by: null,
          approved_at: null,
          rejected_by: null,
          rejected_at: null,
          rejection_reason: null,
          implemented_by: null,
          implemented_at: null,
          implementation_notes: null,
          implemented_start_at: null,
          implemented_end_at: null,
          verified_by: null,
          verified_at: null,
          verification_notes: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          components: [],
          events: [
            {
              id: 'evt-1',
              event_type: 'note',
              note: 'Planned maintenance',
              created_by: 'u-1',
              created_at: new Date().toISOString(),
              updated_at: null,
              deleted_at: null,
              deleted_by: null,
              deleted_reason: null,
            },
          ],
          integration_checks: [],
        },
      ],
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/DK Register/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /change register/i }))
    const titleCell = await screen.findByText('Rotate encryption key')
    const changeRow = titleCell.closest('li')
    expect(changeRow).not.toBeNull()

    fireEvent.click(
      within(changeRow as HTMLLIElement).getByRole('button', { name: /details/i })
    )
    await screen.findByRole('heading', { name: /rotate encryption key/i, level: 2 })
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }))

    const dialog = await screen.findByRole('dialog', { name: /delete timeline event/i })
    const confirmButton = screen.getByRole('button', { name: /delete event/i })
    expect(confirmButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/deletion rationale/i), {
      target: { value: 'Superseded by corrected event entry' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /delete event/i }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith(
        '/change-management/changes/chg-1/events/evt-1',
        expect.objectContaining({
          data: { reason: 'Superseded by corrected event entry' },
        })
      )
    })
  })
})

it.each(['draft', 'approved'])('preserves the approval boundary and version evidence for a %s proposal', async (status) => {
  vi.clearAllMocks()
  mockRole = 'manager'
  const change = {
    id: 'chg-1', title: 'Version-preserving edit', status, change_type: 'normal',
    description: 'Test proposal', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z',
    components: [{ component_id: 'comp-1', version_at_proposal: '1.0', planned_version: '1.1', implemented_version: '1.1' }],
    events: [], integration_checks: [],
  }
  setupApiMocks({ registers: [{ id: 'reg-1', jurisdiction_id: 'jur-1', name: 'Version fixture', status: 'active', created_at: '2026-09-20T10:00:00Z' }], changes: [change] })
  vi.mocked(api.patch).mockResolvedValue(makeAxiosResponse(change))
  renderPage()
  await screen.findByText('Version fixture')
  fireEvent.click(screen.getByRole('button', { name: 'Change Register' }))
  const row = (await screen.findByText('Version-preserving edit')).closest('li')!
  fireEvent.click(within(row).getByRole('button', {name:'Details'}))
  fireEvent.click(await screen.findByRole('button', { name: 'Edit change evidence' }))
  const save = await screen.findByRole('button', { name: 'Save Change' })
  if (status === 'approved') {
    expect(within(save.closest('form')!).getByLabelText('Change title')).toBeDisabled()
    expect(within(save.closest('form')!).getByLabelText('Evaluation decision')).toBeEnabled()
  }
  fireEvent.submit(save.closest('form')!)
  await waitFor(() => expect(api.patch).toHaveBeenCalled())
  const payload = vi.mocked(api.patch).mock.calls[0][1]
  if (status === 'draft') expect(payload).toMatchObject({ components: [{ component_id: 'comp-1', version_at_proposal: '1.0', planned_version: '1.1', implemented_version: '1.1' }] })
  else {
    expect(payload).not.toHaveProperty('components')
    expect(payload).not.toHaveProperty('title')
    expect(payload).toHaveProperty('compliance')
  }
})

const workflowRegister = {id:'reg-1',jurisdiction_id:'jur-1',name:'Workflow fixture',status:'active',created_at:'2026-10-01T10:00:00Z'}
function workflowChange(overrides: Record<string, unknown> = {}) {
  return {id:'chg-1',register_id:'reg-1',title:'PAM release',status:'draft',description:'Replace the authorisation service',justification:'Close a security finding',change_type:'normal',components:[],events:[],integration_checks:[],proposed_at:'2026-10-01T10:00:00Z',updated_at:'2026-10-01T10:00:00Z',...overrides}
}

it('saves an incomplete title-only change as a draft and preserves it after a failed request', async () => {
  vi.clearAllMocks(); mockRole='manager'
  setupApiMocks({registers:[workflowRegister]})
  vi.mocked(api.post).mockRejectedValue(new Error('offline'))
  renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'New change'}))
  const dialog=screen.getByRole('dialog',{name:'New change'})
  fireEvent.change(within(dialog).getByLabelText('Change title'),{target:{value:'Review PAM scope'}})
  fireEvent.click(within(dialog).getByRole('button',{name:'Save draft'}))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/change-management/registers/reg-1/changes',expect.objectContaining({title:'Review PAM scope',components:[]})))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Your entries are preserved')
  expect(within(dialog).getByLabelText('Change title')).toHaveValue('Review PAM scope')
})

it('requires a discard decision when dismissing an unsaved change, and restores the editor on cancellation', async () => {
  vi.clearAllMocks(); mockRole='manager';setupApiMocks({registers:[workflowRegister]});renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'New change'}))
  const editor=screen.getByRole('dialog',{name:'New change'})
  fireEvent.change(within(editor).getByLabelText('Change title'),{target:{value:'Keep this draft'}})
  fireEvent.keyDown(window,{key:'Escape'})
  const decision=await screen.findByRole('dialog',{name:'Discard unsaved changes?'})
  fireEvent.click(within(decision).getByRole('button',{name:'Cancel'}))
  expect(within(editor).getByLabelText('Change title')).toHaveValue('Keep this draft')
  fireEvent.click(within(editor).getByRole('button',{name:'Cancel'}))
  fireEvent.click(within(await screen.findByRole('dialog',{name:'Discard unsaved changes?'})).getByRole('button',{name:'Discard changes'}))
  expect(screen.queryByRole('dialog',{name:'New change'})).not.toBeInTheDocument()
})

it('shows full approved scope to a reader and makes missing release evidence visible before implementation', async () => {
  vi.clearAllMocks();mockRole='contributor'
  const change=workflowChange({status:'approved',readiness:{approval:{ready:true,reasons:[]},implementation:{ready:false,reasons:[{code:'rng_certificate',message:'RNG certification is required before implementation'}]},verification:{ready:false,reasons:[]}}})
  setupApiMocks({registers:[workflowRegister],changes:[change]});renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Details'}))
  expect(await screen.findByText('Replace the authorisation service')).toBeInTheDocument()
  expect(screen.getByText('Close a security finding')).toBeInTheDocument()
  expect(screen.getByText('RNG certification is required before implementation')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Record implementation'})).toBeDisabled()
  expect(screen.queryByRole('button',{name:'Approve change'})).not.toBeInTheDocument()
})

it('names the approval target so a decision cannot silently apply to another selected record', async () => {
  vi.clearAllMocks();mockRole='manager'
  setupApiMocks({registers:[workflowRegister],changes:[workflowChange({readiness:{approval:{ready:true,reasons:[]}}})]});renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Details'}))
  fireEvent.click(screen.getByRole('button',{name:'Approve change'}))
  const dialog=await screen.findByRole('dialog',{name:'Approve: PAM release'})
  expect(within(dialog).getByText('Replace the authorisation service')).toBeInTheDocument()
  fireEvent.change(within(dialog).getByLabelText('Enter required rationale'),{target:{value:'Scope and evidence reviewed'}})
  vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
  fireEvent.click(within(dialog).getByRole('button',{name:'Approve Change'}))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/change-management/changes/chg-1/approve',{approval_decision:'Scope and evidence reviewed'}))
})

it('records explicit actual versions rather than inferring them from the planned change', async () => {
  vi.clearAllMocks();mockRole='manager'
  const link={component_id:'comp-1',version_at_proposal:'1.0',planned_version:'1.1',planned_checksum_hash:'expected',frozen_snapshot:{component_uid:'PAM',classification_code:3}}
  setupApiMocks({registers:[workflowRegister],changes:[workflowChange({status:'approved',components:[link],readiness:{implementation:{ready:true,reasons:[]}}})]});renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Details'}));fireEvent.click(screen.getByRole('button',{name:'Record implementation'}))
  const dialog=await screen.findByRole('dialog',{name:'Implement: PAM release'})
  expect(within(dialog).getByLabelText('Implemented Start')).toHaveValue('')
  expect(within(dialog).getByLabelText('Implemented End')).toHaveValue('')
  fireEvent.change(within(dialog).getByLabelText('Implemented Start'),{target:{value:'2026-10-01T12:00:00'}})
  fireEvent.change(within(dialog).getByLabelText('Implemented End'),{target:{value:'2026-10-01T13:00:00'}})
  fireEvent.change(within(dialog).getByLabelText(/actual version/),{target:{value:'1.1'}})
  fireEvent.change(within(dialog).getByLabelText('Actual checksum'),{target:{value:'observed-checksum'}})
  fireEvent.change(within(dialog).getByLabelText('Enter required rationale'),{target:{value:'Observed release recorded'}})
  vi.mocked(api.post).mockRejectedValue(new Error('retry'))
  fireEvent.click(within(dialog).getByRole('button',{name:'Implement Change'}))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/change-management/changes/chg-1/implement',expect.objectContaining({components:[{component_id:'comp-1',implemented_version:'1.1',implemented_checksum_hash:'observed-checksum'}]})))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Your entries are preserved')
  expect(within(dialog).getByLabelText('Actual checksum')).toHaveValue('observed-checksum')
})


it('guards real workspace navigation when a new change contains unsaved work', async () => {
  vi.clearAllMocks(); mockRole='manager'; setupApiMocks({registers:[workflowRegister]})
  const client=createQueryClient()
  const router=createMemoryRouter([{path:'/',element:<DraftNavigationProvider><Link to="/guide">Open guide</Link><ChangeManagement /></DraftNavigationProvider>},{path:'/guide',element:<p>Guide destination</p>}])
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>)
  await screen.findByText('Workflow fixture')
  const newChange=screen.queryByRole('button',{name:'New change'})
  if (newChange) fireEvent.click(newChange)
  else {fireEvent.click(screen.getByRole('button',{name:'Change Register'}));fireEvent.click(screen.getByText('Create Change Proposal',{selector:'summary'}))}
  fireEvent.change(screen.getByLabelText('Change title'),{target:{value:'Unsent change'}})
  fireEvent.click(screen.getByRole('link',{name:'Open guide'}))
  const decision=await screen.findByRole('dialog',{name:'Changes are not saved yet'})
  expect(screen.queryByText('Guide destination')).not.toBeInTheDocument()
  fireEvent.click(within(decision).getByRole('button',{name:'Cancel'}))
  expect(screen.getByLabelText('Change title')).toHaveValue('Unsent change')
})

it('protects unsaved programme evidence when switching the component register', async () => {
  vi.clearAllMocks();mockRole='manager'
  setupApiMocks({registers:[workflowRegister,{...workflowRegister,id:'reg-2',name:'Second register'}]});renderPage()
  fireEvent.click(await screen.findByRole('button',{name:'Programme assurance'}))
  const plan=await screen.findByLabelText('Approved change-management plan reference')
  fireEvent.change(plan,{target:{value:'Unsent governance evidence'}})
  fireEvent.change(screen.getByRole('combobox',{name:'Component Register'}),{target:{value:'reg-2'}})
  const dialog=await screen.findByRole('dialog',{name:'Discard unsaved changes?'})
  fireEvent.click(within(dialog).getByRole('button',{name:'Cancel'}))
  expect(screen.getByRole('combobox',{name:'Component Register'})).toHaveValue('reg-1')
  expect(plan).toHaveValue('Unsent governance evidence')
  fireEvent.change(screen.getByRole('combobox',{name:'Component Register'}),{target:{value:'reg-2'}})
  fireEvent.click(within(await screen.findByRole('dialog',{name:'Discard unsaved changes?'})).getByRole('button',{name:'Discard changes'}))
  await waitFor(()=>expect(screen.getByRole('combobox',{name:'Component Register'})).toHaveValue('reg-2'))
  expect(screen.getByLabelText('Approved change-management plan reference')).toHaveValue('')
})


it('keeps focus inside a change editor while delayed details navigation settles', async () => {
  vi.clearAllMocks(); mockRole='manager'
  setupApiMocks({registers:[workflowRegister],changes:[workflowChange()]})
  renderPage()
  const details=await screen.findByRole('button',{name:'Details'})
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
  try {
    fireEvent.click(details)
    fireEvent.click(screen.getByRole('button',{name:'Edit change evidence'}))
    const editor=screen.getByRole('dialog',{name:'Edit: PAM release'})
    expect(editor.contains(document.activeElement)).toBe(true)
    await act(async () => { vi.runOnlyPendingTimers() })
    expect(editor.contains(document.activeElement)).toBe(true)
    fireEvent.keyDown(window,{key:'Escape'})
    expect(screen.queryByRole('dialog',{name:'Edit: PAM release'})).not.toBeInTheDocument()
    expect(api.patch).not.toHaveBeenCalled()
  } finally { vi.useRealTimers() }
})

it('opens the missing impact field from prerequisites while preserving the approval gate', async () => {
  vi.clearAllMocks(); mockRole = 'manager'
  setupApiMocks({ registers: [workflowRegister], changes: [workflowChange({ readiness: {
    approval: { ready: false, reasons: [{ code: 'missing_evaluation_risk', message: 'Approval requires evaluation risk' }] },
    implementation: { ready: false, reasons: [] }, verification: { ready: false, reasons: [] },
  } })] }); renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
  expect(screen.getByRole('button', { name: 'Approve change' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Complete change details' }))
  const editor = await screen.findByRole('dialog', { name: 'Edit: PAM release' })
  expect(within(editor).getByLabelText('Evaluation: risk')).toBeVisible()
  expect(within(editor).getByLabelText('Evaluation: risk')).toHaveFocus()
  expect(api.post).not.toHaveBeenCalled()
})

it('takes assessment blockers to linked assessments without allowing read-only roles to edit change evidence', async () => {
  vi.clearAllMocks(); mockRole = 'assigned_reviewer'
  setupApiMocks({ registers: [workflowRegister], changes: [workflowChange({ readiness: {
    approval: { ready: false, reasons: [{ code: 'blocking_assessment_unresolved', message: 'Required assessment is incomplete' }, { code: 'missing_evaluation_risk', message: 'Approval requires evaluation risk' }] },
    implementation: { ready: false, reasons: [] }, verification: { ready: false, reasons: [] },
  } })] }); renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Details' }))
  fireEvent.click(screen.getByRole('button', { name: 'Review assessments' }))
  expect(document.getElementById('change-assessments')).toHaveFocus()
  expect(screen.queryByRole('button', { name: 'Complete change details' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Approve change' })).not.toBeInTheDocument()
})


it('blocks Danish approval when authoritative readiness is unavailable', async () => {
  vi.clearAllMocks(); mockRole = 'manager'
  setupApiMocks({registers: [workflowRegister], changes: [workflowChange()]}); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  expect(screen.getByRole('button', {name: 'Approve change'})).toBeDisabled()
  expect(screen.getByText('Readiness unavailable')).toBeVisible()
  expect(screen.getByText('Unavailable until readiness can be checked')).toBeVisible()
  expect(screen.queryByRole('dialog', {name: 'Approve: PAM release'})).not.toBeInTheDocument()
  expect(api.post).not.toHaveBeenCalled()
})

it('uses Danish server readiness without imposing the legacy testing status and cycle', async () => {
  vi.clearAllMocks(); mockRole = 'manager'
  const change = workflowChange({testing_org_required: true, testing_org_status: null, testing_org_cycle: null, readiness: {approval: {ready: true, reasons: []}}})
  setupApiMocks({registers: [workflowRegister], changes: [change]}); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  fireEvent.click(screen.getByRole('button', {name: 'Approve change'}))
  const dialog = await screen.findByRole('dialog', {name: 'Approve: PAM release'})
  expect(within(dialog).getByLabelText('Enter required rationale')).toBeInTheDocument()
  expect(within(dialog).getByRole('button', {name: 'Approve Change'})).toBeEnabled()
})

it('preserves Danish readiness blockers for component scope, ATO evidence and required assessments', async () => {
  vi.clearAllMocks(); mockRole = 'manager'
  const reasons = [
    {code: 'unknown_component_scope', message: 'Component regulatory scope must be classified'},
    {code: 'ato_evaluation_missing', message: 'ATO evaluation evidence is required before approval'},
    {code: 'blocking_assessment_unresolved', message: 'Required assessment is incomplete'},
  ]
  setupApiMocks({registers: [workflowRegister], changes: [workflowChange({readiness: {approval: {ready: false, reasons}}})]}); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  expect(screen.getByRole('button', {name: 'Approve change'})).toBeDisabled()
  for (const reason of reasons) expect(within(screen.getByRole('region', {name: 'Current change readiness'})).getByText(reason.message)).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})


it('preserves existing multiline proposal evidence when editing and saving a draft', async () => {
  vi.clearAllMocks(); mockRole = 'manager'
  const evidence = {
    complexity_classification: 'Low complexity\nSeparate deployment stages',
    resource_assessment: 'Two engineers\nOne independent reviewer',
    scheduling_assessment: 'Maintenance window\nRollback window',
    evaluation_effect: 'Improved availability\nReduced recovery time',
    evaluation_risk: 'Deployment risk\nRollback control',
    evaluation_regulatory_impact: 'Scope review\nNo new obligations',
    evaluation_ciaa_impact: 'Integrity review\nAvailability review',
    affected_documentation: 'Runbook\nSupport guide',
  }
  const change = workflowChange(evidence)
  setupApiMocks({registers: [workflowRegister], changes: [change]})
  vi.mocked(api.patch).mockResolvedValue(makeAxiosResponse(change)); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  fireEvent.click(screen.getByRole('button', {name: 'Edit change evidence'}))
  const dialog = await screen.findByRole('dialog', {name: 'Edit: PAM release'})
  const labels = ['Complexity', 'Resource assessment', 'Scheduling assessment', 'Evaluation: expected effect', 'Evaluation: risk', 'Evaluation: regulatory impact', 'Evaluation: CIAA impact', 'Affected documentation']
  for (const [index, value] of Object.values(evidence).entries()) {
    const field = within(dialog).getByLabelText(labels[index])
    expect(field.tagName).toBe('TEXTAREA')
    expect(field).toHaveValue(value)
  }
  fireEvent.change(within(dialog).getByLabelText('Description'), {target: {value: 'Updated description'}})
  fireEvent.submit(within(dialog).getByRole('button', {name: 'Save Change'}).closest('form')!)
  await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/change-management/changes/chg-1', expect.objectContaining(evidence)))
})


it.each([
  ['approved', 'Record implementation'],
  ['implemented', 'Verify'],
])('blocks the Danish %s transition when readiness is unavailable', async (status, action) => {
  vi.clearAllMocks(); mockRole = 'manager'
  setupApiMocks({registers: [workflowRegister], changes: [workflowChange({status})]}); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  expect(screen.getByRole('button', {name: action})).toBeDisabled()
  expect(screen.getByText('Readiness unavailable')).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})

it('keeps generic proposal review available without reporting missing Danish checks', async () => {
  vi.clearAllMocks(); mockRole = 'manager'; mockJurisdictionCode = 'example'
  setupApiMocks({registers: [workflowRegister], changes: [workflowChange()]}); renderPage()
  fireEvent.click(await screen.findByRole('button', {name: 'Details'}))
  expect(screen.getByText('Review the change proposal')).toBeVisible()
  expect(screen.queryByText('Readiness unavailable')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', {name: 'Review proposal'}))
  expect(await screen.findByRole('dialog', {name: 'Approve: PAM release'})).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})
