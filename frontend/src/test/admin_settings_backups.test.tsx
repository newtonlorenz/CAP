import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'

const logoutMock = vi.fn()
const authState = vi.hoisted(() => ({ installationOperator: true }))

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

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'admin-1',
      email: 'admin@example.com',
      full_name: 'Admin',
      role: 'admin',
      installation_operator: authState.installationOperator,
      active: true,
      created_at: new Date().toISOString(),
    },
    isLoading: false,
    login: vi.fn(),
    logout: logoutMock,
    isAuthenticated: true,
  }),
}))

import api from '../api/client'
import Settings from '../pages/admin/Settings'

function makeAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {} as AxiosResponse<T>['headers'],
    config: {} as unknown as InternalAxiosRequestConfig,
  }
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

function renderSettings(entry = '/admin/settings?section=backups') {
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}><Settings /></MemoryRouter>
    </QueryClientProvider>
  )
}

const baseBackup = {
  id: '20260224T220000Z-abcd1234',
  archive_filename: '20260224T220000Z-abcd1234.capbak',
  created_at: new Date().toISOString(),
  reason: 'manual',
  source_backup_id: null,
  created_by_user_id: 'u1',
  created_by_user_name: 'Admin',
  size_bytes: 1024,
  sha256: 'a'.repeat(64),
  format_version: 1,
}

