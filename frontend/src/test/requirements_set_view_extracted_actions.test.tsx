import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type {
  Document,
  ExtractedRequirement,
  PaginatedResponse,
  RequirementSetSummary,
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

describe('RequirementsSetView extracted actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.scrollIntoView = vi.fn()
    window.localStorage.clear()
  })

  it.each([false, true])('preserves extraction ordering with pagination: %s', async (largeSet) => {
    const documentId = 'doc-extracted-view'
    const runId = 'run-extracted-view'
    const createdAt = new Date().toISOString()

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Extracted Set',
      document_type: 'annex_b',
      version: null,
      effective_date: null,
      status: 'extracted',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: runId,
      current_extraction: null,
      maintenance_plan_id: null,
      cadence_interval_days: null,
      testing_frequency: 'quarterly',
      archived_at: null,
      created_at: createdAt,
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'source.pdf',
      name: 'Extracted Set',
      document_type: 'annex_b',
      version: null,
      testing_frequency: 'quarterly',
      document_status: 'extracted',
      archived_at: null,
      requirements_total: 2,
      requirements_active: 2,
      current_version_id: null,
      current_version_number: null,
      current_version_status: null,
    }

    const requirements: RequirementWithStatus[] = [
      {
        id: 'req-1',
        organization_id: 'org-1',
        jurisdiction_id: 'jur-1',
        source_extraction_id: 'ext-1',
        document_id: documentId,
        requirement_set_version_id: null,
        source_requirement_id: null,
        reference_id: '1.1',
        title: 'Flagged requirement',
        text: '<p>Flagged requirement text</p>',
        requirement_type: 'mandatory',
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
      },
      {
        id: 'req-2',
        organization_id: 'org-1',
        jurisdiction_id: 'jur-1',
        source_extraction_id: 'ext-2',
        document_id: documentId,
        requirement_set_version_id: null,
        source_requirement_id: null,
        reference_id: '1.2',
        title: 'Normal requirement',
        text: '<p>Normal requirement text</p>',
        requirement_type: 'mandatory',
        parent_id: null,
        default_owner_id: null,
        active: true,
        version: 1,
        sort_order: 2,
        created_at: createdAt,
        current_status: null,
        assigned_to: null,
        status_history: [],
        evidence_counts: { notes: 0, files: 0, links: 0 },
      },
    ]

    const extractions: ExtractedRequirement[] = [
      {
        id: 'ext-1',
        document_id: documentId,
        reference_id: '1.1',
        title: 'Flagged extraction',
        text: 'Flagged extraction text',
        original_text: 'Flagged extraction text',
        requirement_type: 'mandatory',
        parent_id: null,
        page_number: 2,
        confidence_score: 0.61,
        status: 'pending',
        needs_review: true,
        review_reason: 'anchor_mismatch',
        sort_order: 0,
        created_at: createdAt,
      },
      {
        id: 'ext-2',
        document_id: documentId,
        reference_id: '1.2',
        title: 'Normal extraction',
        text: 'Normal extraction text',
        original_text: 'Normal extraction text',
        requirement_type: 'mandatory',
        parent_id: null,
        page_number: 3,
        confidence_score: 0.92,
        status: 'pending',
        needs_review: false,
        sort_order: 1,
        created_at: createdAt,
      },
    ]

    if (largeSet) {
      for (let n = 3; n <= 26; n++) extractions.push({ ...extractions[1], id: `ext-${n}`, reference_id: `1.${n}`, text: `Section ${n}`, sort_order: n - 1 })
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

      if (url === `/requirements/sets/${documentId}/versions`) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<unknown>>({
            items: [],
            total: 0,
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

      if (url.startsWith(`/documents/${documentId}/extractions?`)) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<ExtractedRequirement>>({
            items: extractions,
            total: extractions.length,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.post).mockImplementation((url: unknown, payload: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
      if (url === `/documents/${documentId}/extractions/reorder`) {
        return Promise.resolve(
          makeAxiosResponse({
            updated_count: 2,
            ordered_ids: (payload as { ordered_ids: string[] }).ordered_ids,
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({}))
    })
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse(extractions[0]))

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

    expect(await screen.findByText('Extracted Set')).toBeInTheDocument()
    expect(await screen.findByText('Extracted Requirements')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Requirement library' }))
    expect(screen.queryByRole('button', { name: /Edit extracted requirement/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Extracted sections' }))
    expect((await screen.findAllByText('Flagged')).length).toBeGreaterThan(0)
    expect(
      await screen.findAllByRole('button', { name: /Edit extracted requirement/i })
    ).not.toHaveLength(0)
    expect(await screen.findAllByRole('button', { name: 'Delete' })).not.toHaveLength(0)
    if (largeSet) {
      expect(screen.getAllByRole('button', { name: /Edit extracted requirement/i })).toHaveLength(50)
      fireEvent.click(screen.getAllByRole('button', { name: 'Next page' })[0])
      expect(screen.getAllByRole('button', { name: /Edit extracted requirement/i })).toHaveLength(2)
      fireEvent.click(screen.getAllByRole('button', { name: 'Move up' })[0])
      await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/documents/${documentId}/extractions/reorder`, {
        run_id: runId,
        ordered_ids: [...Array.from({length: 24}, (_, i) => `ext-${i + 1}`), 'ext-26', 'ext-25'],
      }))
      return
    }
    const moveDownButtons = await screen.findAllByRole('button', { name: 'Move down' })
    expect(moveDownButtons.length).toBeGreaterThan(0)

    fireEvent.click(moveDownButtons[0] as HTMLElement)
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        `/documents/${documentId}/extractions/reorder`,
        {
          run_id: runId,
          ordered_ids: ['ext-2', 'ext-1'],
        }
      )
    })
  })
})
