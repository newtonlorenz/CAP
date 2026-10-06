import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { RequirementWithStatus } from '../types'
import { JurisdictionProvider } from '../contexts/JurisdictionContext'
import RequirementDetail from '../pages/RequirementDetail'

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

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
    toasts: [],
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

describe('RequirementDetail review-specific fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('renders source requirement content without evidence/history tabs or current status', async () => {
    const requirementId = 'req-1'
    const requirement: RequirementWithStatus = {
      id: requirementId,
      organization_id: 'org-1',
      jurisdiction_id: 'jur-1',
      source_extraction_id: null,
      document_id: 'doc-1',
      requirement_set_version_id: 'v1',
      source_requirement_id: null,
      reference_id: 'REQ-1',
      title: 'Requirement Title',
      text: '<p>Requirement body text</p>',
      requirement_type: 'mandatory',
      parent_id: null,
      default_owner_id: null,
      active: true,
      version: 3,
      sort_order: 1,
      created_at: new Date().toISOString(),
      current_status: 'in_progress',
      assigned_to: null,
      status_history: [
        {
          id: 's1',
          requirement_id: requirementId,
          status: 'in_progress',
          assigned_to: null,
          comment: 'In progress',
          changed_by: 'u1',
          changed_at: new Date().toISOString(),
        },
      ],
      evidence_counts: { notes: 1, files: 2, links: 3 },
    }

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
                created_at: new Date().toISOString(),
              },
            ],
            total: 1,
          })
        )
      }

      if (url === `/requirements/${requirementId}`) {
        return Promise.resolve(makeAxiosResponse(requirement))
      }

      return Promise.resolve(makeAxiosResponse({ items: [], total: 0 }))
    })

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/requirements/${requirementId}`]}>
          <JurisdictionProvider>
            <Routes>
              <Route path="/requirements/:id" element={<RequirementDetail />} />
            </Routes>
          </JurisdictionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByRole('heading', { name: 'REQ-1' })).toBeInTheDocument()
    expect(screen.getAllByText('Requirement body text').length).toBeGreaterThan(0)
    expect(screen.getByText('Edit Requirement')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
    expect(screen.getByText('Version')).toBeInTheDocument()
    expect(await screen.findByDisplayValue('REQ-1')).toBeInTheDocument()
    expect(screen.queryByText(/^Current Status$/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Evidence$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^History$/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/^Status History$/i)).not.toBeInTheDocument()

    const evidenceCalled = vi
      .mocked(api.get)
      .mock.calls.some(
        ([url]) => typeof url === 'string' && url === `/requirements/${requirementId}/evidence`
      )
    expect(evidenceCalled).toBe(false)
  })
})
