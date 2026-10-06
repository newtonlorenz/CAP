import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import RequirementsSetEdit from '../pages/RequirementsSetEdit'
import type {
  Document,
  PaginatedResponse,
  RequirementSetSummary,
  RequirementWithStatus,
} from '../types'

// RequirementsSetEdit redirects to the view page if the user is not an admin/manager.
// In the real app, auth is already resolved before this page mounts; in tests we mock auth as ready.
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

import { AuthProvider } from '../contexts/AuthContext'

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

function renderRequirementsSetEdit(documentId: string) {
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/edit?mode=all`]}>
        <AuthProvider>
          <JurisdictionProvider>
            <Routes>
              <Route
                path="/requirements/sets/:documentId/edit"
                element={<RequirementsSetEdit />}
              />
            </Routes>
          </JurisdictionProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RequirementsSetEdit parent UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('does not render Parent or Parent Title UI on subitem cards', async () => {
    const documentId = 'doc-1'

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'draft',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      testing_frequency: null,
      archived_at: null,
      created_at: new Date().toISOString(),
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      document_status: 'draft',
      archived_at: null,
      requirements_total: 2,
      requirements_active: 2,
    }

    const parentReq: RequirementWithStatus = {
      id: 'r-parent',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '1',
      title: 'Parent',
      text: '<p>Parent text</p>',
      requirement_type: 'mandatory',
      parent_id: null,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 1,
      created_at: new Date().toISOString(),
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    const childReq: RequirementWithStatus = {
      id: 'r-child',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '1.1',
      title: 'Child',
      text: '<p>Child text</p>',
      requirement_type: 'mandatory',
      parent_id: parentReq.id,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 2,
      created_at: new Date().toISOString(),
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') {
        return Promise.resolve(makeAxiosResponse({}))
      }

      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<unknown>>({
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

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: [parentReq, childReq],
            total: 2,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    renderRequirementsSetEdit(documentId)

    const matches = await screen.findAllByDisplayValue('1.1')
    expect(matches.length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(`/documents/${documentId}/prepare-edit`)
    })

    expect(screen.queryByText('Parent Title')).not.toBeInTheDocument()
    expect(screen.queryByText(/^Parent$/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/show archived requirements/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^Text$/)).not.toBeInTheDocument()
    expect(screen.getAllByLabelText(/collapse outline/i).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /add requirement/i }))
    expect(screen.queryByText(/^Parent$/)).not.toBeInTheDocument()
  })

  it('shows a hierarchy mismatch warning and repairs the stored parent', async () => {
    const documentId = 'doc-hierarchy-fix'
    const createdAt = new Date().toISOString()

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'draft',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      testing_frequency: null,
      archived_at: null,
      created_at: createdAt,
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      document_status: 'draft',
      archived_at: null,
      requirements_total: 3,
      requirements_active: 3,
    }

    const topReq: RequirementWithStatus = {
      id: 'r-top',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2',
      title: 'Accounts',
      text: '<p>Accounts</p>',
      requirement_type: 'informational',
      parent_id: null,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 1,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    const parentReq: RequirementWithStatus = {
      id: 'r-parent',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2.5',
      title: 'Player ID',
      text: '<p>Player ID</p>',
      requirement_type: 'informational',
      parent_id: topReq.id,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 2,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    const childReq: RequirementWithStatus = {
      id: 'r-child',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2.5.3',
      title: 'Child',
      text: '<p>Child text</p>',
      requirement_type: 'mandatory',
      parent_id: topReq.id,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 3,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    let requirements: RequirementWithStatus[] = [topReq, parentReq, childReq]

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<unknown>>({
            items: [
              {
                id: 'jur-1',
                code: 'dk',
                name: 'Denmark',
                regulator_name: 'Example Authority',
                report_header_text: null,
                active: true,
                created_at: createdAt,
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

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: requirements,
            total: requirements.length,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.put).mockImplementation((url: unknown, data: unknown) => {
      if (url === `/requirements/${childReq.id}`) {
        const payload = data as { sync_parent_from_reference?: boolean }
        if (payload.sync_parent_from_reference) {
          requirements = requirements.map((item) =>
            item.id === childReq.id ? { ...item, parent_id: parentReq.id } : item
          )
        }
      }
      return Promise.resolve(makeAxiosResponse({}))
    })

    renderRequirementsSetEdit(documentId)

    expect(await screen.findByText(/Hierarchy mismatch\./i)).toBeInTheDocument()
    fireEvent.click(await screen.findByTestId(`fix-hierarchy-${childReq.id}`))

    await waitFor(() => {
      expect(vi.mocked(api.put)).toHaveBeenCalledWith(`/requirements/${childReq.id}`, {
        sync_parent_from_reference: true,
      })
    })
    await waitFor(() => {
      expect(screen.queryByText(/Hierarchy mismatch\./i)).not.toBeInTheDocument()
    })
  })

  it('clears the hierarchy warning after saving a reference that matches the stored parent', async () => {
    const documentId = 'doc-hierarchy-save'
    const createdAt = new Date().toISOString()

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'draft',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      testing_frequency: null,
      archived_at: null,
      created_at: createdAt,
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      filename: 'test.pdf',
      name: 'Test Doc',
      document_type: 'annex_b',
      document_status: 'draft',
      archived_at: null,
      requirements_total: 3,
      requirements_active: 3,
    }

    const topReq: RequirementWithStatus = {
      id: 'r-top',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2',
      title: 'Accounts',
      text: '<p>Accounts</p>',
      requirement_type: 'informational',
      parent_id: null,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 1,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    const parentReq: RequirementWithStatus = {
      id: 'r-parent',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2.5',
      title: 'Player ID',
      text: '<p>Player ID</p>',
      requirement_type: 'informational',
      parent_id: topReq.id,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 2,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    const childReq: RequirementWithStatus = {
      id: 'r-child',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: documentId,
      reference_id: '3.2.5.3',
      title: 'Child',
      text: '<p>Child text</p>',
      requirement_type: 'mandatory',
      parent_id: topReq.id,
      default_owner_id: null,
      active: true,
      version: 1,
      sort_order: 3,
      created_at: createdAt,
      current_status: null,
      assigned_to: null,
      status_history: [],
      evidence_counts: { notes: 0, files: 0, links: 0 },
    }

    let requirements: RequirementWithStatus[] = [topReq, parentReq, childReq]

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<unknown>>({
            items: [
              {
                id: 'jur-1',
                code: 'dk',
                name: 'Denmark',
                regulator_name: 'Example Authority',
                report_header_text: null,
                active: true,
                created_at: createdAt,
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

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: requirements,
            total: requirements.length,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.put).mockImplementation((url: unknown, data: unknown) => {
      if (url === `/requirements/${childReq.id}`) {
        const payload = data as { reference_id?: string }
        if (payload.reference_id) {
          requirements = requirements.map((item) =>
            item.id === childReq.id
              ? { ...item, reference_id: payload.reference_id as string, parent_id: topReq.id }
              : item
          )
        }
      }
      return Promise.resolve(makeAxiosResponse({}))
    })

    renderRequirementsSetEdit(documentId)

    expect(await screen.findByText(/Hierarchy mismatch\./i)).toBeInTheDocument()

    const referenceInput = screen.getByDisplayValue('3.2.5.3')
    fireEvent.change(referenceInput, { target: { value: '3.2.1' } })
    fireEvent.blur(referenceInput)

    await waitFor(() => {
      expect(vi.mocked(api.put)).toHaveBeenCalledWith(`/requirements/${childReq.id}`, {
        reference_id: '3.2.1',
        title: 'Child',
        text: '<p>Child text</p>',
        requirement_type: 'mandatory',
      })
    })
    await waitFor(() => {
      expect(screen.queryByText(/Hierarchy mismatch\./i)).not.toBeInTheDocument()
    })
  })

  it('renders deep outline nodes from numeric references even when stored parents are malformed', async () => {
    const documentId = 'doc-outline-hierarchy'
    const createdAt = new Date().toISOString()

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'outline.pdf',
      name: 'Outline Doc',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'draft',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      testing_frequency: null,
      archived_at: null,
      created_at: createdAt,
    }

    const makeRequirement = (options: {
      id: string
      referenceId: string
      sortOrder: number
      parentId?: string | null
      title?: string | null
      requirementType?: string
    }): RequirementWithStatus => {
      const {
        id,
        referenceId,
        sortOrder,
        parentId = null,
        title = null,
        requirementType = 'mandatory',
      } = options

      return {
        id,
        jurisdiction_id: 'jur-1',
        source_extraction_id: null,
        document_id: documentId,
        reference_id: referenceId,
        title,
        text: `<p>${referenceId}</p>`,
        requirement_type: requirementType,
        parent_id: parentId,
        default_owner_id: null,
        active: true,
        version: 1,
        sort_order: sortOrder,
        created_at: createdAt,
        current_status: null,
        assigned_to: null,
        status_history: [],
        evidence_counts: { notes: 0, files: 0, links: 0 },
      }
    }

    const requirements: RequirementWithStatus[] = [
      makeRequirement({
        id: 'req-34',
        referenceId: '3.4',
        sortOrder: 1,
        title: 'Payments',
        requirementType: 'informational',
      }),
      makeRequirement({
        id: 'req-342',
        referenceId: '3.4.2',
        sortOrder: 2,
        parentId: null,
        title: 'Deposits',
      }),
      ...Array.from({ length: 9 }, (_, index) =>
        makeRequirement({
          id: `req-342${index + 1}`,
          referenceId: `3.4.2.${index + 1}`,
          sortOrder: 3 + index,
          parentId: 'req-342',
        })
      ),
      makeRequirement({
        id: 'req-35',
        referenceId: '3.5',
        sortOrder: 20,
        title: 'Responsible gambling',
        requirementType: 'informational',
      }),
      makeRequirement({
        id: 'req-351',
        referenceId: '3.5.1',
        sortOrder: 21,
        parentId: null,
        title: 'General',
        requirementType: 'informational',
      }),
      makeRequirement({
        id: 'req-3511',
        referenceId: '3.5.1.1',
        sortOrder: 22,
        parentId: null,
      }),
      makeRequirement({
        id: 'req-3512',
        referenceId: '3.5.1.2',
        sortOrder: 23,
        parentId: 'req-351',
      }),
      makeRequirement({
        id: 'req-3513',
        referenceId: '3.5.1.3',
        sortOrder: 24,
        parentId: null,
      }),
      ...Array.from({ length: 6 }, (_, index) =>
        makeRequirement({
          id: `req-351${index + 4}`,
          referenceId: `3.5.1.${index + 4}`,
          sortOrder: 25 + index,
          parentId: 'req-35',
        })
      ),
    ]

    const summary: RequirementSetSummary = {
      document_id: documentId,
      filename: 'outline.pdf',
      name: 'Outline Doc',
      document_type: 'annex_b',
      document_status: 'draft',
      archived_at: null,
      requirements_total: requirements.length,
      requirements_active: requirements.length,
    }

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

      if (url.startsWith('/jurisdictions')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<unknown>>({
            items: [
              {
                id: 'jur-1',
                code: 'dk',
                name: 'Denmark',
                regulator_name: 'Example Authority',
                report_header_text: null,
                active: true,
                created_at: createdAt,
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

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: requirements,
            total: requirements.length,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    renderRequirementsSetEdit(documentId)

    await screen.findByDisplayValue('3.4.2.1')
    expect(screen.getByDisplayValue('3.4.2.9')).toBeInTheDocument()

    const getOutlineTexts = () =>
      screen
        .getAllByTestId('requirements-outline-row')
        .map((row) => (row.textContent || '').trim())

    const outlineTexts = getOutlineTexts()
    expect(outlineTexts.some((text) => text.startsWith('3.4.2.1'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.4.2.9'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.5.1.1'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.5.1.9'))).toBe(true)

    const sectionRow = screen
      .getAllByTestId('requirements-outline-row')
      .find((row) => (row.textContent || '').trim().startsWith('3.5.1 '))
    expect(sectionRow).toBeTruthy()

    const collapseButton = within(sectionRow!.parentElement as HTMLElement).getByRole('button', {
      name: /collapse/i,
    })
    fireEvent.click(collapseButton)

    const collapsedOutlineTexts = getOutlineTexts()
    expect(collapsedOutlineTexts.some((text) => text.startsWith('3.5.1.4'))).toBe(false)
    expect(collapsedOutlineTexts.some((text) => text.startsWith('3.5.1.9'))).toBe(false)
  })
})
