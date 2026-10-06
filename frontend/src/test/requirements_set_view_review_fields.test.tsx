import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type {
  Document,
  PaginatedResponse,
  RequirementSetSummary,
  RequirementSetVersion,
  RequirementWithStatus,
} from '../types'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import RequirementsSetView from '../pages/RequirementsSetView'

vi.mock('../contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: unknown }) => children,
  useAuth: () => ({
    user: {
      id: 'u1',
      email: 'admin@example.com',
      full_name: 'Admin',
      role: 'admin',
      active: true,
      created_at: new Date().toISOString(),
    },
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  }),
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

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

import api from '../api/client'

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

describe('RequirementsSetView review-specific fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('does not render status/evidence requirement fields and keeps core requirement columns', async () => {
    const documentId = 'doc-1'
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Source Set',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'draft',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      maintenance_plan_id: null,
      cadence_interval_days: null,
      testing_frequency: 'quarterly',
      archived_at: null,
      created_at: new Date().toISOString(),
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Source Set',
      document_type: 'annex_b',
      version: null,
      testing_frequency: 'quarterly',
      document_status: 'draft',
      archived_at: null,
      requirements_total: 1,
      requirements_active: 1,
      current_version_id: 'v1',
      current_version_number: 1,
      current_version_status: 'draft',
    }

    const versions: RequirementSetVersion[] = [
      {
        id: 'v1',
        organization_id: 'org-1',
        document_id: documentId,
        version_number: 1,
        status: 'draft',
        is_current: true,
        based_on_version_id: null,
        change_summary: null,
        created_by: 'u1',
        approved_by: null,
        created_at: new Date().toISOString(),
        approved_at: null,
        locked_at: null,
      },
    ]

    const requirements: RequirementWithStatus[] = [
      {
        id: 'r1',
        organization_id: 'org-1',
        jurisdiction_id: 'jur-1',
        source_extraction_id: null,
        document_id: documentId,
        requirement_set_version_id: 'v1',
        source_requirement_id: null,
        reference_id: '1',
        title: 'Original Requirement',
        text: '<p>Must support source-only display</p>',
        requirement_type: 'mandatory',
        parent_id: null,
        default_owner_id: null,
        active: true,
        version: 1,
        sort_order: 1,
        created_at: new Date().toISOString(),
        current_status: 'in_progress',
        assigned_to: null,
        status_history: [],
        evidence_counts: { notes: 2, files: 1, links: 3 },
      },
    ]

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'jur-1',
                code: 'dk',
                name: 'Denmark',
                regulator_name: 'Example Authority',
                report_header_text: null,
                active: true,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }

      if (url === `/documents/${documentId}`) {
        return Promise.resolve(makeAxiosResponse(doc))
      }

      if (url.startsWith('/requirements/sets?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementSetSummary>>({
            items: [summary],
            total: 1,
          })
        )
      }

      if (url === `/requirements/sets/${documentId}/versions`) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementSetVersion>>({
            items: versions,
            total: 1,
          })
        )
      }

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: requirements,
            total: 1,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/requirements/sets/${documentId}`]}>
          <JurisdictionProvider>
            <Routes>
              <Route path="/requirements/sets/:documentId" element={<RequirementsSetView />} />
            </Routes>
          </JurisdictionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByText('Source Set')).toBeInTheDocument()
    expect(screen.queryByLabelText(/requirements status filter/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Notes 2 • Files 1 • Links 3')).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Reference$/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Requirement$/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /^Type$/i })).toBeInTheDocument()

    const referenceHeader = screen.getByRole('columnheader', { name: /^Reference$/i })
    const requirementsTable = referenceHeader.closest('table')
    expect(requirementsTable).toBeTruthy()
    const tableScope = within(requirementsTable as HTMLTableElement)
    expect(tableScope.queryByRole('columnheader', { name: /^Status$/i })).not.toBeInTheDocument()
    expect(tableScope.queryByRole('columnheader', { name: /^Evidence$/i })).not.toBeInTheDocument()
    expect(tableScope.getByRole('link', { name: /^Open$/i })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements search' }), { target: { value: 'no-matching-synthetic-requirement' } })
    expect(screen.getByText('No requirements found', { exact: true })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('all')
    fireEvent.change(screen.getByRole('textbox', { name: 'Requirements search' }), { target: { value: '' } })
    expect(tableScope.getByRole('link', { name: /^Open$/i })).toBeInTheDocument()
    expect(screen.queryByText('No requirements found', { exact: true })).not.toBeInTheDocument()
  })

  it('uses decision modals for approve and reject actions', async () => {
    const documentId = 'doc-2'
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Pending Set',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'pending_approval',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      maintenance_plan_id: null,
      cadence_interval_days: null,
      testing_frequency: 'quarterly',
      archived_at: null,
      created_at: new Date().toISOString(),
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Pending Set',
      document_type: 'annex_b',
      version: null,
      testing_frequency: 'quarterly',
      document_status: 'pending_approval',
      archived_at: null,
      requirements_total: 0,
      requirements_active: 0,
      current_version_id: null,
      current_version_number: null,
      current_version_status: null,
    }

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'jur-1',
                code: 'dk',
                name: 'Denmark',
                regulator_name: 'Example Authority',
                report_header_text: null,
                active: true,
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }
      if (url === `/documents/${documentId}`) return Promise.resolve(makeAxiosResponse(doc))
      if (url.startsWith('/requirements/sets?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementSetSummary>>({
            items: [summary],
            total: 1,
          })
        )
      }
      if (url === `/requirements/sets/${documentId}/versions`) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementSetVersion>>({
            items: [],
            total: 0,
          })
        )
      }
      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: [],
            total: 0,
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/requirements/sets/${documentId}`]}>
          <JurisdictionProvider>
            <Routes>
              <Route path="/requirements/sets/:documentId" element={<RequirementsSetView />} />
            </Routes>
          </JurisdictionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByText('Pending Set')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Approve$/i }))
    const approveDialog = await screen.findByRole('dialog', {
      name: /approve requirement set/i,
    })
    fireEvent.click(within(approveDialog).getByRole('button', { name: /^Approve$/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/documents/${documentId}/approve`,
        null,
        expect.objectContaining({ params: undefined })
      )
    })

    fireEvent.click(screen.getByRole('button', { name: /^Reject$/i }))
    const rejectDialog = await screen.findByRole('dialog', {
      name: /reject requirement set/i,
    })
    const rejectConfirm = within(rejectDialog).getByRole('button', { name: /^Reject$/i })
    expect(rejectConfirm).toBeDisabled()

    fireEvent.change(within(rejectDialog).getByLabelText(/rejection comment/i), {
      target: { value: 'Needs revision' },
    })
    fireEvent.click(within(rejectDialog).getByRole('button', { name: /^Reject$/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/documents/${documentId}/reject`,
        null,
        expect.objectContaining({ params: { comment: 'Needs revision' } })
      )
    })
  })
})
