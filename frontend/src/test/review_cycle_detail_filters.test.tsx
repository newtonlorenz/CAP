import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { ReactNode } from 'react'

const authState = {
  role: 'admin' as 'admin' | 'contributor',
}

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'current-user',
      email: 'current@example.com',
      full_name: 'Current User',
      role: authState.role,
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
  default: ({ main }: { sidebar: ReactNode; main: ReactNode }) => <div>{main}</div>,
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

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

const createItem = ({
  id,
  referenceId,
  title,
  responsibleUserId,
  assignedReviewerId,
  sortOrder,
  parentId = null,
}: {
  id: string
  referenceId: string
  title: string
  responsibleUserId: string | null
  assignedReviewerId: string | null
  sortOrder: number
  parentId?: string | null
}) => ({
  id,
  review_cycle_id: 'review-1',
  requirement_id: `req-${id}`,
  review_status: 'pending',
  assigned_reviewer_id: assignedReviewerId,
  responsible_user_id: responsibleUserId,
  reviewer_id: null,
  review_comment: null,
  review_evidence: null as string | null,
  jira_issue_key: null,
  jira_issue_url: null,
  jira_status: null,
  jira_summary: null,
  jira_assignee: null,
  jira_priority: null,
  jira_updated_at: null,
  jira_synced_at: null,
  jira_sync_error: null,
  reviewed_at: null as string | null,
  created_at: '2026-03-20T10:00:00Z',
  comments: [],
  evidence_files: [],
  requirement_current_status: 'not_started',
  requirement: {
    id: `req-${id}`,
    document_id: 'doc-1',
    reference_id: referenceId,
    title,
    text: `<p>${title}</p>`,
    requirement_type: 'mandatory',
    parent_id: parentId,
    sort_order: sortOrder,
  },
})

const defaultCycle = {
  id: 'review-1',
  organization_id: 'org-1',
  jurisdiction_id: 'jur-1',
  certification_project_id: null,
  predecessor_cycle_id: null,
  cycle_type: 'operational',
  name: 'Quarterly Review',
  description: 'Assignment filter coverage',
  scope: 'documents',
  scope_filter: null,
  document_ids: ['doc-1'],
  baseline_versions: [],
  deadline: null,
  status: 'active',
  created_by: 'current-user',
  closed_at: null,
  closed_by: null,
  snapshot_id: null,
  created_at: '2026-03-20T10:00:00Z',
  jira_integration_configured: false,
  progress: {
    total: 4,
    completed: 0,
    pending: 4,
  },
  items: [
    createItem({
      id: 'item-1',
      referenceId: 'REQ-100',
      title: 'Alpha',
      responsibleUserId: 'responsible-1',
      assignedReviewerId: 'reviewer-1',
      sortOrder: 1,
    }),
    createItem({
      id: 'item-2',
      referenceId: 'REQ-200',
      title: 'Beta',
      responsibleUserId: 'responsible-2',
      assignedReviewerId: 'reviewer-1',
      sortOrder: 2,
    }),
    createItem({
      id: 'item-3',
      referenceId: 'REQ-300',
      title: 'Gamma',
      responsibleUserId: null,
      assignedReviewerId: 'reviewer-2',
      sortOrder: 3,
    }),
    createItem({
      id: 'item-4',
      referenceId: 'REQ-400',
      title: 'Delta',
      responsibleUserId: 'responsible-1',
      assignedReviewerId: null,
      sortOrder: 4,
    }),
  ],
}

