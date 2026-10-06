import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError, type AxiosResponse } from 'axios'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'
import { JurisdictionProvider, useJurisdiction } from '../contexts/JurisdictionContext'
import type { MarketProfile } from '../types/applications'
import MarketSetup from '../pages/MarketSetup'
import api from '../api/client'
import { applicationsApi } from '../api/applications'

vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'manager', role: 'manager' }, isAuthenticated: true, isLoading: false }) }))
vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))
vi.mock('../api/applications', () => ({ applicationsApi: { marketProfile: vi.fn(), updateMarketProfile: vi.fn() } }))
const profile: MarketProfile = { code: 'DK', version: 'one', revision: 1, status: 'draft', label: 'Danish checklist', authority: 'Authority', setup_questions: [], items: [], guidance: [], source_urls: [], checked_at: null }
function SwitchMarket() { const { setJurisdictionId } = useJurisdiction(); return <button onClick={() => setJurisdictionId('fi')}>Switch to Finland</button> }
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const router = createMemoryRouter([{ element: <QueryClientProvider client={client}><JurisdictionProvider><DraftNavigationProvider><SwitchMarket /><Outlet /></DraftNavigationProvider></JurisdictionProvider></QueryClientProvider>, children: [
    { path: '/market-setup', element: <MarketSetup /> }, { path: '/jurisdictions', element: <h1>Jurisdictions overview</h1> },
  ] }], { initialEntries: ['/market-setup'] })
  render(<RouterProvider router={router} />)
  return { client, router }
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.clearAllMocks(); localStorage.setItem('cap:jurisdictionId', 'dk')
  vi.mocked(api.get).mockResolvedValue({ data: { items: [{ id: 'dk', code: 'DK', name: 'Denmark' }, { id: 'fi', code: 'FI', name: 'Finland' }] } })
  vi.mocked(applicationsApi.marketProfile).mockResolvedValue(profile)
})
describe('Market setup drafts', () => {
  it('keeps edits through refresh, route cancellation and market-switch cancellation', async () => {
    const { client, router } = setup()
    const label = await screen.findByRole('textbox', { name: 'Profile label' })
    expect(screen.getByRole('button', { name: 'Save market profile' })).toBeDisabled()
    fireEvent.change(label, { target: { value: 'My draft' } })
    await act(async () => { client.setQueryData(['applications', 'market-profile', 'dk'], { ...profile, revision: 2, label: 'Another editor' }) })
    expect(label).toHaveValue('My draft')
    fireEvent.click(screen.getByRole('link', { name: 'Jurisdictions' }))
    const dialog = await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(label).toHaveValue('My draft')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Finland' }))
    expect(confirm).toHaveBeenCalled()
    expect(label).toHaveValue('My draft')
    expect(screen.getByText(/authority sources for Denmark/)).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'People without Finnish ID' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(label).toHaveValue('Another editor'))
    expect(screen.getByRole('button', { name: 'Save market profile' })).toBeDisabled()
    router.dispose()
  })
  it('focuses validation errors and preserves drafts after a failed save', async () => {
    const { router } = setup()
    const label = await screen.findByRole('textbox', { name: 'Profile label' })
    fireEvent.change(label, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save market profile' }))
    expect(screen.getByText('Enter a profile label.')).toBeInTheDocument()
    await waitFor(() => expect(label).toHaveFocus())
    expect(applicationsApi.updateMarketProfile).not.toHaveBeenCalled()
    fireEvent.change(label, { target: { value: 'Retained draft' } })
    vi.mocked(applicationsApi.updateMarketProfile).mockRejectedValue(new Error('Offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Save market profile' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be saved/)
    expect(label).toHaveValue('Retained draft')
    expect(screen.getByRole('button', { name: 'Save market profile' })).toBeEnabled()
    router.dispose()
  })
  it('does not apply a completed save to a different market after a confirmed switch', async () => {
    vi.mocked(applicationsApi.marketProfile).mockImplementation(async (id) => id === 'fi' ? { ...profile, code: 'FI', label: 'Finnish checklist' } : profile)
    let finishSave!: (value: MarketProfile) => void
    vi.mocked(applicationsApi.updateMarketProfile).mockImplementation(() => new Promise((resolve) => { finishSave = resolve }))
    const { router } = setup()
    fireEvent.change(await screen.findByRole('textbox', { name: 'Profile label' }), { target: { value: 'Saved Danish draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save market profile' }))
    await waitFor(() => expect(applicationsApi.updateMarketProfile).toHaveBeenCalledOnce())
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Switch to Finland' }))
    await act(async () => { finishSave({ ...profile, revision: 2, label: 'Saved Danish draft' }) })
    expect(await screen.findByRole('textbox', { name: 'Profile label' })).toHaveValue('Finnish checklist')
    expect(screen.getByRole('button', { name: 'Save market profile' })).toBeDisabled()
    router.dispose()
  })

  it('requires explicit discard for a conflict reload and uses the original revision on save', async () => {
    const { router } = setup()
    const label = await screen.findByRole('textbox', { name: 'Profile label' })
    fireEvent.change(label, { target: { value: 'Conflicting draft' } })
    vi.mocked(applicationsApi.updateMarketProfile).mockRejectedValue(new AxiosError('Conflict', 'ERR_BAD_REQUEST', undefined, undefined, { status: 409, data: { detail: 'Profile changed' } } as AxiosResponse))
    fireEvent.click(screen.getByRole('button', { name: 'Save market profile' }))
    expect(await screen.findByRole('button', { name: 'Load latest profile' })).toBeInTheDocument()
    expect(applicationsApi.updateMarketProfile).toHaveBeenCalledWith(expect.objectContaining({ expected_revision: 1, label: 'Conflicting draft' }))
    expect(screen.getByRole('button', { name: 'Save market profile' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Load latest profile' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(label).toHaveValue('Conflicting draft')
    vi.mocked(applicationsApi.marketProfile).mockResolvedValue({ ...profile, revision: 2, label: 'Latest profile' })
    fireEvent.click(screen.getByRole('button', { name: 'Load latest profile' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Discard and load latest' }))
    await waitFor(() => expect(label).toHaveValue('Latest profile'))
    expect(screen.queryByRole('button', { name: 'Load latest profile' })).not.toBeInTheDocument()
    router.dispose()
  })
})
