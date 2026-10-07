import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter, MemoryRouter, createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { AuthProvider } from '../contexts/AuthContext'
import { JurisdictionProvider, useJurisdiction } from '../contexts/JurisdictionContext'

// Mock the API client
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

vi.mock('../contexts/ToastContext', async () => {
  const actual = await vi.importActual<typeof import('../contexts/ToastContext')>(
    '../contexts/ToastContext'
  )
  return {
    ...actual,
    useToast: () => ({
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      dismiss: vi.fn(),
      toasts: [],
    }),
  }
})

import api from '../api/client'
import App from '../App'
import Login from '../pages/Login'
import Dashboard from '../pages/Dashboard'
import Reports from '../pages/Reports'

function makeAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {} as AxiosResponse<T>['headers'],
    config: {} as unknown as InternalAxiosRequestConfig,
  }
}

function neverResolve<T>(): Promise<T> {
  return new Promise<T>(() => {})
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

const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <JurisdictionProvider>{children}</JurisdictionProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('should render login form', () => {
    render(
      <TestWrapper>
        <Login />
      </TestWrapper>
    )
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('should have required fields', () => {
    render(
      <TestWrapper>
        <Login />
      </TestWrapper>
    )
    const emailInput = screen.getByLabelText(/email/i)
    const passwordInput = screen.getByLabelText(/^password$/i)

    expect(emailInput).toHaveAttribute('required')
    expect(passwordInput).toHaveAttribute('required')
  })

  it('should display title', () => {
    render(
      <TestWrapper>
        <Login />
      </TestWrapper>
    )
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('Dashboard Page', () => {
    beforeEach(() => {
      vi.clearAllMocks()
      window.localStorage.clear()
    })

    it('should show loading state initially', async () => {
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
            })
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
            })
          )
        }
        // Dashboard request stays pending
        return neverResolve<AxiosResponse<unknown>>()
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      await waitFor(() => {
        expect(screen.getByText(/loading/i)).toBeInTheDocument()
      })
    })

    it('should show core cards by default and reveal insights on toggle', async () => {
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
            })
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
            })
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
            })
          )
        }
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'My work' })).toBeInTheDocument()
        expect(screen.getByRole('heading', { name: 'Assigned work' })).toBeInTheDocument()
        expect(screen.queryByText(/snapshot trend/i)).not.toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Activity and reporting'))
      expect(screen.getByRole('heading', { name: 'Recent Activity' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'Open requirement' })).toHaveAttribute('href', '/requirements/req-1')

      const toggle = screen.getByRole('button', { name: /show additional data/i })
      fireEvent.click(toggle)

      expect(await screen.findByText(/snapshot trend/i)).toBeInTheDocument()
      expect(await screen.findByText(/status snapshot/i)).toBeInTheDocument()
      expect(screen.getAllByRole('heading', { name: 'Recent Activity' })).toHaveLength(1)
    })
  })

  describe('Reports Page', () => {
    beforeEach(() => {
      vi.clearAllMocks()
      vi.mocked(api.get).mockResolvedValue(makeAxiosResponse({ items: [], total: 0 }))
    })

  it('opens assessment reports without the generic compliance overview', () => {
    render(
      <TestWrapper>
        <Reports />
      </TestWrapper>
    )
    expect(screen.queryByRole('button', { name: /^compliance overview$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^assessment reports$/i })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /^requirement assessment$/i })).toBeVisible()
    expect(screen.getByRole('heading', { name: /^gap analysis$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^audit trail$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^change management$/i })).toBeInTheDocument()
  })

  it('requires an assessment for assessment exports while leaving audit export available', () => {
    render(
      <TestWrapper>
        <Reports />
      </TestWrapper>
    )
    expect(screen.getByRole('button', { name: /^download compliance summary \(pdf\)$/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /^audit trail$/i }))
    expect(screen.getByRole('button', { name: /^download$/i })).toBeEnabled()
  })

  it('should have date inputs for audit trail', () => {
    render(
      <TestWrapper>
        <Reports />
      </TestWrapper>
    )
    fireEvent.click(screen.getByRole('button', { name: /^audit trail$/i }))
    expect(screen.getByLabelText('Audit from date')).toBeVisible()
    expect(screen.getByLabelText('Audit to date')).toBeVisible()
  })
})

