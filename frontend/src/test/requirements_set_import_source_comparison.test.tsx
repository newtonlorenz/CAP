import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { Document, ExtractedRequirement, ExtractionRun, PaginatedResponse } from '../types'
import type { InstallationCapabilities } from '../hooks/useCapabilities'
import RequirementsSetImport from '../pages/RequirementsSetImport'

const testState = vi.hoisted(() => ({
  capabilities: vi.fn(() => undefined as InstallationCapabilities | undefined),
  jurisdictionCode: vi.fn(() => 'dk'),
}))

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u1', role: 'admin' } }) }))
vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'jur-1',
    jurisdictionById: { 'jur-1': { code: testState.jurisdictionCode(), name: 'Test' } },
    setJurisdictionId: vi.fn(),
  }),
}))
vi.mock('../hooks/useCapabilities', () => ({ useCapabilities: () => ({ data: testState.capabilities() }) }))
vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

import api from '../api/client'

function response<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config: {} as InternalAxiosRequestConfig }
}

const queryClient = () => new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
const capabilitiesWithStructure = (available = true): InstallationCapabilities => ({
  ai: { enabled: true, provider: 'openai', model: 'model', external_processing: true },
  pdf_structure: { engine: 'opendataloader', available, local_only: true },
  email: { enabled: false, mode: 'disabled' },
  ocr: { enabled: false, available: false },
  feedback: { enabled: false },
})

