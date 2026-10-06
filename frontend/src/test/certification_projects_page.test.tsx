import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

let mockRole: 'admin' | 'manager' | 'approver' | 'contributor' | 'assigned_reviewer' = 'admin'

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
      email: 'test@example.com',
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

vi.mock('../contexts/JurisdictionContext', () => ({ useJurisdiction: () => ({ jurisdictionId: 'jur-1', jurisdictionById: { 'jur-1': { name: 'Denmark' } }, setJurisdictionId: vi.fn() }) }))

import api from '../api/client'
import CertificationProjects from '../pages/CertificationProjects'
import CertificationEngagement from '../components/workflows/CertificationEngagement'
import type { CertificationProject, SubmissionPackageGateCheck } from '../types'

function makeAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {} as AxiosResponse<T>['headers'],
    config: {} as unknown as InternalAxiosRequestConfig,
  }
}

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

const baseProject = {
  id: 'proj-1',
  organization_id: null,
  source_document_id: null,
  jurisdiction_id: 'jur-1',
  name: 'Nordic launch',
  description: 'Initial flow',
  stage: 'scoping',
  status: 'active',
  owner_id: null,
  created_by: 'u-1',
  started_at: new Date().toISOString(),
  target_submission_date: new Date().toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
}

const baseMilestone = {
  id: 'mil-1',
  project_id: 'proj-1',
  stage: 'scoping',
  title: 'Scope definition',
  due_at: null,
  status: 'pending',
  notes: null,
  created_at: new Date().toISOString(),
}

const baseJurisdiction = {
  id: 'jur-1',
  code: 'dk',
  name: 'Denmark',
  regulator_name: 'Example Authority',
  report_header_text: null,
  active: true,
  created_at: new Date().toISOString(),
}

const basePackage = {
  id: 'pkg-1',
  project_id: 'proj-1',
  review_cycle_id: 'cycle-1' as string | null,
  snapshot_id: 'snapshot-1' as string | null,
  version: 'v1',
  status: 'draft',
  checklist_json: null,
  created_by: 'u-1',
  created_at: new Date().toISOString(),
}

const closedSubmissionCycle = {
  id: 'cycle-1',
  certification_project_id: 'proj-1',
  cycle_type: 'submission',
  name: 'Submission assessment: Nordic launch',
  status: 'closed',
  snapshot_id: 'snapshot-1',
}

const readyPackageGateCheck: SubmissionPackageGateCheck = {
  package_id: 'pkg-1',
  project_id: 'proj-1',
  status: 'draft',
  review_cycle_linked: true,
  review_cycle_closed: true,
  review_cycle_snapshot_id: 'snapshot-1',
  snapshot_bound: true,
  required_artifacts_total: 1,
  required_artifacts_included: 1,
  missing_required_artifacts: [],
  checklist_required_total: 3,
  checklist_required_completed: 3,
  checklist_blocking_items: [],
  checks_passed: true,
  blocking_reasons: [],
}

function renderPackageWorkspace({
  packages = [basePackage],
  gateCheck = (packageId: string) => Promise.resolve(makeAxiosResponse({ ...readyPackageGateCheck, package_id: packageId })),
  cycles = [closedSubmissionCycle],
}: {
  packages?: typeof basePackage[]
  gateCheck?: (packageId: string) => Promise<AxiosResponse<SubmissionPackageGateCheck>>
  cycles?: typeof closedSubmissionCycle[]
} = {}) {
  vi.mocked(api.get).mockImplementation((url: unknown) => {
    if (url === '/certification-projects?limit=1000') return Promise.resolve(makeAxiosResponse({ items: [baseProject], total: 1 }))
    if (url === '/submission-packages?project_id=proj-1&limit=1000') return Promise.resolve(makeAxiosResponse({ items: packages, total: packages.length }))
    if (url === '/review-cycles?certification_project_id=proj-1&limit=1000') return Promise.resolve(makeAxiosResponse({ items: cycles, total: cycles.length }))
    if (url === '/jurisdictions?limit=1000') return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
    const gateMatch = typeof url === 'string' && url.match(/^\/submission-packages\/([^/]+)\/gate-check$/)
    if (gateMatch) return gateCheck(gateMatch[1])
    return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
  })
  vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
  const queryClient = createTestQueryClient()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/?project=proj-1&section=reports']}><CertificationProjects /></MemoryRouter></QueryClientProvider>)
  return queryClient
}