describe('Navigation', () => {
  it('should render protected route wrapper', () => {
    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/dashboard']}>
          <AuthProvider>
            <div data-testid="app">App Content</div>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )
    expect(screen.getByTestId('app')).toBeInTheDocument()
  })
})

describe('Routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('should render NotFound for /documents', async () => {
    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.includes('/auth/me')) {
        return Promise.resolve(
          makeAxiosResponse({
            id: 'u1',
            email: 'test@example.com',
            full_name: 'Test User',
            role: 'admin',
            active: true,
            created_at: new Date().toISOString(),
          })
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
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/documents']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /^Page not found$/i })
      ).toBeInTheDocument()
    })
  })

  it('opens market setup for the clicked jurisdiction rather than the current selection', async () => {
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
          })
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
                report_header_text: 'Custom report heading',
                pack_status: 'published',
                pack_version: '2026.1.0',
                parser_mode: 'dk_hybrid',
                supports_deterministic_import: true,
                coverage_notes: 'Production-ready Denmark pack',
                active: true,
                created_at: new Date().toISOString(),
              },
              { id: 'jur-2', code: 'fi', name: 'Finland', regulator_name: 'Finnish Authority', active: true, created_at: new Date().toISOString() },
            ],
            total: 2,
          })
        )
      }
      if (url === '/applications/market-profile') {
        return Promise.resolve(makeAxiosResponse({ jurisdiction_id: 'jur-2', code: 'fi', version: 'test-fi', revision: 0, status: 'draft', label: 'Finland checklist', authority: 'Finnish Authority', setup_questions: [], items: [], guidance: [], source_urls: [], checked_at: null }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/jurisdictions']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /jurisdictions/i })).toBeInTheDocument()
    })
    fireEvent.click((await screen.findAllByRole('button', { name: 'Market setup for Finland' }))[0])
    expect(await screen.findByRole('heading', { name: 'Market setup' })).toBeInTheDocument()
    expect(screen.getByText(/authority sources for Finland/)).toBeInTheDocument()
  })
})