const usersResponse = {
  items: [
    {
      id: 'responsible-1',
      email: 'responsible.one@example.com',
      full_name: 'Responsible One',
      role: 'manager',
      active: true,
      created_at: '2026-03-20T10:00:00Z',
    },
    {
      id: 'responsible-2',
      email: 'responsible.two@example.com',
      full_name: 'Responsible Two',
      role: 'contributor',
      active: true,
      created_at: '2026-03-20T10:00:00Z',
    },
    {
      id: 'reviewer-1',
      email: 'reviewer.one@example.com',
      full_name: 'Reviewer One',
      role: 'assigned_reviewer',
      active: true,
      created_at: '2026-03-20T10:00:00Z',
    },
    {
      id: 'reviewer-2',
      email: 'reviewer.two@example.com',
      full_name: 'Reviewer Two',
      role: 'assigned_reviewer',
      active: true,
      created_at: '2026-03-20T10:00:00Z',
    },
  ],
  total: 4,
}

const renderPage = (cycleData = defaultCycle, entry = '/review-cycles/review-1') => {
  vi.mocked(api.get).mockImplementation((url: unknown) => {
    if (typeof url !== 'string') return Promise.resolve(makeAxiosResponse({}))

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
              requirements_total: cycleData.items.length,
              requirements_active: cycleData.items.length,
              current_version_id: 'version-1',
              current_version_number: 1,
              current_version_status: 'approved',
            },
          ],
          total: 1,
        })
      )
    }

    if (url === '/users?limit=1000') {
      return Promise.resolve(makeAxiosResponse(usersResponse))
    }

    if (url === '/users/mentions?limit=1000') {
      return Promise.resolve(makeAxiosResponse(usersResponse))
    }

    return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
  })

  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const getFiltersSection = () => {
  const heading = screen.getByRole('heading', { name: 'Filters' })
  const section = heading.closest('section')
  expect(section).not.toBeNull()
  return section as HTMLElement
}

const expectVisibleRequirementHeadings = (expected: string[], hidden: string[]) => {
  for (const name of expected) {
    expect(screen.getByRole('heading', { name })).toBeInTheDocument()
  }
  for (const name of hidden) {
    expect(screen.queryByRole('heading', { name })).not.toBeInTheDocument()
  }
}