function renderExtractionScenario(documentType: string) {
  const documentId = 'structured-scenario'
  const createdAt = new Date().toISOString()
  const doc: Document = {
    id: documentId, jurisdiction_id: 'jur-1', filename: 'source.pdf', has_source: true,
    name: 'Scenario', document_type: documentType, version: null, effective_date: null,
    status: 'extracted', uploaded_by: 'u1', approval_comment: null, approved_by: null,
    current_extraction_id: 'run-1', current_extraction: null, maintenance_plan_id: null,
    cadence_interval_days: null, testing_frequency: 'quarterly', archived_at: null, created_at: createdAt,
  }
  const run: ExtractionRun = {
    id: 'run-1', document_id: documentId, status: 'completed', total_pages: 1, current_page: 1,
    requirements_found: 0, started_at: createdAt, completed_at: createdAt, error_message: null,
    error_page: null, ai_provider: 'local', ai_model: 'opendataloader_2.5.11', created_at: createdAt,
  }
  vi.mocked(api.get).mockImplementation((url: unknown) => {
    const path = typeof url === 'string' ? url : ''
    if (path === `/documents/${documentId}`) return Promise.resolve(response(doc))
    if (path === `/documents/${documentId}/extraction-runs`) {
      return Promise.resolve(response<PaginatedResponse<ExtractionRun>>({ items: [run], total: 1 }))
    }
    return Promise.resolve(response({ items: [], total: 0 }))
  })
  vi.mocked(api.post).mockResolvedValue(response({}))
  render(
    <QueryClientProvider client={queryClient()}>
      <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/import`]}>
        <Routes><Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
  return { documentId }
}

describe('RequirementsSetImport source comparison', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    testState.capabilities.mockReturnValue(undefined)
    testState.jurisdictionCode.mockReturnValue('dk')
    window.localStorage.clear()
  })

  it('marks changed wording and expands a safe original/current comparison', async () => {
    const documentId = 'source-comparison-doc'
    const createdAt = new Date().toISOString()
    const doc: Document = {
      id: documentId, jurisdiction_id: 'jur-1', filename: 'source.pdf', has_source: true, name: 'Source set',
      document_type: 'annex_b', version: null, effective_date: null, status: 'extracted', uploaded_by: 'u1',
      approval_comment: null, approved_by: null, current_extraction_id: 'run-1', current_extraction: null,
      maintenance_plan_id: null, cadence_interval_days: null, testing_frequency: 'quarterly',
      archived_at: null, created_at: createdAt,
    }
    const run: ExtractionRun = {
      id: 'run-1', document_id: documentId, status: 'completed', total_pages: 2, current_page: 2,
      requirements_found: 2, started_at: createdAt, completed_at: createdAt, error_message: null,
      error_page: null, ai_provider: '', ai_model: '', created_at: createdAt,
    }
    const rows: ExtractedRequirement[] = [
      {
        id: 'unchanged', document_id: documentId, reference_id: '1.1', title: 'Unchanged',
        text: 'Original unchanged wording', original_text: 'Original unchanged wording', requirement_type: 'mandatory',
        parent_id: null, page_number: 1, confidence_score: 0.9, status: 'pending', sort_order: 0, created_at: createdAt,
      },
      {
        id: 'changed', document_id: documentId, reference_id: '1.2', title: 'Changed',
        text: '<strong>Edited wording</strong><img src=x onerror=alert(1)>',
        original_text: '<strong>Original wording</strong><script>alert(1)</script>', requirement_type: 'mandatory',
        parent_id: null, page_number: 2, confidence_score: 0.9, status: 'pending', sort_order: 1, created_at: createdAt,
        source_excerpt: 'Nearby source context', parser_strategy: 'text_layout',
      },
    ]

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      const path = typeof url === 'string' ? url : ''
      if (path === `/documents/${documentId}`) return Promise.resolve(response(doc))
      if (path === `/documents/${documentId}/extraction-runs`) {
        return Promise.resolve(response<PaginatedResponse<ExtractionRun>>({ items: [run], total: 1 }))
      }
      if (path.startsWith(`/documents/${documentId}/extractions?`)) {
        return Promise.resolve(response<PaginatedResponse<ExtractedRequirement>>({ items: rows, total: rows.length }))
      }
      return Promise.resolve(response({ items: [], total: 0 }))
    })

    render(
      <QueryClientProvider client={queryClient()}>
        <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/import`]}>
          <Routes><Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    const table = await screen.findByTestId('document-extraction-results-table')
    const unchangedRow = within(table).getByText('1.1').closest('tr') as HTMLElement
    const changedRow = within(table).getByText('1.2').closest('tr') as HTMLElement
    expect(within(unchangedRow).queryByText('Modified')).not.toBeInTheDocument()
    expect(within(changedRow).getByText('Modified')).toBeInTheDocument()

    fireEvent.click(within(changedRow).getByRole('button', { name: 'Edit' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit extracted requirement' })
    fireEvent.click(within(dialog).getByText('Compare extracted and current wording'))

    expect(within(dialog).getByText('Original wording')).toBeInTheDocument()
    expect(within(dialog).getByText('Edited wording')).toBeInTheDocument()
    expect(within(dialog).getByText('Nearby source context')).toBeInTheDocument()
    expect(within(dialog).getByText('Source PDF, page 2')).toBeInTheDocument()
    expect(within(dialog).queryByText('alert(1)')).not.toBeInTheDocument()
    expect(dialog.querySelector('script')).toBeNull()
    expect(dialog.querySelector('img')).toBeNull()
  })

  it.each([null, 'legacy-placeholder.pdf'])('explains a missing PDF and prevents viewing or starting extraction when filename is %s', async (filename) => {
    const documentId = 'manual-set'
    const doc: Document = {
      id: documentId, jurisdiction_id: 'jur-1', filename, has_source: false,
      name: 'Manual set', document_type: 'manual', version: null, effective_date: null,
      status: 'uploaded', uploaded_by: 'u1', approval_comment: null, approved_by: null,
      current_extraction_id: null, current_extraction: null, maintenance_plan_id: null,
      cadence_interval_days: null, testing_frequency: 'quarterly', archived_at: null,
      created_at: new Date().toISOString(),
    }
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      const path = typeof url === 'string' ? url : ''
      if (path === `/documents/${documentId}`) return Promise.resolve(response(doc))
      return Promise.resolve(response({ items: [], total: 0 }))
    })

    render(
      <QueryClientProvider client={queryClient()}>
        <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/import`]}>
          <Routes><Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    expect(await screen.findAllByText('No PDF attached')).toHaveLength(2)
    expect(screen.getByRole('link', { name: 'Open draft editor' })).toHaveAttribute('href', `/requirements/sets/${documentId}/edit`)
    expect(screen.queryByRole('link', { name: 'View source PDF' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'No PDF attached' })).toBeDisabled()
  })

  it('skips external AI consent and request parameters for available local structured extraction', async () => {
    testState.capabilities.mockReturnValue(capabilitiesWithStructure())
    const { documentId } = renderExtractionScenario('standard')

    expect(await screen.findByText(/Local structured extraction · OpenDataLoader/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Allow document text/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Re-extract' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/documents/${documentId}/extract`, null, undefined))
  })

  it('requires named Jev consent for local extraction and preserves the local request when opted out', async () => {
    const capabilities = capabilitiesWithStructure()
    capabilities.ai = { enabled: false, provider: 'none', model: null, external_processing: false }
    capabilities.jev = { enabled: true, model: 'jev-1.13.0', external_processing: true, revision: 9 }
    testState.capabilities.mockReturnValue(capabilities)
    const { documentId } = renderExtractionScenario('standard')
    const consent = await screen.findByRole('checkbox', { name: 'Allow source text to be sent to Jev for this extraction check.' })
    const extract = screen.getByRole('button', { name: 'Re-extract' })
    expect(extract).toBeDisabled()
    fireEvent.click(consent)
    fireEvent.click(extract)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/documents/${documentId}/extract`, null, { params: { allow_external_ai: true, use_jev: true, jev_settings_revision: 9 } }))
    await waitFor(() => expect(extract).toBeEnabled())
    vi.mocked(api.post).mockClear()
    fireEvent.click(screen.getByRole('checkbox', { name: /Enhance the extracted draft with Jev/ }))
    expect(screen.queryByRole('checkbox', { name: 'Allow source text to be sent to Jev for this extraction check.' })).not.toBeInTheDocument()
    fireEvent.click(extract)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(`/documents/${documentId}/extract`, null, undefined))
  })

  it('disables structured extraction with an engine message when unavailable', async () => {
    testState.capabilities.mockReturnValue(capabilitiesWithStructure(false))
    renderExtractionScenario('standard')

    expect(await screen.findByText(/OpenDataLoader is unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'OpenDataLoader unavailable' })).toBeDisabled()
    expect(screen.queryByLabelText(/Allow document text/)).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('keeps external AI consent when the native pipeline uses AI', async () => {
    const capabilities = capabilitiesWithStructure()
    capabilities.pdf_structure!.engine = 'native'
    testState.capabilities.mockReturnValue(capabilities)
    renderExtractionScenario('annex_b')

    expect(await screen.findByLabelText(/Allow document text/)).toBeInTheDocument()
    expect(screen.queryByText(/Local structured extraction/)).not.toBeInTheDocument()
  })

  it('uses local structured extraction for an arbitrary category and jurisdiction', async () => {
    testState.jurisdictionCode.mockReturnValue('custom-area')
    testState.capabilities.mockReturnValue(capabilitiesWithStructure())
    renderExtractionScenario('Custom certification')

    expect(screen.queryByLabelText(/Allow document text/)).not.toBeInTheDocument()
    expect(await screen.findByText(/Local structured extraction/)).toBeInTheDocument()
  })
})
