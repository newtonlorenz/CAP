import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { AuthProvider } from '../contexts/AuthContext'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import Dashboard from '../pages/Dashboard'
import MyWorkPanel from '../pages/dashboard/MyWorkPanel'
import RecentActivityFeed from '../pages/dashboard/RecentActivityFeed'

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

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
    toasts: [],
  }),
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

const DashboardWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <JurisdictionProvider>{children}</JurisdictionProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MyWorkPanel', () => {
  it('opens assigned work in its workflow with deadlines and context', () => {
    render(
      <MemoryRouter>
        <MyWorkPanel
          assignedRequirements={{
            total: 1,
            items: [
              {
                requirement_id: 'req-1',
                reference_id: 'REQ-1',
                title: 'Requirement item',
                document_name: 'Doc A',
                status: 'in_progress',
                last_changed_at: null,
              },
            ],
          }}
          assignedReviewItems={{
            total: 1,
            items: [
              {
                cycle_id: 'cycle-1',
                cycle_name: 'Cycle A',
                deadline: null,
                review_item_id: 'review-1',
                requirement_reference_id: 'REV-1',
                requirement_title: 'Review item',
                review_status: 'pending',
                project_id: 'project-1', project_name: 'Certification Q4',
                change_entry_id: 'change-1', change_title: 'Platform change',
              },
            ],
          }}
          assignedForms={{ total: 1, items: [{ case_id: 'case-1', name: 'Director form', status: 'active', owner_id: 'u1', due_date: '2026-10-15', application_id: 'application-1', application_name: 'Operating licence' }] }}
          authorityQueries={{ total: 1, items: [{ query_id: 'query-1', application_id: 'application-1', application_name: 'Operating licence', question: 'Provide director details', status: 'open', owner_id: 'u1', due_date: '2026-10-20' }] }}
          primaryMode="requirements"
        />
      </MemoryRouter>
    )

    expect(screen.getByText('REQ-1')).toBeInTheDocument()
    expect(screen.queryByText('REV-1')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /requirement assessments/i }))

    expect(screen.getByText('REV-1')).toBeInTheDocument()
    expect(screen.queryByText('REQ-1')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Certification Q4' })).toHaveAttribute('href', '/certification-projects?project=project-1')
    expect(screen.getByRole('link', { name: 'Platform change' })).toHaveAttribute('href', '/change-management?change=change-1&tab=changes')
    fireEvent.click(screen.getByRole('button', { name: /forms/i }))
    expect(screen.getByRole('link', { name: 'Director form' })).toHaveAttribute('href', '/licence-applications?application=application-1&case=case-1')
    expect(screen.getByText(/Due.*15/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /authority queries/i }))
    expect(screen.getByText('Provide director details')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Operating licence' })).toHaveAttribute('href', '/licence-applications?application=application-1#authority-queries')
  })
})

describe('Recent activity destinations', () => {
  it.each([
    ['application', '/licence-applications?application=record%2F1'],
    ['certification_project', '/certification-projects?project=record%2F1'],
    ['preparation_case', '/preparation?case=record%2F1'],
    ['requirement', '/requirements/record%2F1'],
    ['document', '/requirements/sets/record%2F1'],
    ['requirement_set', '/requirements/sets/record%2F1'],
    ['review_cycle', '/review-cycles/record%2F1'],
    ['review_package', '/review-cycles/record%2F1'],
  ])('opens %s in its existing workspace route', (entityType, href) => {
    render(<MemoryRouter basename="/cap" initialEntries={['/cap/']}><RecentActivityFeed items={[{
      id: 'activity-1', user_name: 'Contributor', action: 'update', entity_type: entityType,
      entity_id: 'record/1', timestamp: '2026-10-01T09:00:00Z', summary: 'Recent change',
    }]} /></MemoryRouter>)
    expect(screen.getByRole('link')).toHaveAttribute('href', `/cap${href}`)
    expect(screen.getByText('Recent change')).toBeInTheDocument()
  })

  it.each([
    ['review_item', 'update', 'child-1'],
    ['application_document', 'update', 'child-1'],
    ['requirement', 'delete', 'record-1'],
    ['application', 'application_deleted', 'record-1'],
    ['preparation_case', 'remove', 'record-1'],
    ['requirement', 'update', ''],
  ])('keeps %s %s readable without inventing an available destination', (entityType, action, entityId) => {
    render(<MemoryRouter><RecentActivityFeed items={[{
      id: 'activity-1', user_name: 'Contributor', action, entity_type: entityType,
      entity_id: entityId, timestamp: '2026-10-01T09:00:00Z', summary: 'Historic change',
    }]} /></MemoryRouter>)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Historic change')).toBeInTheDocument()
    expect(screen.getByText(action.replace(/_/g, ' '))).toBeInTheDocument()
  })
})

