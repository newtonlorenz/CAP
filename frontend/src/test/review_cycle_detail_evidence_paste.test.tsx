import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { ReactNode } from 'react'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'admin@example.com',
      full_name: 'Admin User',
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

vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'jur-1',
    jurisdictionById: {},
    isLoading: false,
    setJurisdictionId: vi.fn(),
  }),
}))

const toastApi = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  dismiss: vi.fn(),
  toasts: [],
}

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => toastApi,
}))

vi.mock('../components/RequirementsOutline', () => ({
  default: () => null,
}))

vi.mock('../components/ResizableSplitView', () => ({
  default: ({ main }: { main: ReactNode }) => <div>{main}</div>,
}))

vi.mock('../components/ReviewCycleReportOptions', () => ({
  default: () => null,
}))

vi.mock('../components/ui/DecisionModal', () => ({
  default: () => null,
}))

vi.mock('../utils/reviewEvidence', async () => {
  const actual = await vi.importActual<typeof import('../utils/reviewEvidence')>(
    '../utils/reviewEvidence'
  )
  return {
    ...actual,
    extractClipboardImageFiles: vi.fn(),
    normalizeClipboardImageFile: vi.fn(),
  }
})

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
import ReviewCycleDetail from '../pages/ReviewCycleDetail'
import { extractClipboardImageFiles, normalizeClipboardImageFile } from '../utils/reviewEvidence'

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

function makeCycle(options?: {
  baselineVersions?: Array<Record<string, unknown>>
  evidenceFiles?: Array<Record<string, unknown>>
  requirementCurrentStatus?: string
  reviewEvidence?: string
  jiraIntegrationConfigured?: boolean
}) {
  const {
    baselineVersions = [],
    evidenceFiles = [],
    requirementCurrentStatus = 'not_started',
    reviewEvidence = '',
    jiraIntegrationConfigured = false,
  } = options || {}
  return {
    id: 'review-1',
    organization_id: 'org-1',
    jurisdiction_id: 'jur-1',
    certification_project_id: null,
    predecessor_cycle_id: null,
    cycle_type: 'operational',
    name: 'Quarterly Review',
    description: 'Quarterly review',
    scope: 'all',
    scope_filter: null,
    document_ids: null,
    baseline_versions: baselineVersions,
    deadline: null,
    status: 'active',
    created_by: 'user-1',
    closed_at: null,
    closed_by: null,
    snapshot_id: null,
    created_at: '2026-03-16T10:00:00Z',
    jira_integration_configured: jiraIntegrationConfigured,
    progress: {
      total: 1,
      completed: 0,
      pending: 1,
    },
    items: [
      {
        id: 'item-1',
        review_cycle_id: 'review-1',
        requirement_id: 'req-1',
        review_status: 'pending',
        assigned_reviewer_id: null,
        responsible_user_id: null,
        reviewer_id: null,
        review_comment: null,
        review_evidence: reviewEvidence,
        jira_issue_key: null,
        jira_issue_url: null,
        jira_status: null,
        jira_summary: null,
        jira_assignee: null,
        jira_priority: null,
        jira_updated_at: null,
        jira_synced_at: null,
        jira_sync_error: null,
        reviewed_at: null,
        created_at: '2026-03-16T10:00:00Z',
        comments: [],
        evidence_files: evidenceFiles,
        requirement_current_status: requirementCurrentStatus,
        requirement: {
          id: 'req-1',
          document_id: 'doc-1',
          reference_id: 'REQ-1',
          title: 'Paste screenshots',
          text: '<p>Requirement body</p>',
          requirement_type: 'mandatory',
          parent_id: null,
          sort_order: 1,
        },
      },
    ],
  }
}

function installMatchMediaMock() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: true,
      media: '(min-width: 1024px)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

