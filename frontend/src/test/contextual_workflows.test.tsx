import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, Link, MemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AxiosResponse } from 'axios'
import api from '../api/client'
import ChangeAssessments from '../components/workflows/ChangeAssessments'
import ProjectForms from '../components/workflows/ProjectForms'
import ProjectMaintenance from '../components/workflows/ProjectMaintenance'
import type { ReviewCycle } from '../types'
import type { ChangeImpact, ChangeImpactInput } from '../types/workflows'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn() } }))
const response = <T,>(data: T) => ({ data } as AxiosResponse<T>)
const wrap = (element: JSX.Element, client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) => render(<QueryClientProvider client={client}><MemoryRouter>{element}</MemoryRouter></QueryClientProvider>)
const savedImpact = { id: 'impact-1', requirement_set_version_id: 'version-1', requirement_id: 'req-1', certification_project_id: 'project-1', rationale: 'Changed reporting format', set_name: 'Reporting rules', version_number: 2, project_name: 'Nordic launch', requirement_reference_id: '2.1', requirement_title: 'Reporting' }

const impactRequirements = [
  { id: 'req-1', reference_id: '2.1', title: 'Reporting' },
  { id: 'req-2', reference_id: '2.2', title: 'Retention' },
]
const impactVersions = [{ id: 'version-1', version_number: 2, status: 'approved' }]

function setupImpactApi(initial: ChangeImpact[] = []) {
  let stored = initial
  vi.mocked(api.get).mockImplementation(async url => {
    if (url === '/requirements/sets') return response({ items: [{ document_id: 'doc-1', name: 'Reporting rules' }, { document_id: 'doc-2', name: 'Other rules' }], total: 2 })
    if (url === '/requirements/sets/doc-1/versions') return response({ items: impactVersions, total: 1 })
    if (url === '/requirements/sets/doc-2/versions') return response({ items: [{ id: 'version-2', version_number: 4, status: 'approved' }], total: 1 })
    if (url === '/requirements') return response({ items: impactRequirements, total: 2 })
    if (url === '/certification-projects') return response({ items: [{ id: 'project-1', name: 'Nordic launch' }, { id: 'project-2', name: 'Other launch' }], total: 2 })
    return response({ items: url.endsWith('/impacts') ? stored : [], total: stored.length })
  })
  vi.mocked(api.put).mockImplementation(async (_url, body) => {
    stored = (body as { items: ChangeImpactInput[] }).items.map((item, index) => ({ ...savedImpact, ...item, id: `impact-${index + 1}`,
      requirement_id: item.requirement_id || null,
      certification_project_id: item.certification_project_id || null,
      rationale: item.rationale || '',
      requirement_reference_id: impactRequirements.find(requirement => requirement.id === item.requirement_id)?.reference_id || '',
    }))
    return response({ items: stored })
  })
}

function pendingResponse<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(finish => { resolve = finish })
  return { promise, resolve }
}

beforeEach(() => { vi.resetAllMocks() })

