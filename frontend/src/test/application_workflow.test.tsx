import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Applications from '../pages/Applications'
import api from '../api/client'
import type { LicenceApplication } from '../types/applications'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))
let role = 'manager'
let space = 'dk'
const setJurisdictionId = vi.fn()
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'owner', role } }) }))
vi.mock('../contexts/JurisdictionContext', () => ({ useJurisdiction: () => ({ jurisdictionId: space, setJurisdictionId, jurisdictions: [{ id: 'dk', code: 'DK', name: 'Denmark', active: true }, { id: 'fi', code: 'FI', name: 'Finland', active: true }, { id: 'se', code: 'SE', name: 'Sweden', active: true }], jurisdictionById: { dk: { name: 'Denmark' }, fi: { name: 'Finland' }, se: { name: 'Sweden' } } }) }))
const makeApplication = (overrides: Partial<LicenceApplication> = {}): LicenceApplication => ({
  id: 'app-1', name: 'Annex A and B', scope: 'annex_only', jurisdiction_id: 'dk', applicant: 'Example Ltd', authority: 'Authority', description: null, owner_id: null, due_date: null,
  status: 'draft', revision: 1, outcome: null, created_at: '2026-09-29T10:00:00Z', updated_at: '2026-09-29T10:00:00Z', components: [], followups: [], snapshots: [], history: [],
  readiness: { ready: false, required_count: 0, ready_count: 0, blockers: [{ code: 'empty', message: 'Include at least one component.' }] }, ...overrides,
})
let stored = makeApplication()
const component = { id: 'component-1', name: 'Annex A', kind: 'annex' as const, required: true, included: true, owner_id: null, due_date: null, case_id: 'case-1', evidence_id: null, case_name: 'Annex A', ready: true, blockers: [] }
const ready = { ready: true, required_count: 1, ready_count: 1, blockers: [] }
const profile = { code: 'DK', version: 'builtin-1', revision: 0, status: 'published', label: 'Denmark application', authority: 'Authority', setup_questions: [{ key: 'people', label: 'People requiring declarations', type: 'people' }], items: [{ key: 'annex-a', name: 'Annex A', kind: 'annex', required: true, repeat_for: 'people' }], guidance: [], source_urls: [], checked_at: '2026-09-30' }
let currentProfile = profile
function renderPage(query = '?application=app-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/licence-applications${query}`]}><Applications /></MemoryRouter></QueryClientProvider>)
  return { ...view, client }
}
beforeEach(() => {
  role = 'manager'; space = 'dk'; stored = makeApplication(); currentProfile = profile; vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.get).mockImplementation(async (url) => {
    if (url === '/applications/market-profile') return { data: currentProfile }
    if (url === '/access/application/app-1') return { data: { resource_type: 'application', resource_id: 'app-1', visibility: 'secret', owner_id: 'owner', revision: 1, effective_permissions: ['view', 'manage_access'], grants: [] } }
    if (url === '/access/teams') return { data: [] }
    if (url === '/applications/app-1') return { data: stored }
    if (url?.startsWith('/applications?')) return { data: { items: [], total: 0 } }
    if (url === '/preparation/templates?limit=500') return { data: { items: [{ id: 'annex-template', name: 'Supplementary annex', kind: 'licence_application', active: true, fields: [], revision: 1 }], total: 1 } }
    if (url === '/preparation/starters') return { data: { items: [], total: 0 } }
    if (url?.startsWith('/preparation/cases?') || url?.startsWith('/users/mentions') || url?.startsWith('/certification-projects')) return { data: { items: [], total: 0 } }
    throw new Error(`Unexpected GET ${url}`)
  })
})

