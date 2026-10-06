import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import api from '../api/client'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

function Account() {
  const auth = useAuth()
  return <div>
    <p>{auth.user?.full_name || 'Signed out'}</p>
    {auth.sessionError && <p role="alert">{auth.sessionError}</p>}
    <button onClick={() => void auth.logout()}>Sign out</button>
    <button onClick={() => void auth.login('second@example.test', 'fixture-password')}>Switch account</button>
  </div>
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.get).mockResolvedValue({ data: { id: 'first', full_name: 'First account' } })
  vi.mocked(api.post).mockResolvedValue({ data: {} })
})

async function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><AuthProvider><Account /></AuthProvider></QueryClientProvider>)
  await screen.findByText('First account')
  client.setQueryData(['review-cycle', 'private-review'], 'Private first-account content')
  return client
}

it('clears cached private records after successful sign out', async () => {
  const client = await setup()
  fireEvent.click(screen.getByText('Sign out'))
  await screen.findByText('Signed out')
  expect(client.getQueryCache().getAll()).toHaveLength(0)
})

it('clears first-account data before showing a different account', async () => {
  const client = await setup()
  vi.mocked(api.get).mockResolvedValue({ data: { id: 'second', full_name: 'Second account' } })
  fireEvent.click(screen.getByText('Switch account'))
  await screen.findByText('Second account')
  expect(client.getQueryData(['review-cycle', 'private-review'])).toBeUndefined()
})

it('reports failed sign out without falsely showing a closed session', async () => {
  await setup()
  vi.mocked(api.post).mockRejectedValue(new Error('Offline'))
  fireEvent.click(screen.getByText('Sign out'))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Sign out failed'))
  expect(screen.getByText('First account')).toBeInTheDocument()
})