describe('Admin Settings backups', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.installationOperator = true
    logoutMock.mockResolvedValue(undefined)
    Object.defineProperty(URL, 'createObjectURL', {
      writable: true,
      value: vi.fn(() => 'blob://test'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      writable: true,
      value: vi.fn(),
    })
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      writable: true,
      value: vi.fn(),
    })
    Object.defineProperty(window, 'location', {
      writable: true,
      value: {
        ...window.location,
        assign: vi.fn(),
      },
    })

    vi.mocked(api.get).mockImplementation((url: unknown) => {
      if (typeof url === 'string' && url.includes('/integrations/jira')) {
        return Promise.resolve(
          makeAxiosResponse({
            configured: false,
            integration: null,
          })
        )
      }
      if (typeof url === 'string' && url.includes('/admin/backups')) {
        return Promise.resolve(
          makeAxiosResponse({
            items: [baseBackup],
            total: 1,
          })
        )
      }
      return Promise.resolve(makeAxiosResponse({}))
    })
    vi.mocked(api.post).mockResolvedValue(makeAxiosResponse(baseBackup))
    vi.mocked(api.delete).mockResolvedValue(makeAxiosResponse({}))
    vi.mocked(api.put).mockResolvedValue(makeAxiosResponse({}))
  })

  it('renders backup section and backup row', async () => {
    renderSettings()

    expect(await screen.findByRole('heading', { name: /backups & restore/i })).toBeInTheDocument()
    expect(await screen.findByText(/manual/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create backup/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /import backup/i })).toBeInTheDocument()
    expect(screen.getByText('Your access: System admin')).toBeInTheDocument()
  })

  it.each(['/admin/settings', '/admin/settings?section=backups'])(
    'lets company admins configure Jira without backup access from %s',
    async (entry) => {
      authState.installationOperator = false
      renderSettings(entry)

      expect(screen.getByText('Your access: Company admin')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Backups & restore' }))
      const backupSection = screen.getByRole('region', { name: 'Backup settings' })
      expect(within(backupSection).getByText(/contact a system admin/i)).toBeInTheDocument()
      expect(within(backupSection).queryByRole('button')).not.toBeInTheDocument()
      expect(screen.queryByLabelText(/import backup file/i)).not.toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Jira integration' }))
      fireEvent.change(await screen.findByRole('textbox', { name: 'Jira site URL' }), {
        target: { value: 'https://company.atlassian.net' },
      })
      fireEvent.change(screen.getByRole('textbox', { name: 'Project key' }), { target: { value: 'CAP' } })
      fireEvent.change(screen.getByRole('textbox', { name: 'Jira account email' }), {
        target: { value: 'jira@example.com' },
      })
      fireEvent.change(screen.getByLabelText('API token'), { target: { value: 'company-token' } })
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(api.put).toHaveBeenCalledWith('/integrations/jira', {
        base_url: 'https://company.atlassian.net',
        project_key: 'CAP',
        user_email: 'jira@example.com',
        api_token: 'company-token',
        enabled: true,
      }))
      expect(api.get).toHaveBeenCalledWith('/integrations/jira')
      expect(api.get).not.toHaveBeenCalledWith('/admin/backups')
    }
  )

  it('preserves an integration draft when switching settings sections', async () => {
    renderSettings()
    fireEvent.click(screen.getByRole('button', { name: 'Jira integration' }))
    const site = await screen.findByRole('textbox', { name: 'Jira site URL' })
    fireEvent.change(site, { target: { value: 'https://draft.example.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Backups & restore' }))
    expect(screen.queryByRole('textbox', { name: 'Jira site URL' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Jira integration' }))
    expect(screen.getByRole('textbox', { name: 'Jira site URL' })).toHaveValue('https://draft.example.test')
    expect(api.put).not.toHaveBeenCalled()
  })

  it('creates, imports, and downloads backup', async () => {
    renderSettings()

    const reasonCell = await screen.findByText(baseBackup.reason)
    const backupRow = reasonCell.closest('tr')
    expect(backupRow).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /create backup/i }))
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/admin/backups')
    })

    const importInput = screen.getByLabelText(/import backup file/i)
    const importFile = new File(['backup-bytes'], 'restore.capbak', {
      type: 'application/octet-stream',
    })
    fireEvent.change(importInput, { target: { files: [importFile] } })

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/admin/backups/import',
        expect.any(FormData),
        expect.objectContaining({
          headers: expect.objectContaining({ 'Content-Type': 'multipart/form-data' }),
        })
      )
    })

    fireEvent.click(
      within(backupRow as HTMLTableRowElement).getByRole('button', {
        name: new RegExp(`download backup ${baseBackup.id}`, 'i'),
      })
    )
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        `/admin/backups/${baseBackup.id}/download`,
        expect.objectContaining({ responseType: 'blob' })
      )
    })
  })

  it('requires RESTORE confirmation before restore and supports delete', async () => {
    vi.mocked(api.post).mockImplementation((url: unknown, _body: unknown) => {
      if (typeof url === 'string' && url.includes('/restore')) {
        return Promise.resolve(
          makeAxiosResponse({
            restored_backup_id: baseBackup.id,
            pre_restore_backup_id: 'pre-restore-id',
            completed_at: new Date().toISOString(),
            reason: null,
          })
        )
      }
      return Promise.resolve(makeAxiosResponse(baseBackup))
    })

    renderSettings()

    const reasonCell = await screen.findByText(baseBackup.reason)
    const backupRow = reasonCell.closest('tr')
    expect(backupRow).not.toBeNull()

    fireEvent.click(
      within(backupRow as HTMLTableRowElement).getByRole('button', {
        name: new RegExp(`restore backup ${baseBackup.id}`, 'i'),
      })
    )

    const dialog = await screen.findByRole('dialog', { name: /restore backup/i })
    const confirmButton = within(dialog).getByRole('button', { name: /restore backup/i })
    expect(confirmButton).toBeDisabled()

    const textarea = within(dialog).getByLabelText(/type RESTORE to confirm/i)
    fireEvent.change(textarea, { target: { value: 'restore' } })
    expect(confirmButton).toBeDisabled()

    fireEvent.change(textarea, { target: { value: 'RESTORE' } })
    expect(confirmButton).not.toBeDisabled()
    fireEvent.click(confirmButton)

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        `/admin/backups/${baseBackup.id}/restore`,
        expect.objectContaining({ confirmation: 'RESTORE' })
      )
    })
    await waitFor(() => {
      expect(logoutMock).toHaveBeenCalled()
      expect(window.location.assign).toHaveBeenCalledWith('/login?restored=1')
    })

    fireEvent.click(
      within(backupRow as HTMLTableRowElement).getByRole('button', {
        name: new RegExp(`delete backup ${baseBackup.id}`, 'i'),
      })
    )
    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith(`/admin/backups/${baseBackup.id}`)
    })
  })
})