describe('flexible application workspace', () => {
  it('confirms placeholder removal and retains the row after cancellation or a failed request', async () => {
    const placeholder = { ...component, id: 'unused', name: 'Unused document', kind: 'document' as const, required: false, included: false, case_id: null, case_name: null, ready: false }
    stored = makeApplication({ components: [component, placeholder], revision: 4, readiness: ready })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    try {
      renderPage('?application=app-1&tab=forms')
      const remove = await screen.findByRole('button', { name: 'Remove Unused document' })
      expect(screen.queryByRole('button', { name: 'Remove Annex A' })).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Remove Unused document' }))
      expect(api.delete).not.toHaveBeenCalled()
      fireEvent.click(screen.getByRole('button', { name: 'Edit Unused document' }))
      const editor = within(remove.closest('article')!).getByRole('textbox', { name: 'Form or document name' })
      fireEvent.change(editor, { target: { value: 'Unsaved name' } })
      expect(screen.getByRole('button', { name: 'Remove Unused document' })).toBeDisabled()
      expect(editor).toHaveValue('Unsaved name')
      confirm.mockReturnValue(true)
      fireEvent.click(screen.getByRole('button', { name: 'Close editor' }))
      expect(screen.getByRole('button', { name: 'Remove Unused document' })).toBeEnabled()
      vi.mocked(api.delete).mockRejectedValueOnce(new Error('Unavailable'))
      fireEvent.click(screen.getByRole('button', { name: 'Remove Unused document' }))
      await screen.findByRole('alert')
      expect(screen.getByRole('heading', { name: 'Unused document' })).toBeInTheDocument()
      vi.mocked(api.delete).mockImplementationOnce(async () => {
        stored = { ...stored, revision: 5, components: [component] }
        return { data: stored }
      })
      fireEvent.click(screen.getByRole('button', { name: 'Remove Unused document' }))
      await waitFor(() => expect(screen.queryByRole('heading', { name: 'Unused document' })).not.toBeInTheDocument())
      expect(api.delete).toHaveBeenLastCalledWith('/applications/app-1/components/unused', { params: { expected_revision: 4 } })
      expect(screen.getByRole('heading', { name: 'Annex A' })).toBeInTheDocument()
    } finally { confirm.mockRestore() }
  })

  it.each(['viewer', 'restricted', 'approved'])('hides placeholder removal for %s access or stage', async (mode) => {
    if (mode === 'viewer') role = 'viewer'
    stored = makeApplication({ components: [{ ...component, case_id: null, case_name: null }],
      ...(mode === 'approved' ? { status: 'approved' as const } : {}),
      ...(mode === 'restricted' ? { access: { permissions: ['view'] } as LicenceApplication['access'] } : {}),
    })
    renderPage('?application=app-1&tab=forms')
    await screen.findByRole('heading', { name: 'Annex A', level: 4 })
    expect(screen.queryByRole('button', { name: 'Remove Annex A' })).not.toBeInTheDocument()
  })

  it('creates a blank Swedish pack without empty question or checklist steps', async () => {
    space = 'se'
    currentProfile = { ...profile, code: 'SE', status: 'draft', setup_questions: [], items: [] }
    vi.mocked(api.post).mockResolvedValue({ data: makeApplication({ jurisdiction_id: 'se' }) })
    renderPage('?create=1')
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Swedish operating pack' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to owners and access' })).toBeEnabled())
    expect(screen.getByText('Step 1 of 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue to owners and access' }))
    expect(screen.getByText('Step 2 of 2')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /reviewed this proposed checklist/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create licence pack' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/applications/guided', expect.objectContaining({ name: 'Swedish operating pack', jurisdiction_id: 'se', items: [], visibility: 'secret' })))
  })

  it('skips absent market questions while retaining explicit checklist review', async () => {
    currentProfile = { ...profile, setup_questions: [], items: [{ ...profile.items[0], repeat_for: '' }] }
    renderPage('?create=1')
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Operating pack' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Review proposed contents' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Review proposed contents' }))
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue to owners and access' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /reviewed this proposed checklist/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to owners and access' }))
    expect(screen.getByText('Assign individual items')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create licence pack' })).toBeEnabled()
  })

  it('opens the next workspace section directly and preserves unsaved pack details', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'Annex A and B', level: 1 })
    fireEvent.click(screen.getByText(/Application details/, { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Applicant' }), { target: { value: 'Applicant draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue to forms and documents' }))
    expect(screen.getByRole('button', { name: 'Forms and documents' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByRole('textbox', { name: 'Applicant' })).toHaveValue('Applicant draft')
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('returns from creation to the filtered list and resumes its safe draft', async () => {
    renderPage('?q=Operating&status=draft')
    fireEvent.click(screen.getByRole('button', { name: 'New licence pack' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Operating pack' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Applicant/ }), { target: { value: 'Private Applicant' } })
    await waitFor(() => expect(sessionStorage.getItem('licence-pack-draft:owner:dk')).toContain('Operating pack'))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel and return to applications' }))
    expect(screen.getByRole('searchbox', { name: 'Search applications' })).toHaveValue('Operating')
    expect(screen.queryByRole('textbox', { name: 'Pack name' })).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'New licence pack' }))
    expect(screen.getByRole('textbox', { name: 'Pack name' })).toHaveValue('Operating pack')
    expect(screen.getByRole('textbox', { name: /Applicant/ })).toHaveValue('')
  })

  it('rejects a reader opening the bookmarked creation view', () => {
    role = 'viewer'
    renderPage('?create=1')
    expect(screen.getByRole('alert')).toHaveTextContent('Only managers and administrators')
    expect(screen.queryByRole('textbox', { name: 'Pack name' })).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel and return to applications' }))
    expect(screen.queryByRole('button', { name: 'New licence pack' })).not.toBeInTheDocument()
  })

  it('keeps sensitive setup answers out of the resumable browser draft', async () => {
    renderPage('')
    expect(screen.queryByRole('textbox', { name: 'Pack name' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'New licence pack' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Operating pack' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Applicant/ }), { target: { value: 'Private Applicant' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Activities and scope' }), { target: { value: 'Private activity' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to market questions' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to market questions' }))
    fireEvent.change(screen.getByRole('textbox', { name: /People requiring declarations/ }), { target: { value: 'Private Person' } })
    await waitFor(() => expect(sessionStorage.getItem('licence-pack-draft:owner:dk')).toContain('Operating pack'))
    const draft = sessionStorage.getItem('licence-pack-draft:owner:dk') || ''
    expect(draft).not.toContain('Private Applicant')
    expect(draft).not.toContain('Private activity')
    expect(draft).not.toContain('Private Person')
  })
  it('resets list pagination and inherits the newly selected space when creating an application', async () => {
    const { client, rerender } = renderPage('?page=1')
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/applications?skip=50&limit=50&jurisdiction_id=dk'))
    space = 'fi'
    rerender(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/licence-applications?page=1']}><Applications /></MemoryRouter></QueryClientProvider>)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/applications?skip=0&limit=50&jurisdiction_id=fi'))
    expect(api.get).not.toHaveBeenCalledWith('/applications?skip=50&limit=50&jurisdiction_id=fi')
    expect(screen.queryByRole('combobox', { name: 'Jurisdiction' })).not.toBeInTheDocument()
    vi.mocked(api.post).mockResolvedValue({ data: makeApplication({ jurisdiction_id: 'fi' }) })
    fireEvent.click(screen.getByRole('button', { name: 'New licence pack' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Finnish annex' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to market questions' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to market questions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review proposed contents' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /reviewed this proposed checklist/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to owners and access' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create licence pack' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/applications/guided', expect.objectContaining({ jurisdiction_id: 'fi' })))
  })

  it('aligns the space with an application opened by a direct link', async () => {
    stored = makeApplication({ jurisdiction_id: 'fi' })
    renderPage()
    await waitFor(() => expect(setJurisdictionId).toHaveBeenCalledWith('fi'))
  })

  it('creates a pack with one blank annex per person and opens access controls', async () => {
    stored = makeApplication({ access: { visibility: 'secret', permissions: ['summary', 'view', 'edit', 'manage_access'], revision: 1 } })
    vi.mocked(api.post).mockResolvedValueOnce({ data: stored })
    renderPage('?jurisdiction=fi')
    fireEvent.click(screen.getByRole('button', { name: 'New licence pack' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Pack name' }), { target: { value: 'Annex A and B' } })
    expect(screen.queryByRole('combobox', { name: /Jurisdiction/i })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to market questions' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to market questions' }))
    fireEvent.change(screen.getByRole('textbox', { name: /People requiring declarations/ }), { target: { value: 'Person One\nPerson Two' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review proposed contents' }))
    expect(screen.getByDisplayValue('Annex A — Person One')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Annex A — Person Two')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /reviewed this proposed checklist/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue to owners and access' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create licence pack' }))
    await screen.findByRole('heading', { name: 'Annex A and B' })
    expect(screen.getByRole('heading', { name: 'Visibility and access' })).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/applications/guided', expect.objectContaining({ name: 'Annex A and B', scope: 'full_pack', jurisdiction_id: 'dk', visibility: 'secret', items: expect.arrayContaining([expect.objectContaining({ name: 'Annex A — Person One' }), expect.objectContaining({ name: 'Annex A — Person Two' })]) }))
  })

  it('explains completed outcomes without implying that a licence was issued', async () => {
    stored = makeApplication({ status: 'completed', outcome: 'Authority declined the application.' })
    renderPage()
    await screen.findByRole('heading', { name: 'Outcome recorded' })
    expect(screen.getByText(/completion alone does not mean a licence was issued/)).toBeInTheDocument()
    expect(screen.getByText('Authority declined the application.')).toBeInTheDocument()
  })

  it('shows only the safe summary even to an account administrator', async () => {
    role = 'admin'
    stored = { id: 'app-1', name: 'Confidential transaction', status: 'draft', due_date: null, summary_only: true, access: { visibility: 'secret', permissions: ['summary'], revision: 1 } } as LicenceApplication
    renderPage()
    await screen.findByRole('heading', { name: 'Confidential transaction' })
    expect(screen.getByText(/You have summary access/)).toBeInTheDocument()
    expect(screen.queryByText('Pack readiness')).not.toBeInTheDocument()
    expect(screen.queryByText('Application details')).not.toBeInTheDocument()
    expect(screen.queryByText('Add form or document')).not.toBeInTheDocument()
    expect(screen.queryByText('Activity history')).not.toBeInTheDocument()
  })

  it('honours explicit view access instead of an administrator role when offering actions', async () => {
    role = 'admin'
    stored = makeApplication({ access: { visibility: 'secret', permissions: ['summary', 'view'], revision: 1 }, readiness: ready, components: [component] })
    renderPage()
    await screen.findByRole('heading', { name: 'Annex A and B' })
    expect(screen.queryByRole('button', { name: 'Send for internal review' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit Annex A' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Who can access this?' })).not.toBeInTheDocument()
  })

  it('turns a planned annex into a form without adding a duplicate component', async () => {
    stored = makeApplication({ components: [{ ...component, case_id: null, case_name: null, ready: false }] })
    vi.mocked(api.patch).mockResolvedValue({ data: makeApplication({ revision: 2, components: [component] }) })
    renderPage('?application=app-1&tab=forms')
    fireEvent.click(await screen.findByRole('button', { name: 'Set up Annex A' }))
    const article = screen.getByRole('heading', { name: 'Annex A' }).closest('article')!
    const source = within(article).getByRole('combobox', { name: 'Form source' })
    expect(within(source).getByRole('option', { name: 'Set up a form in this pack' })).toBeInTheDocument()
    fireEvent.click(within(article).getByRole('button', { name: 'Add question' }))
    fireEvent.change(within(article).getByRole('textbox', { name: 'Question 1' }), { target: { value: 'Legal name' } })
    fireEvent.click(within(article).getByRole('button', { name: 'Save form or document' }))
    await screen.findByRole('button', { name: 'Open Annex A' })
    expect(api.patch).toHaveBeenCalledWith('/applications/app-1/components/component-1', expect.objectContaining({ expected_revision: 1, form_fields: [expect.objectContaining({ label: 'Legal name' })], case_id: null, evidence_id: null }))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('retains a new form draft across workspace tabs and prevents stage changes until saved', async () => {
    stored = makeApplication({ components: [component], readiness: ready })
    renderPage('?application=app-1&tab=forms')
    await screen.findByRole('heading', { name: 'Annex A and B' })
    fireEvent.click(screen.getByText('Add form or document', { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Form or document name' }), { target: { value: 'Annex B draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approval and submission' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send for internal review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm: Send for internal review' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Save or discard your unsaved')
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Forms and documents' }))
    expect(screen.getByRole('textbox', { name: 'Form or document name' })).toHaveValue('Annex B draft')
  })

  it('keeps draft metadata after a concurrent stage change and rejects a stale save without replaying it', async () => {
    vi.mocked(api.patch).mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: 'Application changed. Reload before saving.' } } })
    const { client } = renderPage()
    await screen.findByRole('heading', { name: 'Annex A and B' })
    fireEvent.click(screen.getByText(/Application details/, { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Applicant' }), { target: { value: 'Unsaved applicant' } })
    await act(async () => { client.setQueryData(['applications', 'item', 'app-1'], makeApplication({ status: 'in_review', revision: 2 })) })
    expect(screen.getByRole('textbox', { name: 'Applicant' })).toHaveValue('Unsaved applicant')
    fireEvent.click(screen.getByRole('button', { name: 'Save application details' }))
    await screen.findByText('Application changed. Reload before saving.')
    expect(api.patch).toHaveBeenCalledWith('/applications/app-1', { expected_revision: 1, name: 'Annex A and B', scope: 'annex_only', applicant: 'Unsaved applicant', authority: 'Authority', description: null, owner_id: null, due_date: null })
    expect(screen.getByRole('textbox', { name: 'Applicant' })).toHaveValue('Unsaved applicant')
    expect(screen.getByRole('button', { name: 'Save application details' })).toBeDisabled()
  })

  it('refreshes linked form readiness without dropping unsaved metadata when the application revision is unchanged', async () => {
    stored = makeApplication({ components: [{ ...component, ready: false }], readiness: { ready: false, required_count: 1, ready_count: 0, blockers: [{ code: 'form_incomplete', message: 'Complete Annex A.' }] } })
    const { client } = renderPage()
    await screen.findByRole('heading', { name: 'Annex A and B' })
    fireEvent.click(screen.getByText(/Application details/, { selector: 'summary' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Applicant' }), { target: { value: 'Unsaved applicant' } })
    fireEvent.click(screen.getByRole('button', { name: 'Approval and submission' }))
    expect(screen.getByRole('button', { name: 'Send for internal review' })).toBeDisabled()
    await act(async () => { client.setQueryData(['applications', 'item', 'app-1'], makeApplication({ components: [component], readiness: ready })) })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send for internal review' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect(screen.getByRole('textbox', { name: 'Applicant' })).toHaveValue('Unsaved applicant')
    expect(screen.queryByText('Complete Annex A.')).not.toBeInTheDocument()
  })

  it('lets an approver freeze a reviewed pack and exposes the immutable version', async () => {
    role = 'approver'; stored = makeApplication({ status: 'in_review', components: [component], readiness: ready })
    const snapshot = { id: 'snapshot-1', version: 1, approved_at: '2026-09-29T10:10:00Z', approved_by: 'reviewer', submitted_at: null, reference: null, notes: null, sha256: 'abc', size_bytes: 500 }
    vi.mocked(api.post).mockResolvedValue({ data: makeApplication({ status: 'approved', revision: 2, components: [component], readiness: ready, snapshots: [snapshot] }) })
    renderPage('?application=app-1&tab=approval')
    fireEvent.click(await screen.findByRole('button', { name: 'Approve pack internally' }))
    expect(screen.queryByRole('button', { name: 'Add form or document' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm: Approve and freeze pack' }))
    expect(await screen.findByRole('button', { name: 'Download version 1' })).toBeEnabled()
    expect(api.post).toHaveBeenCalledWith('/applications/app-1/approve', { expected_revision: 1 })
    expect(screen.queryByRole('button', { name: 'Record submission' })).not.toBeInTheDocument()
  })

  it('records an external submission with a local timestamp and reference, then opens follow-up', async () => {
    stored = makeApplication({ status: 'approved', components: [component], readiness: ready })
    vi.mocked(api.post).mockResolvedValueOnce({ data: makeApplication({ status: 'submitted', revision: 2, components: [component], readiness: ready }) }).mockResolvedValueOnce({ data: makeApplication({ status: 'follow_up', revision: 3, components: [component], readiness: ready }) })
    renderPage('?application=app-1&tab=approval')
    fireEvent.click(await screen.findByRole('button', { name: 'Record submission' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Submission reference' }), { target: { value: 'AUTH-100' } })
    fireEvent.change(screen.getByLabelText('Submitted at (local time)'), { target: { value: '2026-09-29T12:45:30.250' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm: Record submission' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Start follow-up' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm: Start follow-up' }))
    await screen.findByText('Add authority query', { selector: 'summary' })
    expect(api.post).toHaveBeenNthCalledWith(1, '/applications/app-1/record-submission', { expected_revision: 1, reference: 'AUTH-100', submitted_at: new Date('2026-09-29T12:45:30.250').toISOString() })
    expect(api.post).toHaveBeenNthCalledWith(2, '/applications/app-1/start-follow-up', { expected_revision: 2 })
  })

  it('allows a contributor to answer a query without offering resolution, composition or approval', async () => {
    role = 'contributor'
    const followup = { id: 'query-1', question: 'Confirm ownership', owner_id: null, due_date: null, response: null, evidence_ids: [], status: 'open' as const, resolved_at: null, created_at: '2026-09-29T10:00:00Z' }
    stored = makeApplication({ status: 'follow_up', followups: [followup] })
    vi.mocked(api.patch).mockResolvedValue({ data: makeApplication({ status: 'follow_up', revision: 2, followups: [{ ...followup, response: 'Ownership confirmed.' }] }) })
    renderPage('?application=app-1&tab=approval')
    fireEvent.change(await screen.findByRole('textbox', { name: 'Response' }), { target: { value: 'Ownership confirmed.' } })
    fireEvent.blur(screen.getByRole('textbox', { name: 'Response' }))
    await screen.findByText('Saved', { exact: true })
    expect(api.patch).toHaveBeenCalledWith('/applications/app-1/followups/query-1', { expected_revision: 1, response: 'Ownership confirmed.', evidence_ids: [] })
    expect(screen.queryByRole('button', { name: 'Resolve query' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record outcome' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Return to draft' })).not.toBeInTheDocument()
  })

  it('guards unsaved component edits when switching editors', async () => {
    stored = makeApplication({ components: [component], readiness: ready })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage('?application=app-1&tab=forms')
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Annex A' }))
    const article = screen.getByRole('heading', { name: 'Annex A' }).closest('article')!
    fireEvent.change(within(article).getByRole('textbox', { name: 'Form or document name' }), { target: { value: 'Unsaved component' } })
    fireEvent.click(screen.getByRole('button', { name: 'Close editor' }))
    expect(confirm).toHaveBeenCalledWith('Discard unsaved form or document edits?')
    expect(within(article).getByRole('textbox', { name: 'Form or document name' })).toHaveValue('Unsaved component')
    confirm.mockRestore()
  })
})

const incompleteCase = {
  id: 'case-1', name: 'Annex A', kind: 'licence_application', jurisdiction_id: 'dk', status: 'active', revision: 1,
  template_id: null, template_name: null, template_revision: null, owner_id: null, project_id: null, due_date: null,
  fields: [{ key: 'company', label: 'Company name', type: 'text', section: 'Applicant', required: true, options: [] }], responses: [],
  readiness: { ready: false, required_count: 1, answered_count: 0, accepted_count: 0, blockers: [{ field_key: 'company', code: 'missing', message: 'Response required' }] },
}
function mockForm() {
  const get = vi.mocked(api.get).getMockImplementation()!
  vi.mocked(api.get).mockImplementation(async (...args) => args[0] === '/preparation/cases/case-1' ? { data: incompleteCase } : get(...args))
}
const answerIssue = { component_id: 'component-1', case_id: 'case-1', field_key: 'company', field_label: 'Company name', field_type: 'text', section: 'Applicant', code: 'missing', message: 'Annex A: Response required' }

it('groups readiness by form and issue type, focuses the exact field and refreshes the same pack section on return', async () => {
  const blockers = [answerIssue, { ...answerIssue, field_key: 'proof', field_label: 'Proof', field_type: 'evidence' }, { ...answerIssue, field_key: 'director', field_label: 'Director', code: 'pending_acceptance' }]
  stored = makeApplication({ components: [{ ...component, ready: false, blockers }], readiness: { ...ready, ready: false, ready_count: 0, blockers } })
  mockForm(); renderPage('?application=app-1&tab=approval')
  const actions = await screen.findByRole('region', { name: 'Readiness actions' })
  expect(within(actions).getByRole('heading', { name: 'Annex A' })).toBeInTheDocument()
  expect(within(actions).getByText('Owner: Unassigned')).toBeInTheDocument()
  for (const type of ['Answers', 'Evidence', 'Acceptance']) expect(within(actions).getByText(`${type} · 1 action`)).toBeInTheDocument()
  fireEvent.click(within(actions).getByRole('button', { name: 'Review Company name' }))
  await waitFor(() => expect(screen.getByRole('article', { name: 'Company name' })).toHaveFocus())
  stored = { ...stored, readiness: ready, components: [component] }
  fireEvent.click(screen.getByRole('button', { name: /Return to pack · Annex A and B/ }))
  expect(await screen.findByText('Ready for internal approval')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Pack readiness' })).toBeVisible()
})

it('continues directly to the incomplete form and prevents opening an unrelated form under pack context', async () => {
  stored = makeApplication({ components: [{ ...component, ready: false, blockers: [answerIssue] }] })
  mockForm(); const view = renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Continue Annex A' }))
  expect(await screen.findByRole('heading', { name: 'Annex A' })).toBeVisible()
  view.unmount()
  stored = makeApplication()
  renderPage('?application=app-1&case=case-1&field=company')
  expect(await screen.findByRole('alert')).toHaveTextContent('This form is not available in this pack')
  expect(screen.queryByRole('textbox', { name: 'Company name' })).not.toBeInTheDocument()
})

it('keeps unsaved pack details when readiness navigation is declined', async () => {
  stored = makeApplication({ components: [{ ...component, ready: false, blockers: [answerIssue] }] })
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  renderPage()
  fireEvent.click(await screen.findByText(/Application details/))
  fireEvent.change(screen.getByRole('textbox', { name: 'Application name' }), { target: { value: 'Unsaved pack' } })
  fireEvent.click(screen.getByRole('button', { name: 'Continue Annex A' }))
  expect(confirm).toHaveBeenCalled()
  expect(screen.getByRole('textbox', { name: 'Application name' })).toHaveValue('Unsaved pack')
  expect(api.get).not.toHaveBeenCalledWith('/preparation/cases/case-1')
  confirm.mockRestore()
})

it('does not expose a form editor through a pack with summary access', async () => {
  stored = { id: 'app-1', name: 'Summary pack', status: 'draft', summary_only: true, access: { visibility: 'secret', permissions: ['summary'], revision: 1 } } as LicenceApplication
  mockForm(); renderPage('?application=app-1&case=case-1&field=company')
  expect(await screen.findByRole('alert')).toHaveTextContent('This form is not available in this pack')
  expect(screen.queryByRole('textbox', { name: 'Company name' })).not.toBeInTheDocument()
})
