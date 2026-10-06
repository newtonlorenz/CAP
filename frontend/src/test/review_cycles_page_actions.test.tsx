import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

const authState = {
  role: 'manager',
}

const toast = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  dismiss: vi.fn(),
  toasts: [],
}

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'manager@example.com',
      full_name: 'Manager User',
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
    jurisdictionById: {
      'jur-1': { id: 'jur-1', name: 'Denmark' },
    },
    isLoading: false,
    setJurisdictionId: vi.fn(),
  }),
}))

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => toast,
}))

vi.mock('../components/ui/DropdownMenu', () => ({
  default: ({
    items,
    ariaLabel,
  }: {
    items: Array<{
      key: string
      label: string
      onSelect: () => void
      disabled?: boolean
    }>
    ariaLabel: string
  }) => (
    <div aria-label={ariaLabel}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          disabled={item.disabled}
          onClick={(event) => {
            event.stopPropagation()
            item.onSelect()
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  ),
}))

vi.mock('../components/ui/DecisionModal', () => ({
  default: ({
    open,
    title,
    description,
    confirmLabel,
    dangerDetails,
    onConfirm,
  }: {
    open: boolean
    title: string
    description?: string
    confirmLabel: string
    dangerDetails?: string[]
    onConfirm: () => void
  }) =>
    open ? (
      <div>
        <div>{title}</div>
        <div>{description}</div>
        {dangerDetails?.map((detail) => <div key={detail}>{detail}</div>)}
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
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

import api from '../api/client'
import ReviewCycles from '../pages/ReviewCycles'

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

describe('ReviewCycles restore actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.role = 'manager'
    toast.success.mockReset()
    toast.error.mockReset()
    toast.info.mockReset()

    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.startsWith('/review-cycles?')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [
              {
                id: 'cycle-archived',
                jurisdiction_id: 'jur-1',
                cycle_type: 'operational',
                name: 'Archived cycle',
                description: null,
                scope: 'all',
                scope_filter: null,
                document_ids: null,
                baseline_versions: [],
                deadline: null,
                status: 'archived',
                created_by: 'user-1',
                closed_at: '2026-03-20T10:00:00Z',
                closed_by: 'user-1',
                snapshot_id: 'snapshot-1',
                created_at: '2026-03-19T10:00:00Z',
              },
            ],
            total: 1,
          })
        )
      }

      if (url.startsWith('/requirements/sets?')) {
        return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
      }

      throw new Error(`Unhandled GET ${url}`)
    })

    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({}))
  })

  it('shows unarchive to managers and posts restore for archived cycles', async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter>
          <ReviewCycles />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const actionButtons = await screen.findAllByRole('button', { name: 'Unarchive' })
    expect(actionButtons.length).toBeGreaterThan(0)

    fireEvent.click(actionButtons[0])

    expect(screen.getByText('Unarchive assessment?')).toBeInTheDocument()
    expect(screen.getByText('Return this cycle to closed status.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Unarchive' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/review-cycles/cycle-archived/restore')
    })
  })
  it.each([
    ['', null],
    ['2026-12-20', '2026-12-20T00:00:00.000Z'],
  ])('creates a review with deadline %s and opens it', async (input, expected) => {
    vi.mocked(api.get).mockImplementation(async (url: string) => makeAxiosResponse({ items: url.startsWith('/requirements/sets?') ? [{ document_id: 'approved-set', name: 'Approved controls', document_status: 'approved' }] : [], total: url.startsWith('/requirements/sets?') ? 1 : 0 }))
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse({ id: 'created-review' }))
    render(<QueryClientProvider client={createQueryClient()}><MemoryRouter initialEntries={['/review-cycles']}><Routes><Route path="/review-cycles" element={<ReviewCycles />} /><Route path="/review-cycles/:id" element={<h1>New review workspace</h1>} /></Routes></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Create assessment' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Annual certification' } })
    if (input) fireEvent.change(screen.getByLabelText('Deadline'), { target: { value: input } })
    fireEvent.click(screen.getByRole('radio', { name: 'All approved requirement sets (lock snapshot now)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/review-cycles', expect.objectContaining({ name: 'Annual certification', deadline: expected })))
    expect(await screen.findByRole('heading', { name: 'New review workspace' })).toBeInTheDocument()
  })

  it('guides users to approve requirements and prevents creating an empty assessment', async () => {
    vi.mocked(api.get).mockResolvedValue(makeAxiosResponse({ items: [], total: 0 }))
    render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ReviewCycles /></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Create assessment' }))
    expect(await screen.findByRole('link', { name: 'Open requirements' })).toHaveAttribute('href', '/requirements')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Empty assessment' } })
    fireEvent.click(screen.getByRole('radio', { name: 'All approved requirement sets (lock snapshot now)' }))
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('recovers a failed scope load without misrepresenting it as an empty library', async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.startsWith('/requirements/sets?')) throw new Error('Offline')
      return makeAxiosResponse({ items: [], total: 0 })
    })
    render(<QueryClientProvider client={createQueryClient()}><MemoryRouter><ReviewCycles /></MemoryRouter></QueryClientProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Create assessment' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Requirement sets could not be loaded')
    expect(screen.queryByRole('link', { name: 'Open requirements' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    vi.mocked(api.get).mockResolvedValue(makeAxiosResponse({ items: [{ document_id: 'approved-set', name: 'Approved controls', document_status: 'approved' }], total: 1 }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Approved controls' }))
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled()
  })

})
