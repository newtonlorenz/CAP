import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import GettingStartedGuide from '../pages/dashboard/GettingStartedGuide'
import { useGettingStarted } from '../pages/dashboard/useGettingStarted'
import Dashboard from '../pages/Dashboard'

const auth = vi.hoisted(() => ({ operator: true }))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'user-1', role: 'admin', installation_operator: auth.operator } }),
}))
vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({ jurisdictionId: null, jurisdictionById: {}, isLoading: false, error: null, retry: vi.fn() }),
}))
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))
vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api/client'

function wrap(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('first-run guide', () => {
  it('shows the jurisdiction step on a fresh Dashboard', () => {
    auth.operator = true
    wrap(<Dashboard />)
    expect(screen.getByRole('heading', { name: 'Get started' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open jurisdictions' })).toHaveAttribute('href', '/jurisdictions')
  })

  it('does not offer a jurisdiction write to an ordinary admin', () => {
    wrap(<GettingStartedGuide stage="jurisdiction" isOperator={false} />)
    expect(screen.queryByRole('link', { name: 'Open jurisdictions' })).not.toBeInTheDocument()
    expect(screen.getByText(/Ask your installation operator/)).toBeInTheDocument()
  })

  it('offers a licence application before any approved requirements exist', () => {
    wrap(<GettingStartedGuide stage="requirements" isOperator={false} />)
    expect(screen.getByRole('link', { name: 'Start a licence pack' })).toHaveAttribute('href', '/licence-applications?create=1')
    expect(screen.getByRole('link', { name: 'Start a certification' })).toHaveAttribute('href', '/certification-projects')
    expect(screen.getByRole('link', { name: 'Start change management' })).toHaveAttribute('href', '/change-management')
    expect(screen.getByText(/start a licence pack or certification project before approving requirements/)).toBeInTheDocument()
  })

  it('advances only when an approved baseline exists and a review has started', async () => {
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url.startsWith('/requirements/sets')) {
        return { data: { items: [{ current_version_status: 'draft', requirements_active: 1 }], total: 1 } } as never
      }
      return { data: { items: [], total: 0 } } as never
    })
    function Stage() {
      const state = useGettingStarted('jurisdiction-1', true)
      return <span>{state.isLoading ? 'loading' : state.stage}</span>
    }
    wrap(<Stage />)
    await waitFor(() => expect(screen.getByText('approval')).toBeInTheDocument())
  })

  it.each([
    { sets: [], reviews: 0, expected: 'requirements' },
    { sets: [{ current_version_status: 'draft', requirements_active: 0 }], reviews: 0, expected: 'requirements' },
    { sets: [{ current_version_status: 'approved', requirements_active: 1 }], reviews: 0, expected: 'review' },
    { sets: [{ current_version_status: 'approved', requirements_active: 1 }], reviews: 1, expected: 'complete' },
  ])('reports $expected for the current journey', async ({ sets, reviews, expected }) => {
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url.startsWith('/requirements/sets')) {
        return { data: { items: sets, total: sets.length } } as never
      }
      return { data: { items: [], total: reviews } } as never
    })
    function Stage() {
      const state = useGettingStarted('jurisdiction-1', true)
      return <span>{state.isLoading ? 'loading' : state.stage}</span>
    }
    wrap(<Stage />)
    await waitFor(() => expect(screen.getByText(expected)).toBeInTheDocument())
  })
})