describe('Certification Projects Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole = 'admin'
  })

  it('retains engagement edits after a failed save and clears the draft after success', async () => {
    const onSave = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(undefined)
    const view = render(<CertificationEngagement mode="testing" project={baseProject as CertificationProject} canManage saving={false} onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Test lab or assurance provider'), { target: { value: 'Independent lab' } })
    expect(screen.getByText('Unsaved engagement changes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save engagement' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your changes are still here')
    expect(screen.getByLabelText('Test lab or assurance provider')).toHaveValue('Independent lab')
    fireEvent.click(screen.getByRole('button', { name: 'Save engagement' }))
    await waitFor(() => expect(screen.queryByText('Unsaved engagement changes')).not.toBeInTheDocument())
    expect(onSave).toHaveBeenCalledTimes(2)
    expect(onSave).toHaveBeenLastCalledWith(expect.objectContaining({ provider_name: 'Independent lab' }))
    expect(onSave.mock.calls[1][0]).not.toHaveProperty('report_outcome')
    view.unmount()
    const saveReport = vi.fn().mockResolvedValue(undefined)
    render(<CertificationEngagement mode="report" project={baseProject as CertificationProject} canManage saving={false} onSave={saveReport} />)
    fireEvent.change(screen.getByLabelText('Report reference'), { target: { value: 'LAB-42' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save report' }))
    await waitFor(() => expect(saveReport).toHaveBeenCalledOnce())
    expect(saveReport).toHaveBeenCalledWith(expect.objectContaining({ report_reference: 'LAB-42' }))
    expect(saveReport.mock.calls[0][0]).not.toHaveProperty('provider_name')
  })

  it('renders project list and timeline section', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (
        typeof url === 'string' &&
        url.includes('/certification-projects') &&
        !url.includes('/milestones')
      ) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseProject],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/certification-projects/proj-1/milestones')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseMilestone],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/review-cycles?certification_project_id=proj-1')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
        return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CertificationProjects />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /^certifications$/i })
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getAllByText(/nordic launch/i)[0]).toBeInTheDocument()
    })
    expect(screen.getAllByText(/scoping/i).length).toBeGreaterThan(0)
  })

  it('allows admin to delete a certification project', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (
        typeof url === 'string' &&
        url.includes('/certification-projects') &&
        !url.includes('/milestones')
      ) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseProject],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
        return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })
    vi.mocked(api.delete).mockResolvedValue(makeAxiosResponse({}))

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CertificationProjects />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getAllByText(/nordic launch/i)[0]).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: /^nordic launch$/i })[0])
    fireEvent.click(screen.getByText('Project administration'))
    fireEvent.click(screen.getByRole('button', { name: /^delete project$/i }))
    const dialog = await screen.findByRole('dialog', {
      name: /delete certification project/i,
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete project$/i }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/certification-projects/proj-1')
    })
  })

  it('shows package and artifact workspace for a selected project', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (
        typeof url === 'string' &&
        url.includes('/certification-projects') &&
        !url.includes('/milestones')
      ) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [{ ...baseProject, source_document_id: 'doc-1' }],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/certification-projects/proj-1/milestones')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseMilestone],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/submission-packages?project_id=proj-1')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'pkg-1',
                project_id: 'proj-1',
                review_cycle_id: 'cycle-1',
                snapshot_id: null,
                version: 'v1',
                status: 'draft',
                checklist_json: null,
                approval_requested_at: null,
                approved_by: null,
                approved_at: null,
                locked_at: null,
                created_by: 'u-1',
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/submission-packages/pkg-1/artifacts')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'art-1',
                submission_package_id: 'pkg-1',
                artifact_type: 'report',
                name: 'SoA',
                file_path: null,
                link_url: null,
                required: true,
                included: true,
                notes: null,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/submission-packages/pkg-1/gate-check')) {
        return Promise.resolve(
          makeAxiosResponse({
            package_id: 'pkg-1',
            project_id: 'proj-1',
            status: 'draft',
            review_cycle_linked: true,
            review_cycle_closed: false,
            review_cycle_snapshot_id: null,
            snapshot_bound: false,
            required_artifacts_total: 1,
            required_artifacts_included: 1,
            missing_required_artifacts: [],
            checks_passed: false,
            blocking_reasons: ['Submission review must be closed before package approval.'],
          })
        )
      }
      if (typeof url === 'string' && url.includes('/review-cycles?certification_project_id=proj-1')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'cycle-1',
                organization_id: null,
                jurisdiction_id: 'jur-1',
                certification_project_id: 'proj-1',
                cycle_type: 'submission',
                name: 'Submission cycle: Nordic launch',
                description: null,
                scope: 'documents',
                scope_filter: null,
                document_ids: ['doc-1'],
                deadline: null,
                status: 'active',
                created_by: 'u-1',
                closed_at: null,
                closed_by: null,
                snapshot_id: null,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
        return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CertificationProjects />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getAllByText(/nordic launch/i)[0]).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: /^nordic launch$/i })[0])
    fireEvent.click(screen.getByRole('button', { name: /^reports and submission$/i }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /submission packages/i })).toBeInTheDocument()
    })

    expect(await screen.findByText(/documents for v1/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open source requirement set/i })).toHaveAttribute('href', '/requirements/sets/doc-1')
    expect(screen.getByRole('button', { name: /request approval/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /request approval/i })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /lock \+ handoff/i })).not.toBeInTheDocument()
  })

  it('puts approval blockers beside the selected action and takes users to the work that needs attention', async () => {
    renderPackageWorkspace({ gateCheck: () => Promise.resolve(makeAxiosResponse({
      ...readyPackageGateCheck,
      review_cycle_closed: false,
      snapshot_bound: false,
      required_artifacts_included: 0,
      missing_required_artifacts: ['Lab report'],
      checklist_required_completed: 2,
      checklist_blocking_items: ['Confirm supporting evidence'],
      checks_passed: false,
      blocking_reasons: [
        'Submission review cycle must be closed before package approval.',
        'Required artifacts need an included file reference or link: Lab report',
        'Required checklist items are incomplete.',
      ],
    })) })
    const readiness = await screen.findByRole('region', { name: 'Readiness for v1' })
    expect(await within(readiness).findByText('Needs attention')).toBeInTheDocument()
    const requestApproval = within(readiness).getByRole('button', { name: 'Request approval' })
    expect(requestApproval).toBeDisabled()
    fireEvent.click(requestApproval)
    expect(api.post).not.toHaveBeenCalled()
    expect(within(readiness).getByRole('link', { name: 'Open submission assessment' })).toHaveAttribute('href', '/review-cycles/cycle-1')
    fireEvent.click(within(readiness).getByRole('button', { name: 'Complete package checklist' }))
    expect(document.activeElement).toHaveAttribute('id', 'package-checklist-pkg-1')
    fireEvent.click(within(readiness).getByRole('button', { name: 'Update required documents' }))
    expect(screen.getByRole('heading', { name: 'Documents for v1' })).toHaveFocus()
  })

  it('requests internal approval when the loaded package checks pass', async () => {
    renderPackageWorkspace()
    const requestApproval = await screen.findByRole('button', { name: 'Request approval' })
    await waitFor(() => expect(requestApproval).toBeEnabled())
    expect(screen.getByText('Ready for internal approval')).toBeInTheDocument()
    expect(screen.getByText(/approval and locking remain separate from the external certification outcome/i)).toBeInTheDocument()
    fireEvent.click(requestApproval)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/submission-packages/pkg-1/request-approval'))
  })

  it('waits for the newly selected package checks instead of reusing another package readiness', async () => {
    let resolveGate: (response: AxiosResponse<SubmissionPackageGateCheck>) => void = () => undefined
    renderPackageWorkspace({
      packages: [basePackage, { ...basePackage, id: 'pkg-2', version: 'v2' }],
      gateCheck: (packageId) => packageId === 'pkg-1' ? Promise.resolve(makeAxiosResponse(readyPackageGateCheck)) : new Promise((resolve) => { resolveGate = resolve }),
    })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Request approval' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Review package' }))
    const readiness = await screen.findByRole('region', { name: 'Readiness for v2' })
    expect(within(readiness).getByRole('status')).toHaveTextContent('Checking package readiness before approval')
    expect(within(readiness).getByRole('button', { name: 'Request approval' })).toBeDisabled()
    resolveGate(makeAxiosResponse({ ...readyPackageGateCheck, package_id: 'pkg-2', checks_passed: false, blocking_reasons: ['Required checklist items are incomplete.'], checklist_blocking_items: ['Review evidence'] }))
    expect(await within(readiness).findByText('Needs attention')).toBeInTheDocument()
    expect(within(readiness).getByRole('button', { name: 'Request approval' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('recovers failed readiness checks before enabling approval', async () => {
    const gateCheck = vi.fn().mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValue(makeAxiosResponse(readyPackageGateCheck))
    renderPackageWorkspace({ gateCheck })
    const readiness = await screen.findByRole('region', { name: 'Readiness for v1' })
    expect(await within(readiness).findByRole('alert')).toHaveTextContent('Submission readiness could not be loaded')
    expect(within(readiness).getByRole('button', { name: 'Request approval' })).toBeDisabled()
    fireEvent.click(within(readiness).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(within(readiness).getByRole('button', { name: 'Request approval' })).toBeEnabled())
    expect(gateCheck).toHaveBeenCalledTimes(2)
  })

  it('does not keep a previous ready result usable after refreshing readiness fails', async () => {
    const gateCheck = vi.fn().mockResolvedValueOnce(makeAxiosResponse(readyPackageGateCheck)).mockRejectedValue(new Error('Network unavailable'))
    renderPackageWorkspace({ gateCheck })
    const requestApproval = await screen.findByRole('button', { name: 'Request approval' })
    await waitFor(() => expect(requestApproval).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Refresh readiness' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Submission readiness could not be loaded')
    expect(requestApproval).toBeDisabled()
    expect(screen.queryByText('Ready for internal approval')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it.each([false, true])('allows the server to bind a closed assessment snapshot during approval (missing link: %s)', async (missingLink) => {
    renderPackageWorkspace({
      packages: [{ ...basePackage, review_cycle_id: missingLink ? null : 'cycle-1', snapshot_id: null }],
      gateCheck: () => Promise.resolve(makeAxiosResponse({
        ...readyPackageGateCheck,
        review_cycle_linked: !missingLink,
        review_cycle_closed: !missingLink,
        review_cycle_snapshot_id: missingLink ? null : 'snapshot-1',
        snapshot_bound: false,
        checks_passed: false,
        blocking_reasons: [
          ...(missingLink ? ['Submission package is not linked to a submission review cycle.'] : []),
          'Submission package is not bound to a snapshot.',
        ],
      })),
    })
    const requestApproval = await screen.findByRole('button', { name: 'Request approval' })
    await waitFor(() => expect(requestApproval).toBeEnabled())
    expect(screen.getByText(/will be attached when you request approval/i)).toBeInTheDocument()
    fireEvent.click(requestApproval)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/submission-packages/pkg-1/request-approval'))
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('keeps an unbound package blocked when the loaded assessment is still open', async () => {
    renderPackageWorkspace({
      packages: [{ ...basePackage, review_cycle_id: null, snapshot_id: null }],
      cycles: [{ ...closedSubmissionCycle, status: 'active' }],
      gateCheck: () => Promise.resolve(makeAxiosResponse({
        ...readyPackageGateCheck,
        review_cycle_linked: false,
        review_cycle_closed: false,
        review_cycle_snapshot_id: null,
        snapshot_bound: false,
        checks_passed: false,
        blocking_reasons: ['Submission package is not linked to a submission review cycle.', 'Submission package is not bound to a snapshot.'],
      })),
    })
    expect(await screen.findByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request approval' })).toBeDisabled()
    expect(screen.queryByText(/will be attached when you request approval/i)).not.toBeInTheDocument()
  })

  it('does not treat a mismatched existing snapshot as something approval can repair', async () => {
    renderPackageWorkspace({
      packages: [{ ...basePackage, snapshot_id: 'snapshot-old' }],
      gateCheck: () => Promise.resolve(makeAxiosResponse({
        ...readyPackageGateCheck,
        checks_passed: false,
        blocking_reasons: ['Submission package snapshot does not match submission review cycle snapshot.'],
      })),
    })
    expect(await screen.findByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request approval' })).toBeDisabled()
    expect(screen.queryByText(/will be attached when you request approval/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create a new package version' }))
    expect(screen.getByRole('textbox', { name: 'Package version' })).toHaveFocus()
  })

  it('does not auto-link an assessment that conflicts with an unlinked package snapshot', async () => {
    renderPackageWorkspace({
      packages: [{ ...basePackage, review_cycle_id: null, snapshot_id: 'snapshot-old' }],
      gateCheck: () => Promise.resolve(makeAxiosResponse({
        ...readyPackageGateCheck,
        review_cycle_linked: false,
        review_cycle_closed: false,
        review_cycle_snapshot_id: null,
        checks_passed: false,
        blocking_reasons: ['Submission package is not linked to a submission review cycle.'],
      })),
    })
    expect(await screen.findByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request approval' })).toBeDisabled()
    expect(screen.queryByText('Ready for internal approval')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('hides privileged package actions for non-privileged roles', async () => {
    mockRole = 'contributor'

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (
        typeof url === 'string' &&
        url.includes('/certification-projects') &&
        !url.includes('/milestones')
      ) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [{ ...baseProject, source_document_id: 'doc-1' }],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/certification-projects/proj-1/milestones')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseMilestone],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/submission-packages?project_id=proj-1')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'pkg-1',
                project_id: 'proj-1',
                review_cycle_id: 'cycle-1',
                snapshot_id: null,
                version: 'v1',
                status: 'draft',
                checklist_json: null,
                approval_requested_at: null,
                approved_by: null,
                approved_at: null,
                locked_at: null,
                created_by: 'u-1',
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/submission-packages/pkg-1/artifacts')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }
      if (typeof url === 'string' && url.includes('/submission-packages/pkg-1/gate-check')) {
        return Promise.resolve(
          makeAxiosResponse({
            package_id: 'pkg-1',
            project_id: 'proj-1',
            status: 'draft',
            review_cycle_linked: true,
            review_cycle_closed: false,
            review_cycle_snapshot_id: null,
            snapshot_bound: false,
            required_artifacts_total: 0,
            required_artifacts_included: 0,
            missing_required_artifacts: [],
            checks_passed: false,
            blocking_reasons: ['Submission review must be closed before package approval.'],
          })
        )
      }
      if (typeof url === 'string' && url.includes('/review-cycles?certification_project_id=proj-1')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'cycle-1',
                organization_id: null,
                jurisdiction_id: 'jur-1',
                certification_project_id: 'proj-1',
                cycle_type: 'submission',
                name: 'Submission cycle: Nordic launch',
                description: null,
                scope: 'documents',
                scope_filter: null,
                document_ids: ['doc-1'],
                deadline: null,
                status: 'active',
                created_by: 'u-1',
                closed_at: null,
                closed_by: null,
                snapshot_id: null,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
        return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CertificationProjects />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getAllByText(/nordic launch/i)[0]).toBeInTheDocument()
    })
    fireEvent.click(screen.getAllByRole('button', { name: /^nordic launch$/i })[0])
    fireEvent.click(screen.getByRole('button', { name: /^reports and submission$/i }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /submission packages/i })).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /delete project/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /request approval/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /lock \+ handoff/i })).not.toBeInTheDocument()
  })

  it('requires an explicit version update and confirmation, and continues to the linked assessment', async () => {
    const project = { ...baseProject, requirement_set_ids: ['doc-1'], baseline_versions: [{ document_id: 'doc-1', requirement_set_version_id: 'version-1', version_number: 1, set_name: 'Platform' }] }
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      const path = String(url)
      if (path.startsWith('/certification-projects?')) return Promise.resolve(makeAxiosResponse({ items: [project], total: 1 }))
      if (path.startsWith('/requirements/sets?')) return Promise.resolve(makeAxiosResponse({ items: [{ document_id: 'doc-1', jurisdiction_id: 'jur-1', name: 'Platform', document_status: 'approved', current_version_id: 'version-4', current_version_number: 4 }], total: 1 }))
      if (path.startsWith('/review-cycles?')) return Promise.resolve(makeAxiosResponse({ items: [{ id: 'cycle-1', cycle_type: 'submission', status: 'active', name: 'Submission assessment' }], total: 1 }))
      if (path.startsWith('/jurisdictions')) return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({ project, warning: 'Existing assessments keep their original baseline.' }))
    const client = createTestQueryClient()
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?project=proj-1']}><CertificationProjects /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('link', { name: 'Continue requirement assessment' })).toHaveAttribute('href', '/review-cycles/cycle-1')
    fireEvent.click(screen.getByRole('button', { name: /^requirements and evidence$/i }))
    expect(screen.getByRole('checkbox', { name: 'Platform · Current v1' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Save baseline' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Update from v1 to approved v4' }))
    expect(screen.getByText('Platform: current v1 → proposed v4')).toBeInTheDocument()
    await act(async () => { client.setQueryData(['requirements-sets', 'project-baselines'], { items: [{ document_id: 'doc-1', jurisdiction_id: 'jur-1', name: 'Platform', document_status: 'approved', current_version_id: 'version-5', current_version_number: 5 }], total: 1 }) })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save baseline' })).toBeDisabled())
    expect(screen.getByText(/An approved version changed/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Update from v1 to approved v5/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Update from v1 to approved v5/ }))
    expect(screen.getByText('Platform: current v1 → proposed v5')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save baseline' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirm project baseline changes' })
    expect(within(dialog).getByText(/Existing active and closed assessments keep their original versions/)).toBeInTheDocument()
    expect(api.put).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm baseline changes' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/certification-projects/proj-1/baseline', { requirement_set_ids: ['doc-1'], target_version_ids: { 'doc-1': 'version-5' }, expected_baseline_version_ids: { 'doc-1': 'version-1' } }))
  })

  it('describes carry forward as cloning prior review work in the project migration preview', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (
        typeof url === 'string' &&
        url.includes('/certification-projects') &&
        !url.includes('/milestones')
      ) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                ...baseProject,
                requirement_set_ids: ['doc-1'],
                baseline_versions: [
                  {
                    document_id: 'doc-1',
                    requirement_set_version_id: 'version-1',
                    version_number: 1,
                    set_name: 'Source document',
                  },
                ],
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/certification-projects/proj-1/milestones')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }
      if (typeof url === 'string' && url.includes('/submission-packages?project_id=proj-1')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }
      if (typeof url === 'string' && url.includes('/review-cycles?certification_project_id=proj-1')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'cycle-1',
                organization_id: null,
                jurisdiction_id: 'jur-1',
                certification_project_id: 'proj-1',
                predecessor_cycle_id: null,
                cycle_type: 'submission',
                name: 'Submission cycle: Nordic launch',
                description: null,
                scope: 'documents',
                scope_filter: null,
                document_ids: ['doc-1'],
                baseline_versions: [],
                deadline: null,
                status: 'active',
                created_by: 'u-1',
                closed_at: null,
                closed_by: null,
                snapshot_id: null,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/requirements/sets?')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                document_id: 'doc-1',
                jurisdiction_id: 'jur-1',
                name: 'Source document',
                filename: 'source-document.pdf',
                document_status: 'approved',
                current_version_number: 2,
              },
            ],
            total: 1,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
        return Promise.resolve(makeAxiosResponse({ items: [baseJurisdiction], total: 1 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.post).mockImplementation((url: unknown) => {
      if (url === '/certification-projects/proj-1/baseline-migrations/preview') {
        return Promise.resolve(
          makeAxiosResponse({
            migration_id: 'migration-1',
            from_cycle_id: 'cycle-1',
            matched: [],
            changed: [
              {
                document_id: 'doc-1',
                set_name: 'Source document',
                reference_id: 'REQ-1',
                old_requirement_id: 'req-1',
                new_requirement_id: 'req-2',
                old_text: 'Old text',
                new_text: 'New text',
              },
              {
                document_id: 'doc-2',
                set_name: 'Second document',
                reference_id: 'REQ-1',
                old_requirement_id: 'req-3',
                new_requirement_id: 'req-4',
                old_text: 'Other old text',
                new_text: 'Other new text',
              },
            ],
            added: [],
            removed: [],
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({}))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CertificationProjects />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getAllByText(/nordic launch/i)[0]).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: /^nordic launch$/i })[0])
    fireEvent.click(screen.getByRole('button', { name: /^requirements and evidence$/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /preview migration/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /preview migration/i }))

    expect(await screen.findByText('Migration Preview')).toBeInTheDocument()
    expect(screen.getAllByText(
      'Choose whether this changed requirement should start fresh or clone the prior assessment work.'
    )).toHaveLength(2)
    expect(screen.getByText('Source document')).toBeInTheDocument()
    expect(screen.getByText('Second document')).toBeInTheDocument()
    const carryForward = screen.getAllByRole('radio', { name: /carry forward/i })
    expect(carryForward).toHaveLength(2)
    fireEvent.click(carryForward[1])
    expect(carryForward[0]).not.toBeChecked()
    expect(carryForward[1]).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: /execute migration/i }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/certification-projects/proj-1/baseline-migrations/execute',
      {
        migration_id: 'migration-1',
        changed_decisions: [
          { new_requirement_id: 'req-2', action: 'reset_pending' },
          { new_requirement_id: 'req-4', action: 'carry_forward' },
        ],
      }
    ))
  })
})