describe('Contextual compliance work', () => {
  it('saves an approved requirement impact and creates an assessment only on explicit request', async () => {
    let impactsSaved = false
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url === '/requirements/sets') return response({ items: [{ document_id: 'doc-1', name: 'Reporting rules' }], total: 1 })
      if (url === '/requirements/sets/doc-1/versions') return response({ items: [{ id: 'draft-version', version_number: 3, status: 'draft' }, { id: 'version-1', version_number: 2, status: 'approved' }], total: 2 })
      if (url === '/requirements') return response({ items: [{ id: 'req-1', reference_id: '2.1', title: 'Reporting' }], total: 1 })
      if (url === '/certification-projects') return response({ items: [{ id: 'project-1', name: 'Nordic launch' }], total: 1 })
      return response({ items: url.endsWith('/impacts') && impactsSaved ? [savedImpact] : [] })
    })
    vi.mocked(api.put).mockRejectedValueOnce(new Error('network unavailable')).mockImplementation(async () => { impactsSaved = true; return response({ items: [savedImpact] }) })
    vi.mocked(api.post).mockResolvedValue(response({ items: [{ id: 'assessment-1', name: 'Reporting assessment', status: 'active' }] }))
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    fireEvent.change(screen.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    await screen.findByRole('option', { name: 'Version 2' })
    expect(screen.queryByRole('option', { name: 'Version 3' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Approved version')).toHaveValue('version-1'))
    await screen.findByRole('option', { name: '2.1 Reporting' })
    fireEvent.change(screen.getByLabelText('Affected requirement'), { target: { value: 'req-1' } })
    fireEvent.change(screen.getByLabelText('Certification project (optional)'), { target: { value: 'project-1' } })
    fireEvent.change(screen.getByLabelText('Impact rationale'), { target: { value: 'Changed reporting format' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add impact to draft' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    await screen.findByRole('alert')
    expect(screen.getAllByLabelText('Impact rationale')[0]).toHaveValue('Changed reporting format')
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    const choose = await screen.findByRole('checkbox', { name: 'Assess Reporting rules v2 2.1' })
    expect(api.put).toHaveBeenLastCalledWith('/change-management/changes/change-1/impacts', { items: [{ requirement_set_version_id: 'version-1', requirement_id: 'req-1', certification_project_id: 'project-1', rationale: 'Changed reporting format' }] })
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(choose)
    fireEvent.change(screen.getByLabelText('Assessment name'), { target: { value: 'Reporting assessment' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create assessment for selected impacts' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/change-management/changes/change-1/assessments', { impact_ids: ['impact-1'], name: 'Reporting assessment' }))
  })

  it('adds several requirements using the same set, approved version, and project', async () => {
    setupImpactApi()
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    const fields = within(screen.getByText('Add requirement impact').closest('details')!)
    fireEvent.change(fields.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    await fields.findByRole('option', { name: '2.1 Reporting' })
    fireEvent.change(fields.getByLabelText('Certification project (optional)'), { target: { value: 'project-1' } })
    for (const [requirement, rationale] of [['req-1', 'Reporting changed'], ['req-2', 'Retention changed']]) {
      fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: requirement } })
      fireEvent.change(fields.getByLabelText('Impact rationale'), { target: { value: rationale } })
      fireEvent.click(fields.getByRole('button', { name: 'Add impact to draft' }))
      expect(fields.getByLabelText('Requirement set')).toHaveValue('doc-1')
      expect(fields.getByLabelText('Approved version')).toHaveValue('version-1')
      expect(fields.getByLabelText('Certification project (optional)')).toHaveValue('project-1')
      expect(fields.getByLabelText('Affected requirement')).toHaveValue('')
      expect(fields.getByLabelText('Impact rationale')).toHaveValue('')
    }
    expect(screen.getAllByRole('button', { name: 'Remove impact' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/change-management/changes/change-1/impacts', { items: [
      { requirement_set_version_id: 'version-1', requirement_id: 'req-1', certification_project_id: 'project-1', rationale: 'Reporting changed' },
      { requirement_set_version_id: 'version-1', requirement_id: 'req-2', certification_project_id: 'project-1', rationale: 'Retention changed' },
    ] }))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('explains duplicate impacts without losing inputs and permits separate project contexts', async () => {
    setupImpactApi([savedImpact])
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />)
    await screen.findByRole('checkbox', { name: 'Assess Reporting rules v2 2.1' })
    fireEvent.click(screen.getByText('Add requirement impact'))
    const fields = within(screen.getByText('Add requirement impact').closest('details')!)
    fireEvent.change(fields.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    await fields.findByRole('option', { name: '2.1 Reporting' })
    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: 'req-1' } })
    fireEvent.change(fields.getByLabelText('Certification project (optional)'), { target: { value: 'project-1' } })
    fireEvent.change(fields.getByLabelText('Impact rationale'), { target: { value: 'Keep this pending rationale' } })
    fireEvent.click(fields.getByRole('button', { name: 'Add impact to draft' }))
    expect(await fields.findByRole('alert')).toHaveTextContent('This impact is already listed for the selected version and project.')
    expect(fields.getByLabelText('Affected requirement')).toHaveValue('req-1')
    expect(fields.getByLabelText('Impact rationale')).toHaveValue('Keep this pending rationale')
    expect(screen.getAllByRole('button', { name: 'Remove impact' })).toHaveLength(1)
    expect(api.put).not.toHaveBeenCalled()
    fireEvent.change(fields.getByLabelText('Certification project (optional)'), { target: { value: 'project-2' } })
    expect(fields.queryByRole('alert')).not.toBeInTheDocument()
    fireEvent.click(fields.getByRole('button', { name: 'Add impact to draft' }))
    expect(screen.getAllByRole('button', { name: 'Remove impact' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/change-management/changes/change-1/impacts', { items: [
      { requirement_set_version_id: 'version-1', requirement_id: 'req-1', certification_project_id: 'project-1', rationale: 'Changed reporting format' },
      { requirement_set_version_id: 'version-1', requirement_id: 'req-1', certification_project_id: 'project-2', rationale: 'Keep this pending rationale' },
    ] }))
  })

  it('keeps the next impact inputs while a save is pending and prevents overwriting new draft edits', async () => {
    setupImpactApi()
    const pending = pendingResponse<void>()
    const fallback = vi.mocked(api.put).getMockImplementation()!
    vi.mocked(api.put).mockImplementation(async (url, body, config) => { await pending.promise; return fallback(url, body, config) })
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    const fields = within(screen.getByText('Add requirement impact').closest('details')!)
    fireEvent.change(fields.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    await fields.findByRole('option', { name: '2.1 Reporting' })
    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: 'req-1' } })
    fireEvent.click(fields.getByRole('button', { name: 'Add impact to draft' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Remove impact' })).toBeDisabled()
    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: 'req-2' } })
    fireEvent.change(fields.getByLabelText('Impact rationale'), { target: { value: 'Next impact in progress' } })
    expect(fields.getByRole('button', { name: 'Add impact to draft' })).toBeDisabled()
    await act(async () => pending.resolve())
    await screen.findByRole('checkbox', { name: 'Assess Reporting rules v2 2.1' })
    expect(fields.getByLabelText('Affected requirement')).toHaveValue('req-2')
    expect(fields.getByLabelText('Impact rationale')).toHaveValue('Next impact in progress')
    expect(fields.getByRole('button', { name: 'Add impact to draft' })).toBeEnabled()
  })

  it('waits for a fresh version list instead of selecting a stale cached approved version', async () => {
    setupImpactApi()
    const pending = pendingResponse<AxiosResponse<{ items: typeof impactVersions; total: number }>>()
    const fallback = vi.mocked(api.get).getMockImplementation()!
    vi.mocked(api.get).mockImplementation((url, config) => url === '/requirements/sets/doc-1/versions' ? pending.promise : fallback(url, config))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['requirement-versions', 'doc-1'], { items: impactVersions, total: 1 })
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />, client)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    fireEvent.change(screen.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    expect(screen.getByLabelText('Approved version')).toHaveValue('')
    expect(screen.getByLabelText('Approved version')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Add impact to draft' })).toBeDisabled()
    await act(async () => pending.resolve(response({ items: [{ id: 'fresh-version', version_number: 5, status: 'approved' }], total: 1 })))
    await waitFor(() => expect(screen.getByLabelText('Approved version')).toHaveValue('fresh-version'))
    expect(screen.queryByRole('option', { name: 'Version 2' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Approved version'), { target: { value: '' } })
    expect(screen.getByLabelText('Approved version')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Add impact to draft' })).toBeDisabled()
  })

  it('does not select a version from an earlier set response or choose between multiple approved versions', async () => {
    setupImpactApi()
    const pending = pendingResponse<AxiosResponse<{ items: typeof impactVersions; total: number }>>()
    const fallback = vi.mocked(api.get).getMockImplementation()!
    vi.mocked(api.get).mockImplementation((url, config) => {
      if (url === '/requirements/sets/doc-1/versions') return pending.promise
      if (url === '/requirements/sets/doc-2/versions') return Promise.resolve(response({ items: [
        { id: 'version-2', version_number: 4, status: 'approved' },
        { id: 'version-3', version_number: 5, status: 'approved' },
      ], total: 2 }))
      return fallback(url, config)
    })
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage />)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    fireEvent.change(screen.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    fireEvent.change(screen.getByLabelText('Requirement set'), { target: { value: 'doc-2' } })
    await screen.findByRole('option', { name: 'Version 4' })
    expect(screen.getByLabelText('Approved version')).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Approved version'), { target: { value: 'version-3' } })
    await act(async () => pending.resolve(response({ items: impactVersions, total: 1 })))
    expect(screen.getByLabelText('Requirement set')).toHaveValue('doc-2')
    expect(screen.getByLabelText('Approved version')).toHaveValue('version-3')
    expect(screen.queryByRole('option', { name: 'Version 2' })).not.toBeInTheDocument()
  })

  it('allows navigation with saved reused scope and protects new per-impact inputs', async () => {
    setupImpactApi()
    const pending = pendingResponse<void>()
    const finishSave = vi.mocked(api.put).getMockImplementation()!
    vi.mocked(api.put).mockImplementation(async (url, body, config) => { await pending.promise; return finishSave(url, body, config) })
    const router = createMemoryRouter([
      { path: '/change', element: <DraftNavigationProvider><ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit canManage /><Link to="/other">Other workspace</Link></DraftNavigationProvider> },
      { path: '/other', element: <h1>Other workspace</h1> },
    ], { initialEntries: ['/change'] })
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>)
    await screen.findByText('No structured requirement impacts have been recorded.')
    fireEvent.click(screen.getByText('Add requirement impact'))
    const fields = within(screen.getByText('Add requirement impact').closest('details')!)
    fireEvent.change(fields.getByLabelText('Requirement set'), { target: { value: 'doc-1' } })
    await fields.findByRole('option', { name: '2.1 Reporting' })
    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: 'req-1' } })
    fireEvent.change(fields.getByLabelText('Certification project (optional)'), { target: { value: 'project-1' } })
    fireEvent.click(fields.getByRole('button', { name: 'Add impact to draft' }))
    const unsaved = new Event('beforeunload', { cancelable: true })
    fireEvent(window, unsaved)
    expect(unsaved.defaultPrevented).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Save impacts' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const saving = new Event('beforeunload', { cancelable: true })
    fireEvent(window, saving)
    expect(saving.defaultPrevented).toBe(true)
    await act(async () => pending.resolve())
    await screen.findByRole('checkbox', { name: 'Assess Reporting rules v2 2.1' })
    // onSuccess clears dirty before the mutation and shared guard finish updating.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Remove impact' })).toBeEnabled()
      const saved = new Event('beforeunload', { cancelable: true })
      fireEvent(window, saved)
      expect(saved.defaultPrevented).toBe(false)
    })
    expect(fields.getByLabelText('Requirement set')).toHaveValue('doc-1')
    expect(fields.getByLabelText('Approved version')).toHaveValue('version-1')
    expect(fields.getByLabelText('Certification project (optional)')).toHaveValue('project-1')

    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: 'req-2' } })
    fireEvent.change(fields.getByLabelText('Impact rationale'), { target: { value: 'Unfinished retention impact' } })
    fireEvent.click(screen.getByRole('link', { name: 'Other workspace' }))
    await screen.findByRole('dialog', { name: 'Changes are not saved yet' })
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(fields.getByLabelText('Affected requirement')).toHaveValue('req-2')
    expect(fields.getByLabelText('Impact rationale')).toHaveValue('Unfinished retention impact')
    fireEvent.change(fields.getByLabelText('Affected requirement'), { target: { value: '' } })
    fireEvent.change(fields.getByLabelText('Impact rationale'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('link', { name: 'Other workspace' }))
    await screen.findByRole('heading', { name: 'Other workspace' })
    expect(router.state.location.pathname).toBe('/other')
    router.dispose()
  })

  it('shows linked assessment context without edit or create controls for readers', async () => {
    vi.mocked(api.get).mockImplementation(async url => response({ items: url.endsWith('/impacts') ? [savedImpact] : [{ id: 'assessment-1', name: 'Reporting assessment', status: 'active' }] }))
    wrap(<ChangeAssessments changeId="change-1" jurisdictionId="jur-1" changeName="Reporting update" canEdit={false} canManage={false} />)
    expect(await screen.findByRole('link', { name: 'Reporting assessment' })).toHaveAttribute('href', '/review-cycles/assessment-1')
    expect(screen.queryByRole('button', { name: /save|create|remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('creates a form with its project link and preserves entries after a failed save', async () => {
    vi.mocked(api.get).mockImplementation(async url => response({ items: url.includes('/templates') ? [{ id: 'template-1', name: 'Certification form', kind: 'certification', active: true }] : [], total: 0 }))
    vi.mocked(api.post).mockRejectedValueOnce(new Error('network unavailable')).mockResolvedValue(response({ id: 'case-1' }))
    wrap(<ProjectForms projectId="project-1" jurisdictionId="jur-1" canManage />)
    await screen.findByText('No forms are linked to this project. Add a form, import reviewed questions or use a saved blank form.')
    expect(api.get).toHaveBeenCalledWith('/preparation/cases?project_id=project-1&jurisdiction_id=jur-1&limit=100&skip=0')
    fireEvent.click(screen.getByRole('button', { name: 'Add form' }))
    fireEvent.change(screen.getByLabelText('Form name'), { target: { value: 'Evidence questionnaire' } })
    fireEvent.click(screen.getByRole('button', { name: 'Use a saved blank form' }))
    await screen.findByRole('option', { name: 'Certification form' })
    fireEvent.change(screen.getByLabelText('Saved blank form'), { target: { value: 'template-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create form' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Form name')).toHaveValue('Evidence questionnaire')
    fireEvent.click(screen.getByRole('button', { name: 'Create form' }))
    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith('/preparation/cases', { name: 'Evidence questionnaire', template_id: 'template-1', original_evidence_ids: [], jurisdiction_id: 'jur-1', project_id: 'project-1' }))
  })

  it('confirms dismissal of an unsaved form and keeps entries when dismissal is cancelled', async () => {
    vi.mocked(api.get).mockResolvedValue(response({ items: [], total: 0 }))
    wrap(<ProjectForms projectId="project-1" jurisdictionId="jur-1" canManage />)
    fireEvent.click(screen.getByRole('button', { name: 'Add form' }))
    fireEvent.change(screen.getByLabelText('Form name'), { target: { value: 'Draft questions' } })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByRole('dialog', { name: 'Discard this form draft?' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Discard this form draft?' })).getByRole('button', { name: 'Cancel' }))
    expect(screen.getByLabelText('Form name')).toHaveValue('Draft questions')
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'Discard draft' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Add form' }))
    expect(screen.getByLabelText('Form name')).toHaveValue('')
  })

  it('loads the next page of project forms without changing its project scope', async () => {
    vi.mocked(api.get).mockImplementation(async url => response({
      items: [{ id: url.includes('skip=100') ? 'case-101' : 'case-1', project_id: 'project-1', name: url.includes('skip=100') ? 'Later evidence form' : 'First evidence form', template_name: 'Certification form', status: 'draft', readiness: { ready: false, answered_count: 0, required_count: 1 } }], total: 101,
    }))
    wrap(<ProjectForms projectId="project-1" jurisdictionId="jur-1" canManage={false} />)
    await screen.findByRole('link', { name: 'First evidence form' })
    expect(screen.getByRole('button', { name: 'Previous forms' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next forms' }))
    const next = await screen.findByRole('link', { name: 'Later evidence form' })
    expect(next).toHaveAttribute('href', '/preparation?case=case-101&return_project=project-1')
    expect(api.get).toHaveBeenLastCalledWith('/preparation/cases?project_id=project-1&jurisdiction_id=jur-1&limit=100&skip=100')
    expect(screen.getByRole('button', { name: 'Next forms' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Previous forms' }))
    await screen.findByRole('link', { name: 'First evidence form' })
  })

  it('runs maintenance only for the selected project and links assessment history', async () => {
    vi.mocked(api.get).mockResolvedValue(response({ items: [], total: 0 }))
    vi.mocked(api.post).mockResolvedValue(response({ generated_cycles: 1, generated_items: 3 }))
    wrap(<ProjectMaintenance projectId="project-1" jurisdictionId="jur-1" canManage assessments={[{ id: 'maintenance-1', name: 'Annual assessment', cycle_type: 'maintenance', status: 'closed', closed_at: '2026-09-30T09:00:00Z' } as ReviewCycle]} />)
    await screen.findByText('No maintenance plans are linked to this project.')
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Annual assessment' })).toHaveAttribute('href', '/review-cycles/maintenance-1')
    fireEvent.click(screen.getByRole('button', { name: 'Run due plans' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 maintenance assessments created')
    expect(api.post).toHaveBeenCalledWith('/maintenance-plans/run-due', null, { params: { certification_project_id: 'project-1' } })
  })
})
