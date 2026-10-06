import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { Document, ExtractedRequirement, ExtractionRun, PaginatedResponse } from '../types'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import RequirementsSetImport from '../pages/RequirementsSetImport'

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

function renderPage(documentId: string) {
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/import`]}>
        <JurisdictionProvider>
          <Routes>
            <Route
              path="/requirements/sets/:documentId/import"
              element={<RequirementsSetImport />}
            />
          </Routes>
        </JurisdictionProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RequirementsSetImport bulk triage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('keeps QA locked until metadata is complete', async () => {
    const documentId = 'doc-metadata-incomplete'
    const createdAt = new Date().toISOString()
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'imported.pdf',
      name: null,
      document_type: 'standard',
      version: null,
      effective_date: null,
      status: 'extracted',
      uploaded_by: 'u1',
      approval_comment: null,
      approved_by: null,
      current_extraction_id: null,
      current_extraction: null,
      maintenance_plan_id: null,
      cadence_interval_days: null,
      testing_frequency: null,
      archived_at: null,
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
      if (url === `/documents/${documentId}`) return Promise.resolve(makeAxiosResponse(doc))
      if (url === `/documents/${documentId}/extraction-runs`) {
        return Promise.resolve(makeAxiosResponse<PaginatedResponse<ExtractionRun>>({ items: [], total: 0 }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    renderPage(documentId)
    expect(await screen.findByText('imported.pdf')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Extraction QA/ })).toBeDisabled()
  })

  it('previews and applies bulk triage actions, then supports session undo', async () => {
    const documentId = 'doc-bulk'
    const runId = 'run-bulk'
    const createdAt = new Date().toISOString()
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'imported.pdf',
      name: 'Bulk Set',
      document_type: 'standard',
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
    const run: ExtractionRun = {
      id: runId,
      document_id: documentId,
      status: 'completed',
      total_pages: 4,
      current_page: 4,
      requirements_found: 1,
      started_at: createdAt,
      completed_at: createdAt,
      error_message: null,
      error_page: null,
      ai_provider: 'openai',
      ai_model: 'gpt-5-mini',
      created_at: createdAt,
    }
    const extraction: ExtractedRequirement = {
      id: 'ext-1',
      document_id: documentId,
      reference_id: '3.2.1',
      title: 'Customer registration',
      text: 'The gambling system shall collect and store customer details.',
      original_text: 'The gambling system shall collect and store customer details.',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 12,
      confidence_score: 0.62,
      status: 'pending',
      needs_review: true,
      review_reason: 'anchor_mismatch',
      source_excerpt: 'The gambling system shall collect and store customer details.',
      parser_strategy: 'ai_chunked',
      sort_order: 0,
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
      if (url === `/documents/${documentId}`) return Promise.resolve(makeAxiosResponse(doc))
      if (url === `/documents/${documentId}/extraction-runs`) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<ExtractionRun>>({
            items: [run],
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

    vi.mocked(api.post).mockImplementation((url: unknown, data?: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
      if (url === `/documents/${documentId}/extractions/feedback-batch`) {
        const payload = data as { preview_only?: boolean }
        if (payload.preview_only) {
          return Promise.resolve(
            makeAxiosResponse({
              preview_only: true,
              matched_count: 1,
              affected_count: 0,
              affected_ids: [],
              affected_ids_truncated: false,
              failures: [],
              distributions: {
                by_review_reason: [{ key: 'anchor_mismatch', total: 1 }],
                by_requirement_type: [{ key: 'mandatory', total: 1 }],
                by_section_prefix: [{ key: '3', total: 1 }],
                by_confidence_band: [{ key: '0.50-0.74', total: 1 }],
              },
            })
          )
        }
        return Promise.resolve(
          makeAxiosResponse({
            preview_only: false,
            matched_count: 1,
            affected_count: 1,
            affected_ids: ['ext-1'],
            affected_ids_truncated: false,
            failures: [],
            distributions: {
              by_review_reason: [{ key: 'anchor_mismatch', total: 1 }],
              by_requirement_type: [{ key: 'mandatory', total: 1 }],
              by_section_prefix: [{ key: '3', total: 1 }],
              by_confidence_band: [{ key: '0.50-0.74', total: 1 }],
            },
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({}))
    })

    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))

    renderPage(documentId)

    fireEvent.click(await screen.findByText(/Quality summary and bulk actions/))
    expect(await screen.findByText('Bulk Triage')).toBeInTheDocument()
    expect(await screen.findByText('Review Queue')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preview/i })).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Preview/i }))

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        `/documents/${documentId}/extractions/feedback-batch`,
        expect.objectContaining({
          preview_only: true,
          run_id: runId,
          action: { type: 'accept' },
        })
      )
    })
    expect(await screen.findByText(/Matched: 1/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Apply$/i }))
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        `/documents/${documentId}/extractions/feedback-batch`,
        expect.objectContaining({
          preview_only: false,
          run_id: runId,
          action: { type: 'accept' },
        })
      )
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Undo last bulk action/i })).toBeEnabled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Undo last bulk action/i }))
    await waitFor(() => {
      expect(vi.mocked(api.put)).toHaveBeenCalledWith(
        `/documents/${documentId}/extractions/ext-1`,
        expect.objectContaining({
          requirement_type: 'mandatory',
          status: 'pending',
          needs_review: true,
          review_reason: 'anchor_mismatch',
        })
      )
    })
  })
})
