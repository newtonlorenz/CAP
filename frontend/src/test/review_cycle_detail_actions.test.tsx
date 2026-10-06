import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { ReactNode } from 'react'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'manager@example.com',
      full_name: 'Manager User',
      role: 'manager',
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

const toast = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  dismiss: vi.fn(),
  toasts: [],
}

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => toast,
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
  default: ({
    open,
    title,
    description,
    confirmLabel,
    onConfirm,
  }: {
    open: boolean
    title: string
    description?: string
    confirmLabel: string
    onConfirm: () => void
  }) =>
    open ? (
      <div>
        <div>{title}</div>
        <div>{description}</div>
        <button type="button" onClick={onConfirm}>
          {`Confirm ${confirmLabel}`}
        </button>
      </div>
    ) : null,
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

const makeCycle = (status: 'archived' | 'active') => ({
  id: 'review-1',
  organization_id: 'org-1',
  jurisdiction_id: 'jur-1',
  certification_project_id: null,
  predecessor_cycle_id: null,
  cycle_type: 'operational',
  name: 'Restore me',
  description: 'Archived review cycle',
  scope: 'all',
  scope_filter: null,
  document_ids: null,
  baseline_versions: [],
  deadline: null,
  status,
  created_by: 'user-1',
  closed_at: null,
  closed_by: null,
  snapshot_id: null,
  created_at: '2026-03-20T10:00:00Z',
  jira_integration_configured: false,
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
      created_at: '2026-03-20T10:00:00Z',
      comments: [],
      evidence_files: [],
      requirement_current_status: 'not_started',
      requirement: {
        id: 'req-1',
        document_id: 'doc-1',
        reference_id: 'REQ-1',
        title: 'Requirement 1',
        text: '<p>Requirement text</p>',
        requirement_type: 'mandatory',
        parent_id: null,
        sort_order: 1,
      },
    },
  ],
})

describe('ReviewCycleDetail comments and restore action', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    toast.success.mockReset()
    toast.error.mockReset()
    toast.info.mockReset()

    let cycleLoads = 0

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/review-cycles/review-1') {
        cycleLoads += 1
        return Promise.resolve(makeAxiosResponse(cycleLoads === 1 ? makeCycle('archived') : makeCycle('active')))
      }

      if (url.startsWith('/requirements/sets?')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }

      if (url === '/users/mentions?limit=1000') {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }

      throw new Error(`Unhandled GET ${url}`)
    })

    vi.mocked(api.post).mockImplementation((url: string) => {
      if (url === '/review-cycles/review-1/restore') {
        return Promise.resolve(makeAxiosResponse({}))
      }
      throw new Error(`Unhandled POST ${url}`)
    })
  })

  it('renders comment URLs as safe links while preserving mentions and plain text', async () => {
    const body = '@Manager User https://example.com/evidence?q=one&sort=asc#details.\n'
      + 'See (http://example.com/Policy_(2026)), www.example.com/docs!\n'
      + 'javascript:alert(1) <img src=x onerror=alert(1)> https://'
    const cycle = makeCycle('active')
    vi.mocked(api.get).mockImplementation((url: string) => Promise.resolve(makeAxiosResponse(
      url === '/review-cycles/review-1'
        ? { ...cycle, items: cycle.items.map(item => ({ ...item, comments: [{
          id: 'comment-1', author_name: 'Manager User', body,
          created_at: '2026-09-29T16:00:00Z', can_edit: true,
        }] })) }
        : { items: [], total: 0 }
    )))

    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={['/review-cycles/review-1']}>
          <Routes>
            <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    const firstLink = await screen.findByRole('link', {
      name: 'https://example.com/evidence?q=one&sort=asc#details',
    })
    const comment = firstLink.closest('p')!
    expect(comment.textContent).toBe(body)
    expect(within(comment).getByText('@Manager User')).toHaveClass('text-info')
    const links = within(comment).getAllByRole('link')
    expect(links.map(link => link.getAttribute('href'))).toEqual([
      'https://example.com/evidence?q=one&sort=asc#details',
      'http://example.com/Policy_(2026)',
      'https://www.example.com/docs',
    ])
    for (const link of links) {
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    }
    expect(within(comment).queryByRole('img')).not.toBeInTheDocument()
  })

  it('retains comment files after failure and clears them after a successful retry', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => Promise.resolve(makeAxiosResponse(
      url === '/review-cycles/review-1' ? makeCycle('active') : { items: [], total: 0 }
    )))
    vi.mocked(api.post).mockRejectedValueOnce(new Error('Upload failed'))
      .mockResolvedValueOnce(makeAxiosResponse({}))
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={['/review-cycles/review-1']}>
          <Routes>
            <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
    const comment = await screen.findByRole('textbox', { name: 'Comment on REQ-1' })
    const picker = screen.getByLabelText('Attach files to comment on REQ-1')
    fireEvent.change(comment, { target: { value: 'Keep this evidence' } })
    const retained = new File(['evidence'], 'evidence.pdf', { type: 'application/pdf' })
    const removed = new File(['note'], 'remove.txt', { type: 'text/plain' })
    fireEvent.change(picker, { target: { files: [retained, removed] } })
    fireEvent.click(screen.getByRole('button', { name: 'Remove attachment remove.txt' }))
    fireEvent.click(screen.getByRole('button', { name: 'Post Comment' }))
    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(comment).toHaveValue('Keep this evidence')
    expect(screen.getByText('evidence.pdf')).toBeInTheDocument()
    expect(screen.queryByText('remove.txt')).not.toBeInTheDocument()
    const [url, form] = vi.mocked(api.post).mock.calls[0]
    expect(url).toBe('/review-cycles/review-1/items/item-1/comments/attachments')
    expect((form as FormData).get('body')).toBe('Keep this evidence')
    expect((form as FormData).getAll('files')).toEqual([retained])
    fireEvent.click(screen.getByRole('button', { name: 'Post Comment' }))
    await waitFor(() => expect(comment).toHaveValue(''))
    expect(screen.queryByText('evidence.pdf')).not.toBeInTheDocument()
  })

  it('restores archived reviews and flips the action back to archive after refetch', async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={['/review-cycles/review-1']}>
          <Routes>
            <Route path="/review-cycles/:id" element={<ReviewCycleDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Assessment administration' }))
    const topAction = screen.getByRole('menuitem', { name: 'Unarchive assessment' })
    fireEvent.click(topAction)

    expect(screen.getByText('Unarchive assessment cycle')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm Unarchive' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/review-cycles/review-1/restore')
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Assessment administration' })).toBeInTheDocument()
    })
  })
})
