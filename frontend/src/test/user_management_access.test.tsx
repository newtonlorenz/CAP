import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import UserManagement from '../pages/admin/UserManagement'
import api from '../api/client'

const authState = vi.hoisted(() => ({ installationOperator: false }))

vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'actor', role: 'admin', installation_operator: authState.installationOperator } }),
}))
vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

const users = [
  { id: 'system', full_name: 'System Colleague', email: 'system@example.com', role: 'admin', installation_operator: true, active: true, created_at: '2026-09-01T10:00:00Z' },
  { id: 'company', full_name: 'Company Colleague', email: 'company@example.com', role: 'admin', installation_operator: false, active: true, created_at: '2026-09-01T10:00:00Z' },
  { id: 'inactive', full_name: 'Inactive System Colleague', email: 'inactive@example.com', role: 'admin', installation_operator: false, system_admin_designated: true, active: false, created_at: '2026-09-01T10:00:00Z' },
  { id: 'demoted', full_name: 'Demoted System Colleague', email: 'demoted@example.com', role: 'contributor', installation_operator: false, system_admin_designated: true, active: true, created_at: '2026-09-01T10:00:00Z' },
]

function renderUsers() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
    <UserManagement />
  </QueryClientProvider>)
}

describe('User Management admin access', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.installationOperator = false
    vi.mocked(api.get).mockImplementation(async (url) => ({
      data: String(url).startsWith('/users?') ? { items: users, total: users.length } : { items: [], total: 0 },
    }))
  })

  it('shows company and system admin roles and prevents company admins changing system accounts', async () => {
    renderUsers()
    const table = await screen.findByRole('table')
    const companyRow = within(table).getByRole('button', { name: 'Company Colleague' }).closest('tr')!
    expect(within(companyRow).getByText('Company admin')).toBeInTheDocument()

    for (const name of ['System Colleague', 'Inactive System Colleague', 'Demoted System Colleague']) {
      const account = within(table).getByRole('button', { name })
      const row = account.closest('tr')!
      fireEvent.click(account)
      if (name === 'Demoted System Colleague') {
        expect(within(row).getByText('contributor')).toBeInTheDocument()
        expect(within(row).queryByText('System admin')).not.toBeInTheDocument()
        expect(screen.getByText(/retains its system admin designation/i)).toBeInTheDocument()
      } else {
        expect(within(row).getByText('System admin')).toBeInTheDocument()
      }
      const toggle = name === 'Inactive System Colleague' ? 'Reactivate account' : 'Deactivate account'
      fireEvent.click(within(row).getByRole('button', { name: `Actions for ${name}` }))
      for (const action of ['Edit', toggle]) {
        expect(screen.getByRole('menuitem', { name: action })).toBeDisabled()
      }
      expect(screen.getByText(/only a system admin can change this account/i)).toBeInTheDocument()
      fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    }

    fireEvent.click(within(companyRow).getByRole('button', { name: 'Actions for Company Colleague' }))
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeEnabled()
    expect(screen.getByRole('menuitem', { name: 'Deactivate account' })).toBeEnabled()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }))
    expect(screen.getByRole('combobox', { name: 'Role' })).toHaveValue('admin')
    expect(screen.getByRole('option', { name: 'Company admin' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'System admin' })).not.toBeInTheDocument()
  })

  it('removes deactivated users from the default list and keeps inactive accounts recoverable', async () => {
    let active = true
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (!String(url).startsWith('/users?')) return { data: { items: [], total: 0 } }
      const requested = new URL(String(url), 'https://cap.test').searchParams.get('active')
      const items = requested === null || requested === String(active)
        ? [{ ...users[1], active }] : []
      return { data: { items, total: items.length } }
    })
    vi.mocked(api.delete).mockImplementation(async () => {
      active = false
      return { data: null }
    })
    renderUsers()
    const table = await screen.findByRole('table')
    fireEvent.click(within(table).getByRole('button', { name: 'Actions for Company Colleague' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Deactivate account' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Deactivate account?' })).getByRole('button', { name: 'Deactivate account' }))
    await waitFor(() => expect(screen.queryAllByRole('button', { name: 'Company Colleague' })).toHaveLength(0))
    expect(screen.getByRole('combobox', { name: 'Show users' })).toHaveValue('active')
    expect(screen.getByRole('status')).toHaveTextContent('0 users')
    fireEvent.change(screen.getByRole('combobox', { name: 'Show users' }), { target: { value: 'inactive' } })
    const inactiveTable = await screen.findByRole('table')
    await within(inactiveTable).findByRole('button', { name: 'Company Colleague' })
    fireEvent.click(within(inactiveTable).getByRole('button', { name: 'Actions for Company Colleague' }))
    expect(screen.getByRole('menuitem', { name: 'Reactivate account' })).toBeEnabled()
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Show users' }), { target: { value: 'all' } })
    await waitFor(() => expect(vi.mocked(api.get).mock.calls.some(([url]) => {
      const parsed = new URL(String(url), 'https://cap.test')
      return parsed.pathname === '/users' && !parsed.searchParams.has('active')
    })).toBe(true))
  })

  it('lets system admins edit system accounts and explains the separate designation', async () => {
    authState.installationOperator = true
    renderUsers()
    const table = await screen.findByRole('table')
    fireEvent.click(within(table).getByRole('button', { name: 'Actions for Inactive System Colleague' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }))
    const dialog = screen.getByRole('dialog', { name: 'Edit user' })
    expect(within(dialog).getByRole('combobox', { name: 'Role' })).toHaveValue('admin')
    expect(within(dialog).getByRole('option', { name: 'Company admin' })).toBeInTheDocument()
    expect(within(dialog).getByText(/system admin designation is managed separately/i)).toBeInTheDocument()
    expect(within(dialog).queryByRole('option', { name: 'System admin' })).not.toBeInTheDocument()
  })
})