describe('ReviewCycleDetail assignment filters', () => {
  beforeEach(() => {
    authState.role = 'admin'
    vi.clearAllMocks()
    window.sessionStorage.clear()
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.delete).mockResolvedValue(makeAxiosResponse({}))
  })

  it('holds focused navigation after a failed save, then moves after retry', async () => {
    vi.mocked(api.put).mockRejectedValueOnce(new Error('Save unavailable'))
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=item-1')
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    fireEvent.change(screen.getByLabelText('Requirement status for REQ-100'), { target: { value: 'in_progress' } })
    await screen.findByText('Not saved')
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    expect(screen.getByRole('heading', { name: 'REQ-100 Alpha' })).toBeInTheDocument()
    expect(screen.getByText(/Save this requirement before moving/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry save' }))
    await screen.findByText('Saved')
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    expect(screen.getByRole('heading', { name: 'REQ-200 Beta' })).toBeInTheDocument()
    expect(window.sessionStorage.getItem('cap:review-focus:current-user:review-1')).toBe('item-2')
  })

  it('keeps a failed item visible when its draft no longer matches the pending filter', async () => {
    vi.mocked(api.put).mockRejectedValueOnce(new Error('Save unavailable'))
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=item-1&pending=1')
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    fireEvent.change(screen.getByLabelText('Reviewer decision for REQ-100'), { target: { value: 'confirmed' } })
    await screen.findByText('Not saved')
    expect(screen.getByRole('heading', { name: 'REQ-100 Alpha' })).toBeInTheDocument()
    expect(screen.getByLabelText('Reviewer decision for REQ-100')).toHaveValue('confirmed')
  })

  it('resumes the last focused item and reports an unavailable item', async () => {
    window.sessionStorage.setItem('cap:review-focus:current-user:review-1', 'item-3')
    const view = renderPage(defaultCycle, '/review-cycles/review-1?mode=focus')
    await screen.findByRole('heading', { name: 'REQ-300 Gamma' })
    view.unmount()
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=removed')
    await screen.findByText(/That requirement is unavailable in this view/)
    expect(screen.getByRole('heading', { name: 'REQ-100 Alpha' })).toBeInTheDocument()
  })

  it('does not restore another user’s focused item', async () => {
    window.sessionStorage.setItem('cap:review-focus:other-user:review-1', 'item-3')
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus')
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
  })

  it('moves to the next item with Alt+Right Arrow outside an editor', async () => {
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=item-1')
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    fireEvent.keyDown(window, { key: 'ArrowRight', altKey: true })
    expect(screen.getByRole('heading', { name: 'REQ-200 Beta' })).toBeInTheDocument()
  })

  it('renders clearly labeled responsible and reviewer filters for admin users', async () => {
    renderPage()

    await screen.findByText('Quarterly Review')

    const filtersSection = getFiltersSection()
    expect(within(filtersSection).getByLabelText('Responsible for Requirement')).toBeInTheDocument()
    expect(within(filtersSection).getByLabelText('Assigned Reviewer')).toBeInTheDocument()
  })

  it('filters items by assigned reviewer', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Assigned Reviewer'), {
      target: { value: 'reviewer-1' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(
        ['REQ-100 Alpha', 'REQ-200 Beta'],
        ['REQ-300 Gamma', 'REQ-400 Delta']
      )
    })
  })

  it('filters items by responsible for requirement', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Responsible for Requirement'), {
      target: { value: 'responsible-1' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(
        ['REQ-100 Alpha', 'REQ-400 Delta'],
        ['REQ-200 Beta', 'REQ-300 Gamma']
      )
    })
  })

  it('supports unassigned for both assignment filters', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Responsible for Requirement'), {
      target: { value: 'unassigned' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(
        ['REQ-300 Gamma'],
        ['REQ-100 Alpha', 'REQ-200 Beta', 'REQ-400 Delta']
      )
    })

    fireEvent.change(within(filtersSection).getByLabelText('Responsible for Requirement'), {
      target: { value: 'all' },
    })
    fireEvent.change(within(filtersSection).getByLabelText('Assigned Reviewer'), {
      target: { value: 'unassigned' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(
        ['REQ-400 Delta'],
        ['REQ-100 Alpha', 'REQ-200 Beta', 'REQ-300 Gamma']
      )
    })
  })

  it('combines responsible and assigned reviewer filters with AND semantics', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Responsible for Requirement'), {
      target: { value: 'responsible-1' },
    })
    fireEvent.change(within(filtersSection).getByLabelText('Assigned Reviewer'), {
      target: { value: 'reviewer-1' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(
        ['REQ-100 Alpha'],
        ['REQ-200 Beta', 'REQ-300 Gamma', 'REQ-400 Delta']
      )
    })
  })

  it('does not show assignment filters for non-admin non-manager users', async () => {
    authState.role = 'contributor'
    renderPage()

    await screen.findByText('Quarterly Review')

    const filtersSection = getFiltersSection()
    expect(
      within(filtersSection).queryByLabelText('Responsible for Requirement')
    ).not.toBeInTheDocument()
    expect(within(filtersSection).queryByLabelText('Assigned Reviewer')).not.toBeInTheDocument()
  })

  it('shows only directly matching children when responsible filter is active in a hierarchy', async () => {
    const hierarchicalCycle = {
      ...defaultCycle,
      items: [
        createItem({
          id: 'parent-item',
          referenceId: '1',
          title: 'Hierarchy Parent',
          responsibleUserId: 'responsible-2',
          assignedReviewerId: 'reviewer-1',
          sortOrder: 1,
        }),
        createItem({
          id: 'child-item',
          referenceId: '1.1',
          title: 'Hierarchy Child',
          responsibleUserId: 'responsible-1',
          assignedReviewerId: 'reviewer-2',
          sortOrder: 2,
          parentId: 'req-parent-item',
        }),
      ],
      progress: {
        total: 2,
        completed: 0,
        pending: 2,
      },
    }

    renderPage(hierarchicalCycle)

    await screen.findByRole('heading', { name: '1 Hierarchy Parent' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Responsible for Requirement'), {
      target: { value: 'responsible-1' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(['1.1 Hierarchy Child'], ['1 Hierarchy Parent'])
    })
  })

  it('shows only directly matching parents when assigned reviewer filter is active in a hierarchy', async () => {
    const hierarchicalCycle = {
      ...defaultCycle,
      items: [
        createItem({
          id: 'parent-item',
          referenceId: '1',
          title: 'Hierarchy Parent',
          responsibleUserId: 'responsible-2',
          assignedReviewerId: 'reviewer-1',
          sortOrder: 1,
        }),
        createItem({
          id: 'child-item',
          referenceId: '1.1',
          title: 'Hierarchy Child',
          responsibleUserId: 'responsible-1',
          assignedReviewerId: 'reviewer-2',
          sortOrder: 2,
          parentId: 'req-parent-item',
        }),
      ],
      progress: {
        total: 2,
        completed: 0,
        pending: 2,
      },
    }

    renderPage(hierarchicalCycle)

    await screen.findByRole('heading', { name: '1 Hierarchy Parent' })
    const filtersSection = getFiltersSection()

    fireEvent.change(within(filtersSection).getByLabelText('Assigned Reviewer'), {
      target: { value: 'reviewer-1' },
    })

    await waitFor(() => {
      expectVisibleRequirementHeadings(['1 Hierarchy Parent'], ['1.1 Hierarchy Child'])
    })
  })
})


