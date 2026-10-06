import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import type {
  Document,
  ExtractedRequirement,
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

describe('RequirementsSetEdit extraction flag visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('shows extraction flag badges in outline and field surfaces', async () => {
    const documentId = 'doc-flags'
    const extractionId = 'ext-flagged'
    const createdAt = new Date().toISOString()

    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'flagged.pdf',
      name: 'Flagged Set',
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
      created_at: createdAt,
    }

    const summary: RequirementSetSummary = {
      document_id: documentId,
      filename: 'flagged.pdf',
      name: 'Flagged Set',
      document_type: 'annex_b',
      document_status: 'draft',
      archived_at: null,
      requirements_total: 1,
      requirements_active: 1,
    }

    const requirement: RequirementWithStatus = {
      id: 'req-1',
      jurisdiction_id: 'jur-1',
      source_extraction_id: extractionId,
      document_id: documentId,
      reference_id: '2.4',
      title: 'Customer verification',
      text: '<p>Verify customer identity prior to activation.</p>',
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
    }

    const extraction: ExtractedRequirement = {
      id: extractionId,
      document_id: documentId,
      reference_id: '2.4',
      title: 'Customer verification',
      text: 'Verify customer identity prior to activation.',
      original_text: 'Verify customer identity prior to activation.',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 4,
      confidence_score: 0.72,
      status: 'pending',
      sort_order: 1,
      needs_review: true,
      review_reason: 'anchor_mismatch',
      created_at: createdAt,
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

      if (url.startsWith('/requirements?')) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<RequirementWithStatus>>({
            items: [requirement],
            total: 1,
          })
        )
      }

      if (url.startsWith(`/documents/${documentId}/extractions?`)) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<ExtractedRequirement>>({
            items: [extraction],
            total: 1,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))

    const RequirementsSetEdit = (await import('../pages/RequirementsSetEdit')).default
    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/edit`]}>
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

    await screen.findByText('Edit: Flagged Set')

    const outlineRows = await screen.findAllByTestId('requirements-outline-row')
    const flaggedOutlineRow = outlineRows.find(
      (node) => node.getAttribute('data-target-id') === 'req-req-1'
    )
    expect(flaggedOutlineRow).toBeTruthy()
    expect(within(flaggedOutlineRow as HTMLElement).getByText('Flagged')).toBeInTheDocument()

    expect(
      screen.getByText('Flagged from extraction review: anchor_mismatch')
    ).toBeInTheDocument()

    expect(screen.getByDisplayValue('2.4').className).toContain('border-warning-line')
    expect(screen.getByDisplayValue('Customer verification').className).toContain('border-warning-line')
  })
})
