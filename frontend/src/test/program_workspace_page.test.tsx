import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'jur-1',
    jurisdictions: [{ id: 'jur-1', code: 'dk', name: 'Denmark' }],
    jurisdictionById: { 'jur-1': { id: 'jur-1', code: 'dk', name: 'Denmark' } },
    isLoading: false,
    setJurisdictionId: vi.fn(),
  }),
}))

import api from '../api/client'
import ProgramWorkspace from '../pages/ProgramWorkspace'

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

describe('ProgramWorkspace page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders stage timeline, blockers, and role actions', async () => {
    vi.mocked(api.get).mockResolvedValue(
      makeAxiosResponse({
        generated_at: new Date().toISOString(),
        jurisdiction_id: 'jur-1',
        items: [
          {
            project_id: 'project-1',
            project_name: 'Nordic launch',
            jurisdiction_id: 'jur-1',
            stage: 'intake',
            status: 'active',
            target_submission_date: null,
            current_stage_readiness: { ready: false, blocker_count: 1 },
            blockers: [
              {
                code: 'baseline_configured',
                reason: 'Select at least one approved requirement set before moving out of Intake.',
                cta_label: 'Configure baseline',
                cta_path: '/certification-projects?project=project-1',
              },
            ],
            deep_links: {
              project: '/certification-projects?project=project-1',
              review_cycle: null,
              submission_package: null,
            },
            stage_states: [
              {
                stage: 'intake',
                title: 'Intake',
                order: 0,
                state: 'in_progress',
                ready_to_advance: false,
                checks: [
                  {
                    code: 'baseline_configured',
                    label: 'Project baseline is configured',
                    passed: false,
                    severity: 'error',
                    reason:
                      'Select at least one approved requirement set before moving out of Intake.',
                    cta_label: 'Configure baseline',
                    cta_path: '/certification-projects?project=project-1',
                  },
                ],
              },
            ],
          },
        ],
        next_actions: [
          {
            id: 'project-1:intake:baseline_configured',
            project_id: 'project-1',
            stage: 'intake',
            priority: 'medium',
            title: 'Intake is blocked',
            summary: 'Select at least one approved requirement set before moving out of Intake.',
            cta_label: 'Configure baseline',
            cta_path: '/certification-projects?project=project-1',
            role_scope: ['admin', 'manager'],
          },
        ],
      })
    )

    const queryClient = createTestQueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProgramWorkspace />
        </MemoryRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /project readiness/i })).toBeInTheDocument()
    })

    expect(screen.getByText(/next actions/i)).toBeInTheDocument()
    expect(screen.getByText(/intake is blocked/i)).toBeInTheDocument()
    expect(screen.getByText(/project stages/i)).toBeInTheDocument()
    expect(screen.getAllByText(/configure baseline/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/items needing attention/i)).toBeInTheDocument()
  })
})