describe('Dashboard queue routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(api.get).mockImplementation((value: unknown) => {
      const url = new URL(String(value), 'http://localhost')
      if (url.pathname === '/auth/me') return Promise.resolve(makeAxiosResponse({ id: 'user-1', role: 'contributor', active: true }))
      if (url.pathname === '/jurisdictions') return Promise.resolve(makeAxiosResponse({ items: [
        { id: 'dk', code: 'DK', name: 'Denmark', active: true },
        { id: 'fi', code: 'FI', name: 'Finland', active: true },
      ], total: 2 }))
      if (url.pathname === '/dashboard') {
        const page = Number(url.searchParams.get('work_page'))
        const size = Number(url.searchParams.get('work_page_size'))
        const market = url.searchParams.get('jurisdiction_id')
        const scope = url.searchParams.get('work_scope')
        const total = market === 'fi' ? 3 : 26
        const numbers = Array.from({ length: total }, (_, i) => i + 1).slice((page - 1) * size, page * size)
        return Promise.resolve(makeAxiosResponse({
          generated_at: '2026-10-02T10:00:00Z',
          kpis: { overall: { total, evidenced: 0, percentage: 0 }, mandatory: { total, evidenced: 0, percentage: 0 }, at_risk_count: 0, by_status: [] },
          my_work: {
            assigned_requirements: { total, items: numbers.map(number => ({ requirement_id: `req-${number}`, reference_id: `${market}-${scope}-requirement-${number}`, document_name: 'Controls', status: 'not_started' })) },
            assigned_review_items: { total, items: numbers.map(number => ({ cycle_id: 'cycle-1', cycle_name: 'Assessment', review_item_id: `review-${number}`, requirement_reference_id: `${market}-${scope}-assessment-${number}`, review_status: 'pending' })) },
          },
          review_cycles: { active: [] }, snapshots: [], recent_activity: [],
        }))
      }
      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })
  })

  function MarketSwitch() {
    const { setJurisdictionId } = useJurisdiction()
    return <button onClick={() => setJurisdictionId('fi')}>Switch to Finland</button>
  }
  function setup(initialEntry = '/') {
    const client = createTestQueryClient()
    const router = createMemoryRouter([{ path: '/', element: <QueryClientProvider client={client}><AuthProvider><JurisdictionProvider><MarketSwitch /><Dashboard /></JurisdictionProvider></AuthProvider></QueryClientProvider> }], { initialEntries: [initialEntry] })
    render(<RouterProvider router={router} />)
    return router
  }
  const requests = () => vi.mocked(api.get).mock.calls.map(([url]) => String(url)).filter(url => url.startsWith('/dashboard?')).map(url => new URL(url, 'http://localhost').searchParams)
  const expectRequest = (market: string, scope: string, page: string, size: string) => {
    const calls = requests()
    expect(calls[calls.length - 1]).toEqual(new URLSearchParams({ jurisdiction_id: market, work_scope: scope, work_page: page, work_page_size: size }))
  }

  it('loads server pages and restores queue, scope and rows through browser Back', async () => {
    const router = setup('/?keep=bookmark')
    expect(await screen.findByRole('link', { name: 'dk-unresolved-requirement-1' })).toBeInTheDocument()
    expectRequest('dk', 'unresolved', '1', '5')
    expect(screen.queryByRole('link', { name: 'dk-unresolved-requirement-6' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View all 26 in this queue' }))
    expect(await screen.findByRole('link', { name: 'dk-unresolved-requirement-20' })).toBeInTheDocument()
    expectRequest('dk', 'unresolved', '1', '20')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('link', { name: 'dk-unresolved-requirement-21' })).toBeInTheDocument()
    expectRequest('dk', 'unresolved', '2', '20')
    fireEvent.click(screen.getByRole('button', { name: 'Requirement assessments 26' }))
    expect(await screen.findByRole('link', { name: 'dk-unresolved-assessment-1' })).toBeInTheDocument()
    expect(new URLSearchParams(router.state.location.search).get('work_page')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'All assigned' }))
    expect(await screen.findByRole('link', { name: 'dk-all-assessment-1' })).toBeInTheDocument()
    expectRequest('dk', 'all', '1', '20')
    await act(async () => { await router.navigate(-1) })
    expect(await screen.findByRole('link', { name: 'dk-unresolved-assessment-1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Needs attention' })).toHaveAttribute('aria-pressed', 'true')
    await act(async () => { await router.navigate(-1) })
    expect(await screen.findByRole('link', { name: 'dk-unresolved-requirement-21' })).toBeInTheDocument()
    expect(screen.getByText('21–26 of 26')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Requirements 26' })).toHaveAttribute('aria-pressed', 'true')
    expect(new URLSearchParams(router.state.location.search).get('keep')).toBe('bookmark')
    router.dispose()
  })

  it('keeps the root URL unchanged when switching markets without pagination', async () => {
    const router = setup('/')
    expect(await screen.findByRole('link', { name: 'dk-unresolved-requirement-1' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Finland' }))
    expect(await screen.findByRole('link', { name: 'fi-unresolved-requirement-1' })).toBeInTheDocument()
    expectRequest('fi', 'unresolved', '1', '5')
    expect(router.state.location.pathname).toBe('/')
    expect(router.state.location.search).toBe('')
    router.dispose()
  })

  it('preserves a bookmarked page on initial load, then resets only pagination when switching markets', async () => {
    const router = setup('/?work_all=true&work_page=2&work_scope=all&work_mode=review_items&keep=bookmark')
    expect(await screen.findByRole('link', { name: 'dk-all-assessment-21' })).toBeInTheDocument()
    expectRequest('dk', 'all', '2', '20')
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Finland' }))
    expect(await screen.findByRole('link', { name: 'fi-all-assessment-1' })).toBeInTheDocument()
    expectRequest('fi', 'all', '1', '20')
    expect(requests().filter(params => params.get('jurisdiction_id') === 'fi').every(params => params.get('work_page') === '1')).toBe(true)
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({ work_all: 'true', work_page: '1', work_scope: 'all', work_mode: 'review_items', keep: 'bookmark' })
    expect(screen.getByRole('button', { name: 'Requirement assessments 3' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'All assigned' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('1–3 of 3')).toBeInTheDocument()
    router.dispose()
  })
})
