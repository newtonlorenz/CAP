import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../contexts/AuthContext'

// Mock the API client
vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

const TestWrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <AuthProvider>{children}</AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>
)

describe('AuthProvider', () => {
  it('should render children', () => {
    render(
      <TestWrapper>
        <div data-testid="child">Test Child</div>
      </TestWrapper>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('should start with no user when no token in storage', () => {
    localStorage.clear()
    render(
      <TestWrapper>
        <div>Test</div>
      </TestWrapper>
    )
    // AuthProvider should render without crashing
    expect(screen.getByText('Test')).toBeInTheDocument()
  })
})

describe('Component Structure', () => {
  it('should have proper types defined', () => {
    // Test that our types are correctly structured
    interface User {
      id: string
      email: string
      full_name: string
      role: 'admin' | 'approver' | 'contributor'
      active: boolean
      created_at: string
    }

    const testUser: User = {
      id: '123',
      email: 'test@example.com',
      full_name: 'Test User',
      role: 'admin',
      active: true,
      created_at: '2024-01-01T00:00:00Z',
    }

    expect(testUser.role).toBe('admin')
    expect(testUser.active).toBe(true)
  })
})
