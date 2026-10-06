import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import type {
  Document,
  PaginatedResponse,
  RequirementSetSummary,
  RequirementWithStatus,
} from '../types'

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

async function renderRequirementsSetEdit(documentId: string) {
  const RequirementsSetEdit = (await import('../pages/RequirementsSetEdit')).default
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/edit?mode=all`]}>
        <AuthProvider>
          <JurisdictionProvider>
            <Routes>
              <Route path="/requirements/sets/:documentId/edit" element={<RequirementsSetEdit />} />
            </Routes>
          </JurisdictionProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RequirementsSetEdit insert/delete', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('inserts a child (1.1) under parent (1) via Insert child', async () => {
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
      requirements_total: 1,
      requirements_active: 1,
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
            items: [parentReq],
            total: 1,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))

    await renderRequirementsSetEdit(documentId)

    await screen.findAllByDisplayValue('1')

    const insertSummaries = screen.getAllByLabelText(/insert requirement/i)
    fireEvent.click(insertSummaries[0])

    const details = insertSummaries[0].closest('details')
    expect(details).toBeTruthy()
    fireEvent.click(within(details as HTMLElement).getByText('Insert child'))

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        '/requirements',
        expect.objectContaining({
          document_id: documentId,
          parent_id: parentReq.id,
          reference_id: '1.1',
        })
      )
    })
  })

  it('deletes a requirement subtree via deactivate calls', async () => {
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

    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))

    await renderRequirementsSetEdit(documentId)

    await screen.findAllByDisplayValue('1.1')

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' })
    fireEvent.click(deleteButtons[0])
    const dialog = await screen.findByRole('dialog', { name: /delete requirement/i })
    fireEvent.click(within(dialog).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => {
      const putCalls = vi.mocked(api.put).mock.calls.map((call) => call[0])
      expect(putCalls).toContain(`/requirements/${childReq.id}/deactivate`)
      expect(putCalls).toContain(`/requirements/${parentReq.id}/deactivate`)
    })
  })

  it('waits for draft autosave before confirming an insertion', async () => {
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
      requirements_total: 1,
      requirements_active: 1,
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
      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: [parentReq],
            total: 1,
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))

    await renderRequirementsSetEdit(documentId)
    await screen.findAllByDisplayValue('1')

    fireEvent.change(screen.getByDisplayValue('Parent'), {
      target: { value: 'Parent (edited)' },
    })

    const insertSummaries = screen.getAllByLabelText(/insert requirement/i)
    fireEvent.click(insertSummaries[0])
    const details = insertSummaries[0].closest('details')
    expect(details).toBeTruthy()
    fireEvent.click(within(details as HTMLElement).getByText('Insert child'))

    expect(vi.mocked(api.post)).not.toHaveBeenCalledWith(
      '/requirements',
      expect.objectContaining({ reference_id: '1.1' })
    )

    const dialog = await screen.findByRole('dialog', { name: /unsaved changes detected/i })
    const continueInsert = within(dialog).getByRole('button', { name: /continue insert/i })
    expect(continueInsert).toBeDisabled()
    await waitFor(() => expect(continueInsert).toBeEnabled(), { timeout: 2000 })
    expect(vi.mocked(api.put)).toHaveBeenCalledWith('/requirements/r-parent', expect.objectContaining({ title: 'Parent (edited)' }))
    expect(screen.getByDisplayValue('Parent (edited)')).toBeInTheDocument()
    fireEvent.click(continueInsert)

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        '/requirements',
        expect.objectContaining({
          document_id: documentId,
          parent_id: parentReq.id,
          reference_id: '1.1',
        })
      )
    })
  })
})