describe('Dashboard insights', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('expands and collapses additional data', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.includes('/auth/me')) {
        return Promise.resolve(
          makeAxiosResponse({
            id: 'u1',
            email: 'test@example.com',
            full_name: 'Test User',
            role: 'contributor',
            active: true,
            created_at: new Date().toISOString(),
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
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
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/dashboard')) {
        return Promise.resolve(
          makeAxiosResponse({
            generated_at: new Date().toISOString(),
            kpis: {
              overall: { total: 100, evidenced: 75, percentage: 75 },
              mandatory: { total: 50, evidenced: 40, percentage: 80 },
              at_risk_count: 3,
              by_status: [{ status: 'evidenced', total: 75, percentage_of_total: 75 }],
            },
            breakdowns: {
              by_document: [],
              by_document_type: [],
              by_requirement_type: [],
            },
            my_work: {
              assigned_requirements: { total: 0, by_status: [], items: [] },
              assigned_review_items: { total: 0, by_status: [], items: [] },
            },
            review_cycles: { active: [] },
            snapshots: [],
            recent_activity: [
              {
                id: 'audit-1',
                user_name: 'Test User',
                action: 'status_change',
                entity_type: 'requirement',
                entity_id: 'req-1',
                timestamp: new Date().toISOString(),
                summary: 'Status -> evidenced',
              },
            ],
            queues: null,
            data_quality: null,
          }),
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    render(
      <DashboardWrapper>
        <Dashboard />
      </DashboardWrapper>,
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /show additional data/i })).toBeInTheDocument()
    })

    expect(screen.getByRole('heading', { name: 'Recent Activity' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open requirement' })).toHaveAttribute('href', '/requirements/req-1')
    expect(screen.queryByText(/status snapshot/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /show additional data/i }))
    expect(await screen.findByText(/status snapshot/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /hide additional data/i }))
    await waitFor(() => {
      expect(screen.queryByText(/status snapshot/i)).not.toBeInTheDocument()
    })
  })

  it('renders next best actions for admin users', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.includes('/auth/me')) {
        return Promise.resolve(
          makeAxiosResponse({
            id: 'u1',
            email: 'admin@example.com',
            full_name: 'Admin User',
            role: 'admin',
            active: true,
            created_at: new Date().toISOString(),
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
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
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/program-workspace/summary')) {
        return Promise.resolve(
          makeAxiosResponse({
            generated_at: new Date().toISOString(),
            jurisdiction_id: 'jur-1',
            items: [],
            next_actions: [
              {
                id: 'p1:intake:baseline_configured',
                project_id: 'p1',
                stage: 'intake',
                priority: 'medium',
                title: 'Intake is blocked',
                summary: 'Select at least one approved requirement set before moving out of Intake.',
                cta_label: 'Configure baseline',
                cta_path: '/certification-projects?project=p1',
                role_scope: ['admin', 'manager'],
              },
            ],
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/dashboard')) {
        return Promise.resolve(
          makeAxiosResponse({
            generated_at: new Date().toISOString(),
            kpis: {
              overall: { total: 100, evidenced: 75, percentage: 75 },
              mandatory: { total: 50, evidenced: 40, percentage: 80 },
              at_risk_count: 3,
              by_status: [{ status: 'evidenced', total: 75, percentage_of_total: 75 }],
            },
            breakdowns: {
              by_document: [],
              by_document_type: [],
              by_requirement_type: [],
            },
            my_work: {
              assigned_requirements: { total: 0, by_status: [], items: [] },
              assigned_review_items: { total: 0, by_status: [], items: [] },
            },
            review_cycles: { active: [] },
            snapshots: [],
            recent_activity: [],
            queues: null,
            data_quality: null,
          }),
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    render(
      <DashboardWrapper>
        <Dashboard />
      </DashboardWrapper>,
    )

    await waitFor(() => {
      expect(screen.getByText(/next actions/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/intake is blocked/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /configure baseline/i })).toHaveAttribute(
      'href',
      '/certification-projects?project=p1'
    )
  })

  it('creates a snapshot through decision modal input', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.includes('/auth/me')) {
        return Promise.resolve(
          makeAxiosResponse({
            id: 'u1',
            email: 'admin@example.com',
            full_name: 'Admin User',
            role: 'admin',
            active: true,
            created_at: new Date().toISOString(),
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/jurisdictions')) {
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
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/program-workspace/summary')) {
        return Promise.resolve(
          makeAxiosResponse({
            generated_at: new Date().toISOString(),
            jurisdiction_id: 'jur-1',
            items: [],
            next_actions: [],
          }),
        )
      }
      if (typeof url === 'string' && url.includes('/dashboard')) {
        return Promise.resolve(
          makeAxiosResponse({
            generated_at: new Date().toISOString(),
            kpis: {
              overall: { total: 100, evidenced: 75, percentage: 75 },
              mandatory: { total: 50, evidenced: 40, percentage: 80 },
              at_risk_count: 3,
              by_status: [{ status: 'evidenced', total: 75, percentage_of_total: 75 }],
            },
            breakdowns: {
              by_document: [],
              by_document_type: [],
              by_requirement_type: [],
            },
            my_work: {
              assigned_requirements: { total: 0, by_status: [], items: [] },
              assigned_review_items: { total: 0, by_status: [], items: [] },
            },
            review_cycles: { active: [] },
            snapshots: [],
            recent_activity: [],
            queues: null,
            data_quality: null,
          }),
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))

    render(
      <DashboardWrapper>
        <Dashboard />
      </DashboardWrapper>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /show additional data/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create snapshot/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /create snapshot/i }))
    const dialog = await screen.findByRole('dialog', { name: /create snapshot/i })
    fireEvent.change(within(dialog).getByLabelText(/snapshot name/i), {
      target: { value: 'Q1 readiness snapshot' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /^create snapshot$/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/snapshots', {
        name: 'Q1 readiness snapshot',
        description: 'Created from dashboard',
      })
    })
  })
})


it('shows completion blockers and keeps full queue navigation inside My Work', () => {
  const onExpand = vi.fn()
  const onScopeChange = vi.fn()
  render(<MemoryRouter><MyWorkPanel
    assignedRequirements={{ total: 0, items: [] }}
    assignedReviewItems={{ total: 26, items: [{ cycle_id: 'cycle-1', cycle_name: 'Quarterly review', review_item_id: 'item-1', requirement_reference_id: 'CTRL-7', review_status: 'confirmed', action_reasons: ['Evidence is not complete'] }] }}
    primaryMode="review_items" scope="unresolved" onExpand={onExpand} onScopeChange={onScopeChange}
  /></MemoryRouter>)
  expect(screen.getByText('Evidence is not complete')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'CTRL-7' })).toHaveAttribute('href', '/review-cycles/cycle-1?mode=focus&item=item-1')
  expect(screen.getByRole('button', { name: 'Needs attention' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'View all 26 in this queue' }))
  expect(onExpand).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: 'All assigned' }))
  expect(onScopeChange).toHaveBeenCalledWith('all')
})

it('pages every assignment while preserving the selected personal queue', () => {
  const onPageChange = vi.fn()
  render(<MemoryRouter><MyWorkPanel assignedRequirements={{ total: 26, items: [] }} assignedReviewItems={{ total: 0, items: [] }} primaryMode="requirements" expanded page={2} pageSize={20} onPageChange={onPageChange} /></MemoryRouter>)
  expect(screen.getByText('21–26 of 26')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
  expect(onPageChange).toHaveBeenCalledWith(1)
})

it('opens a titled review comment at the assessment that needs attention', () => {
  render(<MemoryRouter basename="/cap" initialEntries={['/cap/']}><RecentActivityFeed items={[{
    id: 'activity-1', user_name: 'Contributor', action: 'create', entity_type: 'review_item_comment',
    entity_id: 'comment-1', timestamp: '2026-10-01T09:00:00Z', title: 'CTRL-7 · Player records',
    destination: '/review-cycles/cycle-1?mode=focus&item=item-1',
  }]} /></MemoryRouter>)
  expect(screen.getByRole('link')).toHaveTextContent('CTRL-7 · Player records')
  expect(screen.getByRole('link')).toHaveAttribute('href', '/cap/review-cycles/cycle-1?mode=focus&item=item-1')
})
