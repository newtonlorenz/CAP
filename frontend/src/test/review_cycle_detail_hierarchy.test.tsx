import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
    toasts: [],
  }),
}))

vi.mock('../components/ResizableSplitView', () => ({
  default: ({
    sidebar,
    main,
  }: {
    sidebar: ReactNode
    main: ReactNode
  }) => (
    <div>
      {sidebar}
      {main}
    </div>
  ),
}))

vi.mock('../components/ReviewCycleReportOptions', () => ({
  default: () => null,
}))

vi.mock('../components/ui/DecisionModal', () => ({
  default: () => null,
}))

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
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

const createdAt = '2026-03-20T10:00:00Z'

const makeReviewItem = (options: {
  id: string
  referenceId: string
  sortOrder: number
  parentId?: string | null
  title?: string | null
  requirementType?: string
}) => {
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
    review_cycle_id: 'review-1',
    requirement_id: `req-${id}`,
    review_status: requirementType === 'informational' ? 'confirmed' : 'pending',
    assigned_reviewer_id: null,
    responsible_user_id: null,
    reviewer_id: null,
    review_comment: null,
    review_evidence: null,
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
    created_at: createdAt,
    comments: [],
    evidence_files: [],
    requirement_current_status: 'not_started',
    requirement: {
      id: `req-${id}`,
      document_id: 'doc-1',
      reference_id: referenceId,
      title,
      text: `<p>${referenceId}</p>`,
      requirement_type: requirementType,
      parent_id: parentId,
      sort_order: sortOrder,
    },
  }
}

const cycle = {
  id: 'review-1',
  organization_id: 'org-1',
  jurisdiction_id: 'jur-1',
  certification_project_id: null,
  predecessor_cycle_id: null,
  cycle_type: 'operational',
  name: 'Deep hierarchy review',
  description: 'Regression case for malformed hierarchy',
  scope: 'documents',
  scope_filter: null,
  document_ids: ['doc-1'],
  baseline_versions: [],
  deadline: null,
  status: 'active',
  created_by: 'user-1',
  closed_at: null,
  closed_by: null,
  snapshot_id: null,
  created_at: createdAt,
  jira_integration_configured: false,
  progress: {
    total: 22,
    completed: 0,
    pending: 22,
  },
  items: [
    makeReviewItem({
      id: 'item-34',
      referenceId: '3.4',
      sortOrder: 1,
      title: 'Payments',
      requirementType: 'informational',
    }),
    makeReviewItem({
      id: 'item-342',
      referenceId: '3.4.2',
      sortOrder: 2,
      parentId: null,
      title: 'Deposits',
    }),
    ...Array.from({ length: 9 }, (_, index) =>
      makeReviewItem({
        id: `item-342${index + 1}`,
        referenceId: `3.4.2.${index + 1}`,
        sortOrder: 3 + index,
        parentId: 'req-item-342',
      })
    ),
    makeReviewItem({
      id: 'item-35',
      referenceId: '3.5',
      sortOrder: 20,
      title: 'Responsible gambling',
      requirementType: 'informational',
    }),
    makeReviewItem({
      id: 'item-351',
      referenceId: '3.5.1',
      sortOrder: 21,
      parentId: null,
      title: 'General',
      requirementType: 'informational',
    }),
    makeReviewItem({
      id: 'item-3511',
      referenceId: '3.5.1.1',
      sortOrder: 22,
      parentId: null,
    }),
    makeReviewItem({
      id: 'item-3512',
      referenceId: '3.5.1.2',
      sortOrder: 23,
      parentId: 'req-item-351',
    }),
    makeReviewItem({
      id: 'item-3513',
      referenceId: '3.5.1.3',
      sortOrder: 24,
      parentId: null,
    }),
    ...Array.from({ length: 6 }, (_, index) =>
      makeReviewItem({
        id: `item-351${index + 4}`,
        referenceId: `3.5.1.${index + 4}`,
        sortOrder: 25 + index,
        parentId: 'req-item-35',
      })
    ),
  ],
}