function renderPage(cycle = makeCycle()) {
  const cycleData = cycle

  vi.mocked(api.get).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') {
      return Promise.resolve(makeAxiosResponse({}))
    }

    if (url.endsWith('/preview')) {
      return Promise.resolve(makeAxiosResponse(new Blob(['preview'], { type: 'image/png' })))
    }

    if (url === '/review-cycles/review-1') {
      return Promise.resolve(makeAxiosResponse(cycleData))
    }

    if (url.startsWith('/requirements/sets?')) {
      return Promise.resolve(
        makeAxiosResponse({
          items: [
            {
              document_id: 'doc-1',
              jurisdiction_id: 'jur-1',
              filename: 'source.pdf',
              name: 'Source document',
              document_type: 'scp',
              version: '1.0',
              testing_frequency: null,
              document_status: 'approved',
              archived_at: null,
              requirements_total: 1,
              requirements_active: 1,
              current_version_id: 'version-1',
              current_version_number: 1,
              current_version_status: 'approved',
            },
          ],
          total: 1,
        })
      )
    }

    if (url === '/users?limit=1000' || url === '/users/mentions?limit=1000') {
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    }

    return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
  })

  vi.mocked(api.put).mockImplementation((url: unknown, payload: unknown) => {
    if (
      url === '/review-cycles/review-1/items/item-1' &&
      payload &&
      typeof payload === 'object' &&
      cycleData.items[0]
    ) {
      const update = payload as Record<string, unknown>
      if (typeof update.review_status === 'string') {
        cycleData.items[0].review_status = update.review_status
      }
      if (typeof update.requirement_status === 'string') {
        cycleData.items[0].requirement_current_status = update.requirement_status
      }
      if ('review_evidence' in update) {
        cycleData.items[0].review_evidence =
          typeof update.review_evidence === 'string' ? update.review_evidence : ''
      }
    }

    return Promise.resolve(makeAxiosResponse({}))
  })

  const queryClient = createTestQueryClient()

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/review-cycles/review-1']}>
        <Routes>
          <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ReviewCycleDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    installMatchMediaMock()
    window.URL.createObjectURL = vi.fn(() => 'blob://preview')
    window.URL.revokeObjectURL = vi.fn()
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.delete).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(extractClipboardImageFiles).mockReturnValue([])
    vi.mocked(normalizeClipboardImageFile).mockImplementation(async (file) => file)
  })

  it('uploads multiple pasted screenshots from the paste zone', async () => {
    renderPage()

    const pasteZone = await screen.findByTestId('evidence-paste-zone-item-1')
    const firstImage = new File(['first'], 'clipboard-one.png', { type: 'image/png' })
    const secondImage = new File(['second'], 'clipboard-two.png', { type: 'image/png' })
    vi.mocked(extractClipboardImageFiles).mockReturnValue([firstImage, secondImage])
    vi.mocked(normalizeClipboardImageFile)
      .mockResolvedValueOnce(
        new File(['normalized-one'], 'screenshot-20260316-153045.png', {
          type: 'image/png',
        })
      )
      .mockResolvedValueOnce(
        new File(['normalized-two'], 'screenshot-20260316-153045-2.png', {
          type: 'image/png',
        })
      )

    fireEvent.paste(pasteZone, {
      clipboardData: {
        items: [
          { kind: 'file', type: 'image/png', getAsFile: () => firstImage },
          { kind: 'file', type: 'image/png', getAsFile: () => secondImage },
        ],
        files: [firstImage, secondImage],
        getData: vi.fn(() => ''),
      },
    })

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))

    const firstFormData = vi.mocked(api.post).mock.calls[0][1] as FormData
    const secondFormData = vi.mocked(api.post).mock.calls[1][1] as FormData
    const firstUploadedFile = firstFormData.get('file')
    const secondUploadedFile = secondFormData.get('file')

    expect(firstUploadedFile).toBeInstanceOf(File)
    expect(secondUploadedFile).toBeInstanceOf(File)
    expect((firstUploadedFile as File).name).toMatch(/^screenshot-\d{8}-\d{6}\.png$/)
    expect((secondUploadedFile as File).name).toMatch(/^screenshot-\d{8}-\d{6}-2\.png$/)
    expect((firstUploadedFile as File).type).toBe('image/png')
    expect((secondUploadedFile as File).type).toBe('image/png')
  })

  it('uploads pasted screenshots from the evidence textarea but ignores plain text paste', async () => {
    renderPage()

    const evidenceTextarea = await screen.findByRole('textbox', { name: 'Evidence for REQ-1' })
    const image = new File(['clipboard'], 'clipboard-image.png', { type: 'image/png' })
    vi.mocked(extractClipboardImageFiles)
      .mockReturnValueOnce([image])
      .mockReturnValueOnce([])
    vi.mocked(normalizeClipboardImageFile).mockResolvedValue(
      new File(['normalized'], 'screenshot-20260316-153045.png', {
        type: 'image/png',
      })
    )

    fireEvent.paste(evidenceTextarea, {
      clipboardData: {
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => image }],
        files: [image],
        getData: vi.fn(() => ''),
      },
    })

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))

    vi.mocked(api.post).mockClear()

    fireEvent.paste(evidenceTextarea, {
      clipboardData: {
        items: [],
        files: [],
        getData: vi.fn(() => 'plain text evidence'),
      },
    })

    await waitFor(() => expect(api.post).not.toHaveBeenCalled())
  })

  it('renders image thumbnails separately from other evidence files and deletes by id', async () => {
    renderPage(
      makeCycle({
        evidenceFiles: [
          {
            id: 'file-image',
            review_item_id: 'item-1',
            filename: 'evidence.png',
            description: null,
            uploaded_by: 'user-1',
            uploaded_at: '2026-03-16T10:00:00Z',
          },
          {
            id: 'file-doc',
            review_item_id: 'item-1',
            filename: 'notes.txt',
            description: null,
            uploaded_by: 'user-1',
            uploaded_at: '2026-03-16T10:00:00Z',
          },
        ],
      })
    )

    expect(await screen.findByAltText('evidence.png')).toBeInTheDocument()
    expect(screen.getByText('notes.txt')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Delete evidence.png' }))

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith(
        '/review-cycles/review-1/items/item-1/files/file-image'
      )
    )
  })

  it('keeps rationale and decision controls available for not-applicable items', async () => {
    renderPage()

    const statusSelect = await screen.findByTestId('requirement-status-select-item-1')
    expect(screen.getByRole('combobox', { name: 'Responsible owner for REQ-1' })).toBeInTheDocument()
    expect(screen.getByTestId('review-item-extra-fields-item-1')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: 'Evidence for REQ-1' }), {
      target: { value: 'Draft evidence reference' },
    })
    fireEvent.change(statusSelect, { target: { value: 'not_applicable' } })

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Responsible owner for REQ-1' })).toBeInTheDocument()
      expect(screen.getByTestId('review-item-extra-fields-item-1')).toBeInTheDocument()
      expect(screen.getAllByLabelText(/^Reviewer decision for /).length).toBeGreaterThan(0)
    })

    fireEvent.change(screen.getByTestId('requirement-status-select-item-1'), {
      target: { value: 'in_progress' },
    })

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Responsible owner for REQ-1' })).toBeInTheDocument()
      expect(screen.getByTestId('review-item-extra-fields-item-1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Draft evidence reference')).toBeInTheDocument()
    })
  })

  it('retains a not applicable draft for retry when its save fails', async () => {
    renderPage()

    const statusSelect = await screen.findByTestId('requirement-status-select-item-1')
    vi.mocked(api.put).mockRejectedValueOnce(new Error('Forbidden'))

    fireEvent.change(statusSelect, { target: { value: 'not_applicable' } })

    expect(screen.getByRole('combobox', { name: 'Responsible owner for REQ-1' })).toBeInTheDocument()
    expect(screen.getByTestId('review-item-extra-fields-item-1')).toBeInTheDocument()
      expect(screen.getAllByLabelText(/^Reviewer decision for /).length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Responsible owner for REQ-1' })).toBeInTheDocument()
      expect(screen.getByTestId('review-item-extra-fields-item-1')).toBeInTheDocument()
      expect(screen.getByTestId('requirement-status-select-item-1')).toHaveValue('not_applicable')
      expect(screen.getByRole('button', { name: 'Retry save' })).toBeInTheDocument()
    })
  })

  it('hides Jira controls when Jira integration is not configured', async () => {
    renderPage(makeCycle({ jiraIntegrationConfigured: false }))

    await screen.findByText('Quarterly Review')

    expect(screen.queryByRole('button', { name: 'Refresh Jira' })).not.toBeInTheDocument()
    expect(screen.queryByText('Jira Issue Key')).not.toBeInTheDocument()
  })

  it('shows Jira controls when Jira integration is configured', async () => {
    renderPage(makeCycle({ jiraIntegrationConfigured: true }))

    expect(await screen.findByRole('button', { name: 'Refresh Jira' })).toBeInTheDocument()
    expect(screen.getByText('Jira Issue Key')).toBeInTheDocument()
  })

  it('shows latest approved state without migration controls when the baseline is current', async () => {
    renderPage(
      makeCycle({
        baselineVersions: [
          {
            document_id: 'doc-1',
            requirement_set_version_id: 'version-1',
            version_number: 1,
            set_name: 'Source document',
            is_latest: true,
            latest_requirement_set_version_id: 'version-1',
            latest_version_number: 1,
          },
        ],
      })
    )

    expect(await screen.findByText('Locked requirement-set versions')).toBeInTheDocument()
    expect(screen.getByText('Latest approved')).toBeInTheDocument()
    expect(
      screen.getByText('This cycle already uses the latest approved requirement-set versions.')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Preview latest migration' })).not.toBeInTheDocument()
    expect(screen.queryByText('This cycle is using an older approved version.')).not.toBeInTheDocument()
  })

  it('shows locked vs latest requirement versions and renders the migration gap analysis', async () => {
    const longLockedText =
      'Locked requirement paragraph. '.repeat(24) + 'Locked requirement final sentence.'
    const longLatestText =
      'Latest approved requirement paragraph. '.repeat(24) +
      'Latest approved requirement final sentence.'

    vi.mocked(api.post).mockImplementation((url: unknown) => {
      if (url === '/review-cycles/review-1/baseline-migrations/preview') {
        return Promise.resolve(
          makeAxiosResponse({
            source_cycle_id: 'review-1',
            target_version_ids: ['version-2'],
            matched: [],
            changed: [
              {
                document_id: 'doc-1',
                set_name: 'Source document',
                reference_id: 'REQ-1',
                old_requirement_id: 'req-1',
                new_requirement_id: 'req-2',
                old_text: longLockedText,
                new_text: longLatestText,
              },
              {
                document_id: 'doc-1',
                set_name: 'Source document',
                reference_id: 'REQ-2',
                old_requirement_id: 'req-3',
                new_requirement_id: 'req-4',
                old_text: `${longLockedText} Second changed requirement locked text.`,
                new_text: `${longLatestText} Second changed requirement latest text.`,
              },
            ],
            added: [],
            removed: [],
          })
        )
      }

      return Promise.resolve(makeAxiosResponse({}))
    })

    renderPage(
      makeCycle({
        baselineVersions: [
          {
            document_id: 'doc-1',
            requirement_set_version_id: 'version-1',
            version_number: 1,
            set_name: 'Source document',
            is_latest: false,
            latest_requirement_set_version_id: 'version-2',
            latest_version_number: 2,
          },
        ],
      })
    )

    expect(await screen.findByText('Locked requirement-set versions')).toBeInTheDocument()
    expect(screen.getByText('Locked v1')).toBeInTheDocument()
    expect(screen.getByText('Latest approved v2 available')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Preview latest migration' }))

    expect(await screen.findByText('Gap analysis')).toBeInTheDocument()
    expect(screen.getByText('Changed: decide 2')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Unchanged requirements carry forward automatically. Choose how to handle each changed requirement. Both choices require a new review.'
      )
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset all to pending' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Carry forward all' })).toBeInTheDocument()
    expect(screen.getByText('Source document - REQ-1')).toBeInTheDocument()
    expect(screen.getByText('Source document - REQ-2')).toBeInTheDocument()
    expect(
      screen.getAllByText(
        'Start pending with no prior comments, files, Jira links, or requirement status. Review the new wording from scratch.'
      )
    ).toHaveLength(2)
    expect(
      screen.getAllByText(
        'Keep prior comments, files, Jira links, review assignments, and evidence. Start with no requirement status or review decision until reviewed again.'
      )
    ).toHaveLength(2)

    const resetPendingRadios = screen.getAllByRole('radio', { name: /Reset pending/i })
    const carryForwardRadios = screen.getAllByRole('radio', { name: /Carry forward/i })
    expect(resetPendingRadios).toHaveLength(2)
    expect(carryForwardRadios).toHaveLength(2)
    resetPendingRadios.forEach((radio) => expect(radio).not.toBeChecked())
    carryForwardRadios.forEach((radio) => expect(radio).not.toBeChecked())
    expect(screen.getByRole('button', { name: 'Migrate to latest requirements' })).toBeDisabled()
    expect(screen.getByText(/2 decisions needed/)).toBeInTheDocument()

    const showFullTextButtons = screen.getAllByRole('button', { name: 'Show full text' })
    expect(showFullTextButtons).toHaveLength(4)
    expect(showFullTextButtons[0]).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(showFullTextButtons[0])

    expect(screen.getAllByRole('button', { name: 'Show less' }).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'Carry forward all' }))

    await waitFor(() => {
      carryForwardRadios.forEach((radio) => expect(radio).toBeChecked())
    })
    expect(screen.getByRole('button', { name: 'Migrate to latest requirements' })).toBeEnabled()

    fireEvent.click(resetPendingRadios[0])

    await waitFor(() => {
      expect(resetPendingRadios[0]).toBeChecked()
      expect(carryForwardRadios[1]).toBeChecked()
    })
    expect(screen.getByText(/1 changed carry forward for re-review; 1 changed reset/)).toBeInTheDocument()
  })

  it('shows a neutral baseline state when latest-version metadata is missing', async () => {
    renderPage(
      makeCycle({
        baselineVersions: [
          {
            document_id: 'doc-1',
            requirement_set_version_id: 'version-1',
            version_number: 1,
            set_name: 'Source document',
          },
        ],
      })
    )

    expect(await screen.findByText('Locked requirement-set versions')).toBeInTheDocument()
    expect(screen.getByText('Latest status unavailable')).toBeInTheDocument()
    expect(
      screen.getByText('Latest approved baseline status is unavailable for 1 requirement set.')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Preview latest migration' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Latest approved v\?/)).not.toBeInTheDocument()
    expect(screen.queryByText('This cycle is using an older approved version.')).not.toBeInTheDocument()
  })
})
