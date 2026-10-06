import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

const authState = vi.hoisted(() => ({ installationOperator: false }))

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

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u-admin',
      email: 'admin@example.com',
      full_name: 'Admin User',
      role: 'admin',
      installation_operator: authState.installationOperator,
      active: true,
      created_at: new Date().toISOString(),
    },
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

import api from '../api/client'
import Jurisdictions from '../pages/Jurisdictions'
vi.mock('../api/applications', () => ({ applicationsApi: { marketProfile: vi.fn().mockResolvedValue({ status: 'published', checked_at: '2026-09-30' }) } }))

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

describe('Jurisdictions Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.installationOperator = false
  })

  it('shows the effective report header and organisation setup without shared-jurisdiction controls', async () => {
    vi.mocked(api.get).mockResolvedValue(
      makeAxiosResponse({
        items: [
          {
            id: 'jur-1',
            code: 'dk',
            name: 'Denmark',
            regulator_name: 'Example Authority',
            report_header_text: null,
            pack_status: 'published',
            pack_version: '2026.1.0',
            parser_mode: 'dk_hybrid',
            supports_deterministic_import: true,
            coverage_notes: 'Production-ready Denmark pack',
            active: true,
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
      })
    )

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <JurisdictionProvider><Jurisdictions /></JurisdictionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /jurisdictions/i })).toBeInTheDocument()
    })
    expect(await screen.findByRole('columnheader', { name: 'Report header preview' })).toBeInTheDocument()
    expect((await screen.findAllByText('Published checklist')).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Sources checked 30 Sept? 2026/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Example Authority').length).toBeGreaterThan(1)
    expect(screen.getAllByRole('button', { name: 'Market setup for Denmark' })).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /create jurisdiction/i })).not.toBeInTheDocument()
  })

  it('shows shared-jurisdiction controls only to installation operators', async () => {
    authState.installationOperator = true
    vi.mocked(api.get).mockResolvedValue(makeAxiosResponse({ items: [], total: 0 }))

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter><JurisdictionProvider><Jurisdictions /></JurisdictionProvider></MemoryRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByRole('button', { name: /create jurisdiction/i })).toBeInTheDocument()
  })
})