describe('Review focus workspace', () => {
  beforeEach(() => {
    authState.role = 'admin'
    vi.clearAllMocks()
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('keeps the original document view and mounts only one editor in focus view', async () => {
    const items = Array.from({ length: 250 }, (_, index) => createItem({
      id: `scale-${index}`, referenceId: `3.${index + 1}`, title: `Control ${index + 1}`,
      responsibleUserId: null, assignedReviewerId: null, sortOrder: index,
    }))
    renderPage({ ...defaultCycle, items })
    await screen.findByText('Quarterly Review')
    expect(document.querySelectorAll('[id^="review-item-"]')).toHaveLength(250)
    fireEvent.click(screen.getByText('Focus on one requirement', { selector: 'button' }))
    expect(document.querySelectorAll('[id^="review-item-"]')).toHaveLength(1)
    expect(screen.getByRole('heading', { name: 'Quarterly Review', level: 1 })).toBeVisible()
    expect(screen.queryByRole('checkbox', { name: 'Select for bulk action' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Assessment and evidence for 3.1' })).toBeVisible()
    expect(screen.getByLabelText('Requirement status for 3.1')).toBeVisible()
    expect(screen.getByLabelText('Reviewer decision for 3.1')).toBeVisible()
    expect(screen.getByLabelText('Evidence for 3.1')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('heading', { name: '3.2 Control 2' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Assessment overview' }))
    expect(document.querySelectorAll('[id^="review-item-"]')).toHaveLength(250)
    expect(within(document.getElementById('review-item-scale-0')!).getByRole('checkbox', { name: 'Select for bulk action' })).toBeVisible()
  }, 20000)

  it('opens the selected requirement and assignment filter from the URL', async () => {
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=item-2&reviewer=reviewer-1')
    await screen.findByRole('heading', { name: 'REQ-200 Beta' })
    expect(document.querySelectorAll('[id^="review-item-"]')).toHaveLength(1)
    expect(screen.getByText('2 of 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('includes undecided not-applicable controls in pending work', async () => {
    const items = defaultCycle.items.map((item, index) => ({ ...item,
      requirement_current_status: index === 0 ? 'not_applicable' : 'not_started',
    }))
    renderPage({ ...defaultCycle, items })
    await screen.findByText('Quarterly Review')
    fireEvent.click(screen.getByRole('button', { name: 'Next needing attention' }))
    expect(screen.getByRole('heading', { name: 'REQ-100 Alpha' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'REQ-200 Beta' })).not.toBeInTheDocument()
  })

  it('keeps evidence drafts when moving between requirements without changing decisions', async () => {
    renderPage(defaultCycle, '/review-cycles/review-1?mode=focus&item=item-1')
    const evidence = await screen.findByLabelText('Evidence for REQ-100')
    fireEvent.change(evidence, { target: { value: 'Unfinished working note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    expect(screen.getByLabelText('Evidence for REQ-100')).toHaveValue('Unfinished working note')
    expect(api.put).not.toHaveBeenCalled()
  })
})


describe('Review triage controls', () => {
  beforeEach(() => { authState.role = 'admin'; vi.clearAllMocks() })
  it('toggles a shared My pending filter off and on', async () => {
    const cycle = { ...defaultCycle, items: defaultCycle.items.map((item, index) => ({ ...item, responsible_user_id: index === 0 ? 'current-user' : item.responsible_user_id })) }
    renderPage(cycle, '/review-cycles/review-1?pending=1&owner=current-user')
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    const toggle = screen.getByRole('button', { name: 'My pending' })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(toggle)
    await screen.findByRole('heading', { name: 'REQ-200 Beta' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(toggle)
    expect(screen.queryByRole('heading', { name: 'REQ-200 Beta' })).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Clear filters' })[0])
    expect(screen.getByRole('heading', { name: 'REQ-200 Beta' })).toBeVisible()
  })
  it('hides informational parents while retaining their children', async () => {
    const parent = { ...defaultCycle.items[0], requirement: { ...defaultCycle.items[0].requirement, requirement_type: 'informational' } }
    const child = { ...defaultCycle.items[1], requirement: { ...defaultCycle.items[1].requirement, parent_id: parent.requirement.id } }
    renderPage({ ...defaultCycle, items: [parent, child] })
    await screen.findByRole('heading', { name: 'REQ-100 Alpha' })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Hide informational' }))
    expect(screen.queryByRole('heading', { name: 'REQ-100 Alpha' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'REQ-200 Beta' })).toBeVisible()
    expect(screen.getByLabelText('Evidence for REQ-200')).toBeVisible()
  })
  it('keeps an evidenced and confirmed item out of Needs attention while allowing evidence filtering', async () => {
    const cycle = { ...defaultCycle, items: defaultCycle.items.map((item, index) => ({
      ...item,
      review_status: index === 0 ? 'pending' : 'confirmed',
      requirement_current_status: index === 0 ? 'not_started' : 'evidenced',
      review_evidence: index === 1 ? null : 'Recorded reference',
      reviewer_name: index === 1 ? 'Dev Admin' : null,
      reviewed_at: index === 1 ? '2026-03-23T10:00:00Z' : null,
      evidence_changed_since_review: index === 1,
    })), readiness: {
      can_close: false, total: 4, applicable: 4, ready: 3, not_applicable: 0, informational: 0, blocker_count: 1,
      blockers: [{ item_id: 'item-1', reference_id: 'REQ-100', reasons: ['Evidence is not complete'] }],
    } }
    renderPage(cycle)
    await screen.findByText('Quarterly Review')
    fireEvent.click(screen.getByRole('button', { name: 'Needs attention' }))
    expectVisibleRequirementHeadings(['REQ-100 Alpha'], ['REQ-200 Beta', 'REQ-300 Gamma'])
    fireEvent.click(screen.getByRole('button', { name: 'No evidence recorded' }))
    expectVisibleRequirementHeadings(['REQ-200 Beta'], ['REQ-100 Alpha', 'REQ-300 Gamma'])
    expect(screen.getByText('No evidence recorded in CAP')).toBeVisible()
    expect(screen.getByText('Evidence changed since the last review; the decision has not been updated.')).toBeVisible()
    expect(screen.getByText(/Last reviewed by Dev Admin:/)).toBeVisible()
  })
})
