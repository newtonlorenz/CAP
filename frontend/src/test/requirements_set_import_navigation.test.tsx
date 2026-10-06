import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

describe('RequirementsSetImport navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    vi.stubGlobal('EventSource', class { close = vi.fn(); onmessage = null; onerror = null })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows "Open Requirement Set" for a draft requirement set', async () => {
    const documentId = 'doc-1'
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'imported.pdf',
      name: 'Imported Draft',
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

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') {
        return Promise.resolve(makeAxiosResponse({}))
      }

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

      if (url === `/documents/${documentId}/extraction-runs`) {
        return Promise.resolve(
          makeAxiosResponse<PaginatedResponse<ExtractionRun>>({
            items: [],
            total: 0,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

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

    expect(await screen.findByText('Imported Draft')).toBeInTheDocument()
    expect(screen.getByTestId('import-stepper')).toBeInTheDocument()
    expect(screen.getByText('Metadata')).toBeInTheDocument()
    expect(screen.getByText('Extraction QA')).toBeInTheDocument()
    expect(screen.getByText('Approval')).toBeInTheDocument()
    const link = await screen.findByRole('link', { name: /open requirement set/i })
    expect(link).toHaveAttribute('href', `/requirements/sets/${documentId}`)
    const editLink = await screen.findByRole('link', { name: /edit requirement set/i })
    expect(editLink).toHaveAttribute('href', `/requirements/sets/${documentId}/edit`)
  })

  it('shows edit actions for extracted requirements before approval', async () => {
    const documentId = 'doc-extracted'
    const runId = 'run-1'
    const createdAt = new Date().toISOString()
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'imported.pdf',
      name: 'Imported Extracted',
      document_type: 'annex_a',
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
      total_pages: 10,
      current_page: 10,
      requirements_found: 1,
      started_at: createdAt,
      completed_at: createdAt,
      error_message: null,
      error_page: null,
      ai_provider: 'deterministic',
      ai_model: 'annex_a_v2',
      created_at: createdAt,
    }
    const extracted: ExtractedRequirement = {
      id: 'ext-1',
      document_id: documentId,
      reference_id: '1.1',
      title: 'Name and address',
      text: 'Enter full name',
      original_text: 'Enter full name',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 1,
      confidence_score: 1,
      status: 'pending',
      sort_order: 0,
      created_at: createdAt,
    }

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url !== 'string') {
        return Promise.resolve(makeAxiosResponse({}))
      }

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
            items: [extracted],
            total: 1,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

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

    expect(await screen.findByText('Imported Extracted')).toBeInTheDocument()
    expect(await screen.findAllByRole('button', { name: 'Edit' })).not.toHaveLength(0)
    expect(await screen.findAllByTestId('delete-extraction-ext-1')).not.toHaveLength(0)
    expect(await screen.findByTestId('drag-reorder-handle-ext-1')).toBeInTheDocument()
    expect(await screen.findByTestId('move-up-ext-1')).toBeDisabled()
    expect(await screen.findByTestId('move-down-ext-1')).toBeDisabled()
  })

  it('shows review queue and blocks submit when flagged extractions exist', async () => {
    const documentId = 'doc-review-queue'
    const runId = 'run-review'
    const createdAt = new Date().toISOString()
    const doc: Document = {
      id: documentId,
      jurisdiction_id: 'jur-1',
      filename: 'imported.pdf',
      name: 'Imported Review Queue',
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
      total_pages: 8,
      current_page: 8,
      requirements_found: 1,
      started_at: createdAt,
      completed_at: createdAt,
      error_message: null,
      error_page: null,
      ai_provider: 'openai',
      ai_model: 'gpt-5-mini',
      created_at: createdAt,
    }
    const extracted: ExtractedRequirement = {
      id: 'ext-flag',
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
      if (typeof url !== 'string') {
        return Promise.resolve(makeAxiosResponse({}))
      }

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
            items: [extracted],
            total: 1,
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

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

    expect(await screen.findByText('Review Queue')).toBeInTheDocument()
    expect(await screen.findByText(/1 extracted item\(s\) need review before submit\./i)).toBeInTheDocument()
    const submitButton = await screen.findByRole('button', { name: /Approval/ })
    expect(submitButton).toBeDisabled()
  })
  it('refreshes results when a fast worker completes between document polls', async () => {
    let completed = false
    const running = { id: 'run-fast', document_id: 'doc-fast', status: 'pending', requirements_found: 0 }
    const getDocument = () => ({ id: 'doc-fast', jurisdiction_id: 'jur-1', name: 'Fast import', filename: 'source.pdf', document_type: 'annex_b', testing_frequency: 'annually', status: completed ? 'extracted' : 'pending_extraction', current_extraction_id: 'run-fast', current_extraction: completed ? { ...running, status: 'completed', requirements_found: 1 } : running })
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url === '/documents/doc-fast') return makeAxiosResponse(getDocument())
      // The history response is deliberately stale. The document contains the latest run.
      if (url === '/documents/doc-fast/extraction-runs') return makeAxiosResponse({ items: [running], total: 1 })
      if (String(url).startsWith('/documents/doc-fast/extractions')) return makeAxiosResponse({ items: completed ? [{ id: 'ex-fast', reference_id: '1.1', text: 'Retain certification evidence.', title: 'Evidence control', requirement_type: 'mandatory', needs_review: false, status: 'extracted', confidence_score: 0.95, sort_order: 1 }] : [], total: completed ? 1 : 0 })
      return makeAxiosResponse({ items: [], total: 0 })
    })
    const client = createTestQueryClient()
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/requirements/sets/doc-fast/import']}><JurisdictionProvider><Routes><Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} /></Routes></JurisdictionProvider></MemoryRouter></QueryClientProvider>)
    await screen.findByText('Fast import')
    expect(screen.queryByRole('button', { name: 'Continue to approval' })).not.toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/documents/doc-fast/extractions')))
    completed = true
    await act(async () => { await client.invalidateQueries({ queryKey: ['document', 'doc-fast'] }) })
    expect(await screen.findByRole('button', { name: 'Continue to approval' })).toBeEnabled()
    expect(screen.getAllByText('Evidence control').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Continue to approval' }))
    expect(screen.getByRole('region', { name: 'Approval summary' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Submit for Approval' })).toBeEnabled()
  })

  it('explains an unavailable extraction provider without losing the uploaded source', async () => {
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url === '/documents/doc-provider') return makeAxiosResponse({ id: 'doc-provider', jurisdiction_id: 'jur-1', name: 'Saved PDF', filename: 'source.pdf', document_type: 'standard', testing_frequency: 'annually', status: 'uploaded', current_extraction: null, current_extraction_id: null })
      return makeAxiosResponse({ items: [], total: 0 })
    })
    vi.mocked(api.post).mockRejectedValueOnce({ isAxiosError: true, response: { data: { detail: 'No AI provider configured' } } })
    const client = createTestQueryClient()
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/requirements/sets/doc-provider/import']}><JurisdictionProvider><Routes><Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} /></Routes></JurisdictionProvider></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Extract Requirements' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your uploaded PDF is saved')
    expect(screen.getByText('Saved PDF')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Extract Requirements' })).toBeEnabled()
  })

})
