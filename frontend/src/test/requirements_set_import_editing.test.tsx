import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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

type ImportFixture = {
  documentId: string
  runId: string
  doc: Document
  run: ExtractionRun
  extractions: ExtractedRequirement[]
}

const setupImportFixture = (): ImportFixture => {
  const documentId = 'doc-import-editing'
  const runId = 'run-import-editing'
  const createdAt = new Date().toISOString()
  const doc: Document = {
    id: documentId,
    jurisdiction_id: 'jur-1',
    filename: 'fixture.pdf',
    name: 'Fixture Set',
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
  const run: ExtractionRun = {
    id: runId,
    document_id: documentId,
    status: 'completed',
    total_pages: 10,
    current_page: 10,
    requirements_found: 3,
    started_at: createdAt,
    completed_at: createdAt,
    error_message: null,
    error_page: null,
    ai_provider: 'openai',
    ai_model: 'gpt-5-mini',
    created_at: createdAt,
  }

  const extractions: ExtractedRequirement[] = [
    {
      id: 'ext-1',
      document_id: documentId,
      reference_id: '1.1',
      title: 'Requirement A',
      text: 'Requirement text A',
      original_text: 'Requirement text A',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 1,
      confidence_score: 0.92,
      status: 'pending',
      sort_order: 0,
      created_at: createdAt,
    },
    {
      id: 'ext-2',
      document_id: documentId,
      reference_id: '1.2',
      title: 'Requirement B',
      text: 'Requirement text B',
      original_text: 'Requirement text B',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 2,
      confidence_score: 0.88,
      status: 'pending',
      sort_order: 1,
      created_at: createdAt,
    },
    {
      id: 'ext-3',
      document_id: documentId,
      reference_id: '1.3',
      title: 'Requirement C',
      text: 'Requirement text C',
      original_text: 'Requirement text C',
      requirement_type: 'mandatory',
      parent_id: null,
      page_number: 3,
      confidence_score: 0.81,
      status: 'pending',
      sort_order: 2,
      created_at: createdAt,
    },
  ]

  return {
    documentId,
    runId,
    doc,
    run,
    extractions,
  }
}

const renderImportPage = async (fixture: ImportFixture) => {
  const { documentId, run, doc } = fixture
  const queryClient = createTestQueryClient()

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
              created_at: doc.created_at,
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
      const ordered = [...fixture.extractions].sort((a, b) => a.sort_order - b.sort_order)
      return Promise.resolve(
        makeAxiosResponse<PaginatedResponse<ExtractedRequirement>>({
          items: ordered,
          total: ordered.length,
        })
      )
    }

    return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
  })

  vi.mocked(api.put).mockImplementation((url: unknown, data: unknown) => {
    if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
    const match = url.match(/\/documents\/[^/]+\/extractions\/([^/]+)$/)
    if (!match) return Promise.resolve(makeAxiosResponse({}))

    const extractionId = match[1]
    const idx = fixture.extractions.findIndex((item) => item.id === extractionId)
    if (idx >= 0) {
      fixture.extractions[idx] = {
        ...fixture.extractions[idx],
        ...(data as Partial<ExtractedRequirement>),
      }
    }
    return Promise.resolve(makeAxiosResponse(fixture.extractions[idx]))
  })

  vi.mocked(api.post).mockImplementation((url: unknown, data: unknown) => {
    if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
    if (url === `/documents/${documentId}/extractions/reorder`) {
      const orderedIds = (data as { ordered_ids: string[] }).ordered_ids
      fixture.extractions = orderedIds.map((id, index) => {
        const current = fixture.extractions.find((item) => item.id === id)
        return {
          ...(current as ExtractedRequirement),
          sort_order: index,
        }
      })
      return Promise.resolve(
        makeAxiosResponse({
          updated_count: orderedIds.length,
          ordered_ids: orderedIds,
        })
      )
    }
    return Promise.resolve(makeAxiosResponse({}))
  })

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/requirements/sets/${documentId}/import`]}>
        <JurisdictionProvider>
          <Routes>
            <Route path="/requirements/sets/:documentId/import" element={<RequirementsSetImport />} />
          </Routes>
        </JurisdictionProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )

  await screen.findByText('Fixture Set')
  await screen.findByText('Showing 3 of 3 requirements')
}

describe('RequirementsSetImport editing behaviors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('shows a rejected structured row as a source-linked correction', async () => {
    const fixture = setupImportFixture()
    fixture.run.pipeline_version = 'opendataloader_v1'
    fixture.extractions[1] = {
      ...fixture.extractions[1],
      reference_id: 'unresolved-2',
      original_text: '1.2 Repeated source heading',
      source_excerpt: '1.2 Repeated source heading',
      needs_review: true,
      review_reason: 'Local draft extraction; duplicate_reference:1.2',
    }
    await renderImportPage(fixture)
    expect(await screen.findByRole('region', { name: 'Structured import recovery' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Source PDF, page 2' })).toHaveAttribute(
      'href', `/api/v1/documents/${fixture.documentId}/source#page=2`
    )
    fireEvent.click(screen.getByRole('button', { name: 'Resolve candidate' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Correct source reference' }), { target: { value: '1.4' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Immediate parent reference' }), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      `/requirements/sets/${fixture.documentId}/import-recovery/${fixture.extractions[1].id}`,
      expect.objectContaining({ action: 'correct', reference_id: '1.4', parent_reference: '1' })
    ))
  })

  it('routes a missing immediate parent to explicit recovery', async () => {
    const fixture = setupImportFixture()
    fixture.run.pipeline_version = 'opendataloader_v1'
    fixture.extractions[1] = {
      ...fixture.extractions[1],
      needs_review: true,
      review_reason: 'Missing immediate parent 1; repair the hierarchy before approval',
    }
    await renderImportPage(fixture)
    const panel = await screen.findByRole('region', { name: 'Structured import recovery' })
    expect(within(panel).getByText(/Missing immediate parent 1; repair/)).toBeInTheDocument()
  })

  it('keeps focus in extraction edit modal while typing', async () => {
    const fixture = setupImportFixture()
    await renderImportPage(fixture)

    fireEvent.click(screen.getAllByRole('button', { name: 'Edit' })[0] as HTMLElement)
    const dialog = await screen.findByRole('dialog', { name: 'Edit extracted requirement' })
    const closeButton = within(dialog).getByRole('button', { name: 'Close dialog' })
    await waitFor(() => {
      expect(closeButton).toHaveFocus()
    })

    const referenceInput = (await screen.findByDisplayValue('1.1')) as HTMLInputElement
    referenceInput.focus()
    fireEvent.change(referenceInput, { target: { value: '1.1-updated' } })
    expect(screen.getByDisplayValue('1.1-updated')).toHaveFocus()

    fireEvent.change(screen.getByDisplayValue('1.1-updated'), {
      target: { value: '1.1-updated-2' },
    })
    expect(screen.getByDisplayValue('1.1-updated-2')).toHaveFocus()
  })

  it('soft deletes extracted rows and hides rejected rows by default', async () => {
    const fixture = setupImportFixture()
    await renderImportPage(fixture)

    expect(screen.getAllByText('Requirement A').length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByTestId('delete-extraction-ext-1')[0] as HTMLElement)

    const deleteDialog = await screen.findByRole('dialog', { name: 'Delete extracted requirement' })
    fireEvent.click(within(deleteDialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(screen.queryAllByText('Requirement A')).toHaveLength(0)
    })
    expect(screen.getByText('1 rejected item(s) hidden from this view.')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('show-rejected-toggle'))
    expect((await screen.findAllByText('Requirement A')).length).toBeGreaterThan(0)
  })

  it('sends reorder payload when dropping a row in desktop table', async () => {
    const fixture = setupImportFixture()
    await renderImportPage(fixture)

    const table = await screen.findByTestId('document-extraction-results-table')
    const targetRow = within(table).getByText('Requirement B').closest('tr')
    expect(targetRow).toBeTruthy()

    fireEvent.drop(targetRow as HTMLElement, {
      dataTransfer: {
        getData: () => 'ext-1',
        setData: vi.fn(),
        dropEffect: 'move',
        effectAllowed: 'move',
      },
      clientY: 9999,
    })

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        `/documents/${fixture.documentId}/extractions/reorder`,
        {
          run_id: fixture.runId,
          ordered_ids: ['ext-2', 'ext-1', 'ext-3'],
        }
      )
    })
  })

  it('sends reorder payload when using mobile move controls', async () => {
    const fixture = setupImportFixture()
    await renderImportPage(fixture)

    fireEvent.click(await screen.findByTestId('move-down-ext-1'))

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        `/documents/${fixture.documentId}/extractions/reorder`,
        {
          run_id: fixture.runId,
          ordered_ids: ['ext-2', 'ext-1', 'ext-3'],
        }
      )
    })
  })

  it('shows a hierarchy mismatch warning and repairs the stored parent', async () => {
    const fixture = setupImportFixture()
    fixture.extractions = [
      {
        ...fixture.extractions[0],
        id: 'ext-1',
        reference_id: '3.2',
        title: 'Accounts',
        text: 'Accounts',
        original_text: 'Accounts',
        parent_id: null,
        sort_order: 0,
      },
      {
        ...fixture.extractions[1],
        id: 'ext-2',
        reference_id: '3.2.5',
        title: 'Player ID',
        text: 'Player ID',
        original_text: 'Player ID',
        parent_id: 'ext-1',
        sort_order: 1,
      },
      {
        ...fixture.extractions[2],
        id: 'ext-3',
        reference_id: '3.2.5.3',
        title: 'Child requirement',
        text: 'Child requirement',
        original_text: 'Child requirement',
        parent_id: 'ext-1',
        sort_order: 2,
      },
    ]

    await renderImportPage(fixture)

    vi.mocked(api.put).mockImplementation((url: unknown, data: unknown) => {
      if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))
      const match = url.match(/\/documents\/[^/]+\/extractions\/([^/]+)$/)
      if (!match) return Promise.resolve(makeAxiosResponse({}))

      const extractionId = match[1]
      const idx = fixture.extractions.findIndex((item) => item.id === extractionId)
      if (idx < 0) return Promise.resolve(makeAxiosResponse({}))

      const payload = data as Partial<ExtractedRequirement> & {
        sync_parent_from_reference?: boolean
      }
      fixture.extractions[idx] = payload.sync_parent_from_reference
        ? {
            ...fixture.extractions[idx],
            parent_id: 'ext-2',
          }
        : {
            ...fixture.extractions[idx],
            ...payload,
          }

      return Promise.resolve(makeAxiosResponse(fixture.extractions[idx]))
    })

    expect((await screen.findAllByText(/Hierarchy mismatch/i)).length).toBeGreaterThan(0)
    fireEvent.click((await screen.findAllByTestId('fix-extraction-hierarchy-ext-3'))[0] as HTMLElement)

    await waitFor(() => {
      expect(vi.mocked(api.put)).toHaveBeenCalledWith(
        `/documents/${fixture.documentId}/extractions/ext-3`,
        { sync_parent_from_reference: true }
      )
    })
    await waitFor(() => {
      expect(screen.queryAllByText(/Hierarchy mismatch/i)).toHaveLength(0)
    })
  })
})