const renderPage = (reviewCycle = cycle, query = '') => {
  const queryClient = createTestQueryClient()

  vi.mocked(api.get).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

    if (url === '/review-cycles/review-1') {
      return Promise.resolve(makeAxiosResponse(reviewCycle))
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
              requirements_total: reviewCycle.items.length,
              requirements_active: reviewCycle.items.length,
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

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/review-cycles/review-1' + query]}>
        <Routes>
          <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const getOutlineTexts = () =>
  screen
    .getAllByTestId('requirements-outline-row')
    .map((row) => (row.textContent || '').trim())

const getOutlineRow = (referencePrefix: string) => {
  const row = screen
    .getAllByTestId('requirements-outline-row')
    .find((candidate) => ((candidate.textContent || '').trim().startsWith(referencePrefix)))
  expect(row).toBeTruthy()
  return row as HTMLElement
}

describe('ReviewCycleDetail hierarchy rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('limits document rows by depth and selects only visible rows for bulk actions', async () => {
    renderPage()
    await screen.findByText('Deep hierarchy review')
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '1' } })
    expect(document.getElementById('review-item-item-3421')).toBeNull()
    expect(screen.getByRole('checkbox', { name: 'Select visible' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '2' } })
    const visibleSelections = screen.getAllByRole('checkbox', { name: 'Select for bulk action' })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select visible' }))
    expect(screen.getByText(`${visibleSelections.length} selected of ${visibleSelections.length} visible`)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Bulk review status' }), { target: { value: 'confirmed' } })
    vi.mocked(api.patch).mockResolvedValue(makeAxiosResponse({ updated_count: visibleSelections.length, failed_count: 0 }))
    fireEvent.click(screen.getByRole('button', { name: 'Apply bulk action' }))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/review-cycles/review-1/items/bulk', expect.objectContaining({ item_ids: expect.any(Array) })))
    const call = vi.mocked(api.patch).mock.calls.find(([url]) => url === '/review-cycles/review-1/items/bulk')
    const ids = (call?.[1] as { item_ids: string[] }).item_ids
    expect(ids).not.toContain('item-3421')
    expect(ids).toHaveLength(visibleSelections.length)
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: 'all' } })
    expect(document.getElementById('review-item-item-3421')).not.toBeNull()
  })

  it('keeps original levels and the chosen preset across search, empty results and hidden headings', async () => {
    renderPage({ ...cycle, items: cycle.items.slice(0, 3) })
    await screen.findByText('Deep hierarchy review')
    const levels = screen.getByRole('combobox', { name: 'Show levels' })
    fireEvent.change(levels, { target: { value: '2' } })
    expect(within(screen.getByRole('region', { name: 'Requirements outline' })).getByRole('combobox', { name: 'Show levels' })).toBe(levels)
    fireEvent.change(screen.getByRole('textbox', { name: 'Search' }), { target: { value: '3.4.2.1' } })
    expect(levels).toHaveValue('2')
    expect(document.getElementById('review-item-item-3421')).toBeNull()
    expect(screen.getByRole('checkbox', { name: 'Select visible' })).toBeDisabled()
    expect(getOutlineTexts()).toContain('3.4 Payments')
    fireEvent.change(levels, { target: { value: '3' } })
    expect(document.getElementById('review-item-item-3421')).not.toBeNull()
    expect(screen.getAllByRole('checkbox', { name: 'Select for bulk action' })).toHaveLength(1)
    fireEvent.change(screen.getByRole('textbox', { name: 'Search' }), { target: { value: 'no matching requirement' } })
    expect(levels).toHaveValue('3')
    expect(screen.getByText('No requirements match these filters.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Search' }), { target: { value: '' } })
    expect(levels).toHaveValue('3')
    fireEvent.change(levels, { target: { value: '1' } })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Hide informational' }))
    expect(document.getElementById('review-item-item-342')).toBeNull()
    expect(screen.getByRole('checkbox', { name: 'Select visible' })).toBeDisabled()
    expect(levels).toHaveValue('1')
    fireEvent.change(levels, { target: { value: '2' } })
    expect(document.getElementById('review-item-item-342')).not.toBeNull()
    expect(document.getElementById('review-item-item-3421')).toBeNull()
  })

  it.each([
    '?q=Unique', '?owner=owner-leaf', '?reviewer=reviewer-leaf',
    '?review_status=pending', '?requirement_status=blocked', '?pending=1',
    '?no_evidence=1', '?attention=1', '?q=Unique&owner=owner-leaf&requirement_status=blocked',
  ])('combines %s with original explicit parent levels and excludes hidden matches from bulk', async (query) => {
    const root = makeReviewItem({ id: 'root', referenceId: 'ROOT', sortOrder: 1, title: 'Parent' })
    const branch = makeReviewItem({ id: 'branch', referenceId: 'BRANCH', sortOrder: 2, parentId: 'req-root', title: 'Branch' })
    const leaf = makeReviewItem({ id: 'leaf', referenceId: 'LEAF', sortOrder: 3, parentId: 'req-branch', title: 'Unique' })
    for (const item of [root, branch]) {
      Object.assign(item, { review_status: 'confirmed', requirement_current_status: 'evidenced', review_evidence: 'Evidence', reviewed_at: createdAt, reviewer_id: 'reviewer' })
    }
    Object.assign(leaf, { requirement_current_status: 'blocked', responsible_user_id: 'owner-leaf', assigned_reviewer_id: 'reviewer-leaf' })
    localStorage.setItem('cap:outline-levels', '2')
    renderPage({ ...cycle, items: [root, branch, leaf] }, query)
    await screen.findByText('Deep hierarchy review')
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('2')
    expect(document.getElementById('review-item-leaf')).toBeNull()
    expect(screen.getByRole('checkbox', { name: 'Select visible' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value: '3' } })
    expect(document.getElementById('review-item-leaf')).not.toBeNull()
    expect(screen.getAllByRole('checkbox', { name: 'Select for bulk action' })).toHaveLength(1)
  })

  it('keeps independent branches and expands skipped levels once when informational headings are hidden', async () => {
    const root = makeReviewItem({ id: 'a', referenceId: 'A', sortOrder: 1 })
    const hidden = makeReviewItem({ id: 'a-info', referenceId: 'B', sortOrder: 2, parentId: 'req-a', requirementType: 'informational' })
    const deep = makeReviewItem({ id: 'a-deep', referenceId: 'C', sortOrder: 3, parentId: 'req-a-info' })
    const otherRoot = makeReviewItem({ id: 'd-info', referenceId: 'D', sortOrder: 4, requirementType: 'informational' })
    const otherChild = makeReviewItem({ id: 'd-child', referenceId: 'E', sortOrder: 5, parentId: 'req-d-info' })
    localStorage.setItem('cap:outline-levels', '2')
    renderPage({ ...cycle, items: [root, hidden, deep, otherRoot, otherChild] }, '?hide_info=1')
    await screen.findByText('Deep hierarchy review')
    const outline = screen.getByRole('region', { name: 'Requirements outline' })
    expect(within(outline).getByRole('button', { name: 'Expand A' })).toHaveAttribute('aria-expanded', 'false')
    expect(within(outline).queryByRole('button', { name: 'C' })).not.toBeInTheDocument()
    expect(within(outline).getByRole('button', { name: 'E' })).toBeInTheDocument()
    fireEvent.click(within(outline).getByRole('button', { name: 'Expand A' }))
    expect(within(outline).getByRole('button', { name: 'C' })).toBeInTheDocument()
    fireEvent.click(within(outline).getByRole('button', { name: 'Collapse A' }))
    expect(within(outline).queryByRole('button', { name: 'C' })).not.toBeInTheDocument()
    expect(within(outline).getByRole('button', { name: 'E' })).toBeInTheDocument()
    expect(document.getElementById('review-item-a-deep')).toBeNull()
    expect(document.getElementById('review-item-d-child')).not.toBeNull()
  })

  it('shows deep numeric descendants in the outline and nests malformed 3.5.1 children under 3.5.1', async () => {
    renderPage()

    await screen.findByText('Deep hierarchy review')
    await waitFor(() => {
      expect(document.getElementById('review-item-item-3421')).not.toBeNull()
      expect(document.getElementById('review-item-item-3429')).not.toBeNull()
    })

    const outlineTexts = getOutlineTexts()
    expect(outlineTexts.some((text) => text.startsWith('3.4.2.1'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.4.2.9'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.5.1.1'))).toBe(true)
    expect(outlineTexts.some((text) => text.startsWith('3.5.1.9'))).toBe(true)

    const sectionRow = getOutlineRow('3.5.1')
    const collapseButton = within(sectionRow.parentElement as HTMLElement).getByRole('button', {
      name: /collapse/i,
    })
    fireEvent.click(collapseButton)

    const collapsedOutlineTexts = getOutlineTexts()
    expect(collapsedOutlineTexts.some((text) => text.startsWith('3.5.1.4'))).toBe(false)
    expect(collapsedOutlineTexts.some((text) => text.startsWith('3.5.1.9'))).toBe(false)
  })
})
