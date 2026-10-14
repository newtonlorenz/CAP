import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Link, createMemoryRouter, RouterProvider } from 'react-router-dom'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import api from '../api/client'
import AccessPanel from '../components/access/AccessPanel'
import TeamsPanel from '../components/access/TeamsPanel'
vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'admin', role: 'admin' } }) }))
const users = [{ id: 'owner', full_name: 'Access owner', email: 'owner@example.test' }, { id: 'reader', full_name: 'Reader', email: 'reader@example.test' }]
function mount(node: React.ReactNode, path = '/') { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}>{node}</MemoryRouter></QueryClientProvider>) }
function mountAccessEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/', element: <DraftNavigationProvider><AccessPanel type="application" id="app" initialOpen /></DraftNavigationProvider> }, { path: '/access-teams', element: <p>Teams destination</p> }])
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.get).mockImplementation(async (url) => {
    if (url?.startsWith('/users/mentions')) return { data: { items: users, total: 2 } }
    if (url === '/access/teams') return { data: [{ id: 'team', name: 'Licensing', owner_id: 'owner', member_ids: ['owner'], revision: 2 }] }
    return { data: { resource_type: 'application', resource_id: 'app', visibility: 'secret', owner_id: 'owner', revision: 7, effective_permissions: ['view', 'manage_access'], grants: [{ subject_type: 'user', subject_id: 'reader', permissions: ['summary'] }] } }
  })
})
it('requires an audit reason to revoke access and retains edits after a conflicting save', async () => {
  vi.mocked(api.put).mockRejectedValue(new Error('Conflict'))
  mount(<AccessPanel type="application" id="app" />)
  fireEvent.click(screen.getByRole('button', { name: 'Who can access this?' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Remove recipient 1' }))
  expect(screen.getByRole('button', { name: 'Save access' })).toBeDisabled()
  fireEvent.change(screen.getByRole('textbox', { name: 'Reason for access change' }), { target: { value: 'Engagement ended' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.put).toHaveBeenCalledWith('/access/application/app', { expected_revision: 7, visibility: 'secret', grants: [], reason: 'Engagement ended' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('textbox', { name: 'Reason for access change' })).toHaveValue('Engagement ended')
  expect(screen.queryByRole('combobox', { name: 'Recipient 1' })).not.toBeInTheDocument()
})
it.each(['visibility', 'permission', 'reason'] as const)('preserves an access %s draft on Cancel and releases navigation when undone', async (field) => {
  mountAccessEditor()
  const visibility = await screen.findByRole('combobox', { name: 'Visibility' })
  const permission = screen.getByRole('checkbox', { name: 'View details' })
  const reason = screen.getByRole('textbox', { name: 'Reason for access change' })
  if (field === 'visibility') fireEvent.change(visibility, { target: { value: 'restricted' } })
  if (field === 'permission') fireEvent.click(permission)
  if (field === 'reason') fireEvent.change(reason, { target: { value: 'Revised sharing' } })
  fireEvent.click(screen.getByRole('link', { name: 'Manage teams' }))
  expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeInTheDocument()
  expect(screen.queryByText('Teams destination')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  if (field === 'visibility') {
    expect(visibility).toHaveValue('restricted')
    fireEvent.change(visibility, { target: { value: 'secret' } })
  }
  if (field === 'permission') {
    expect(permission).toBeChecked()
    fireEvent.click(permission)
  }
  if (field === 'reason') {
    expect(reason).toHaveValue('Revised sharing')
    fireEvent.change(reason, { target: { value: '' } })
  }
  fireEvent.click(screen.getByRole('link', { name: 'Manage teams' }))
  expect(await screen.findByText('Teams destination')).toBeInTheDocument()
})

it('protects a pending access save and clears the warning before refreshing saved access', async () => {
  let completeSave!: (value: { data: object }) => void
  vi.mocked(api.put).mockImplementation(() => new Promise(resolve => { completeSave = resolve }))
  mountAccessEditor()
  fireEvent.change(await screen.findByRole('textbox', { name: 'Reason for access change' }), { target: { value: 'Confirmed sharing' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.put).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('link', { name: 'Manage teams' }))
  expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  const pending = new Event('beforeunload', { cancelable: true })
  fireEvent(window, pending)
  expect(pending.defaultPrevented).toBe(true)
  // jsdom cannot reload a document; keep the real draft lifecycle assertions.
  const reloadFrame = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(0)
  try {
    await act(async () => completeSave({ data: {} }))
    await waitFor(() => {
      const saved = new Event('beforeunload', { cancelable: true })
      fireEvent(window, saved)
      expect(saved.defaultPrevented).toBe(false)
    })
    fireEvent.click(screen.getByRole('link', { name: 'Manage teams' }))
    expect(await screen.findByText('Teams destination')).toBeInTheDocument()
  } finally {
    reloadFrame.mockRestore()
  }
})
it('does not offer another team membership editor to an account administrator', async () => {
  mount(<TeamsPanel users={users} />)
  await screen.findByRole('heading', { name: 'Licensing' })
  expect(screen.getByText(/managed by its owner/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save membership' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'New team' })).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Team name' })).not.toBeInTheDocument()
})


it('retains filtered member selections and owner membership after a failed team save', async () => {
  vi.mocked(api.post).mockRejectedValue(new Error('Revision conflict'))
  mount(<TeamsPanel users={users} />)
  const newTeam = await screen.findByRole('button', { name: 'New team' })
  await waitFor(() => expect(newTeam).toBeEnabled())
  fireEvent.click(newTeam)
  fireEvent.change(screen.getByRole('textbox', { name: 'Team name' }), { target: { value: 'Licensing draft' } })
  const owner = screen.getByRole('checkbox', { name: /Team owner/ })
  expect(owner).toBeChecked()
  expect(owner).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: /Reader/ }))
  fireEvent.change(screen.getByRole('searchbox', { name: 'Find a person' }), { target: { value: 'Access owner' } })
  expect(screen.queryByRole('checkbox', { name: /Reader/ })).not.toBeInTheDocument()
  expect(screen.getByText('2 selected')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Create team' }))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/access/teams', { name: 'Licensing draft', member_ids: ['admin', 'reader'] }))
  await screen.findByRole('alert')
  expect(screen.getByRole('textbox', { name: 'Team name' })).toHaveValue('Licensing draft')
  fireEvent.change(screen.getByRole('searchbox', { name: 'Find a person' }), { target: { value: '' } })
  expect(screen.getByRole('checkbox', { name: /Reader/ })).toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('textbox', { name: 'Team name' })).not.toBeInTheDocument()
})

it('restores a selected team and keeps its original revision while preserving conflict edits', async () => {
  vi.mocked(api.get).mockResolvedValue({ data: [{ id: 'owned', name: 'My team', owner_id: 'admin', member_ids: ['admin', 'reader'], revision: 8 }] })
  vi.mocked(api.put).mockRejectedValue(new Error('Conflict'))
  mount(<TeamsPanel users={users} />, '/access-teams?team=owned')
  const name = await screen.findByRole('textbox', { name: 'Team name' })
  fireEvent.change(name, { target: { value: 'Updated team' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save membership' }))
  await waitFor(() => expect(api.put).toHaveBeenCalledWith('/access/teams/owned', { name: 'Updated team', member_ids: ['admin', 'reader'], expected_revision: 8 }))
  await screen.findByRole('alert')
  expect(name).toHaveValue('Updated team')
})

it('blocks leaving a dirty team draft and disables creation when people are unavailable', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/access-teams', element: <DraftNavigationProvider><Link to="/elsewhere">Leave teams</Link><TeamsPanel users={users} /></DraftNavigationProvider> }, { path: '/elsewhere', element: <p>Other page</p> }], { initialEntries: ['/access-teams?team=new'] })
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>)
  fireEvent.change(await screen.findByRole('textbox', { name: 'Team name' }), { target: { value: 'Unsaved team' } })
  fireEvent.click(screen.getByRole('link', { name: 'Leave teams' }))
  expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeInTheDocument()
  expect(screen.queryByText('Other page')).not.toBeInTheDocument()
})

it('does not permit empty or failed people loading to create a team', async () => {
  mount(<TeamsPanel users={[]} usersError />)
  expect(await screen.findByRole('button', { name: 'New team' })).toBeDisabled()
  expect(screen.getByRole('alert')).toHaveTextContent('People are unavailable')
  expect(screen.queryByRole('textbox', { name: 'Team name' })).not.toBeInTheDocument()
})

it('restores the created team in the URL and clears the unsaved warning before refreshing access', async () => {
  vi.mocked(api.post).mockResolvedValue({ data: { id: 'created-team', name: 'Saved team', owner_id: 'admin', member_ids: ['admin'], revision: 1 } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/access-teams', element: <DraftNavigationProvider><TeamsPanel users={users} /></DraftNavigationProvider> }], { initialEntries: ['/access-teams?team=new'] })
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>)
  fireEvent.change(await screen.findByRole('textbox', { name: 'Team name' }), { target: { value: 'Saved team' } })
  const unsaved = new Event('beforeunload', { cancelable: true })
  fireEvent(window, unsaved)
  expect(unsaved.defaultPrevented).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Create team' }))
  await waitFor(() => expect(new URLSearchParams(window.location.search).get('team')).toBe('created-team'))
  const saved = new Event('beforeunload', { cancelable: true })
  fireEvent(window, saved)
  expect(saved.defaultPrevented).toBe(false)
  window.history.replaceState(window.history.state, '', '/')
})
