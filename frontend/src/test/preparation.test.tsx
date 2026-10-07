import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { createMemoryRouter, Link, MemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import type { ReactNode } from 'react'
import CaseField from '../components/preparation/CaseField'
import CaseDetail from '../components/preparation/CaseDetail'
import EvidenceAttachments from '../components/preparation/EvidenceAttachments'
import { EvidenceLibrary } from '../components/preparation/EvidenceLibrary'
import { DraftNavigationProvider } from '../hooks/useDraftNavigationGuard'
import {
  useCaseWrites,
  type CaseWrites,
} from '../hooks/preparation/useCaseWrites'
import {
  fieldValueToString,
  nextPreparationFieldKey,
  parseFieldValue,
  type PreparationCase,
  type PreparationField,
  type PreparationEvidence,
  type PreparationResponse,
} from '../types/preparation'

const saveResponse = vi.fn()
const updateCase = vi.fn()
const getCase = vi.fn()
const acceptResponse = vi.fn()
const getEvidence = vi.fn()
const searchEvidence = vi.fn()
const download = vi.fn()
const createEvidence = vi.fn()
const uploadEvidence = vi.fn()
vi.mock('../api/preparation', () => ({
  preparationApi: {
    saveResponse: (...args: unknown[]) => saveResponse(...args),
    updateCase: (...args: unknown[]) => updateCase(...args),
    getCase: (...args: unknown[]) => getCase(...args),
    acceptResponse: (...args: unknown[]) => acceptResponse(...args),
    getEvidence: (...args: unknown[]) => getEvidence(...args),
    evidence: (...args: unknown[]) => searchEvidence(...args),
    download: (...args: unknown[]) => download(...args),
    createEvidence: (...args: unknown[]) => createEvidence(...args),
    uploadEvidence: (...args: unknown[]) => uploadEvidence(...args),
    reuseSuggestions: vi.fn(),
  },
}))
const field: PreparationField = {
  key: 'answer',
  label: 'Answer',
  section: 'General',
  help_text: null,
  type: 'text',
  required: true,
  options: [],
  reuse_key: null,
}
const response: PreparationResponse = {
  field_key: 'answer',
  value: null,
  not_applicable_reason: null,
  evidence_ids: [],
  accepted_at: null,
  accepted_by: null,
  reused_from_case_id: null,
  reused_from_field_key: null,
}
const sampleCase = {
  id: 'case-1',
  name: 'Case',
  kind: 'questionnaire',
  jurisdiction_id: 'jurisdiction-1',
  project_id: null,
  owner_id: null,
  due_date: null,
  revision: 2,
  status: 'active',
  template_id: 'template-1',
  template_name: 'Template',
  template_revision: 1,
  fields: [field],
  created_at: '2026-09-29T00:00:00Z',
  updated_at: '2026-09-29T00:00:00Z',
  responses: [response],
  readiness: {
    required_count: 1,
    answered_count: 0,
    accepted_count: 0,
    blockers: [],
    ready: false,
  },
} satisfies PreparationCase
const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={makeClient()}>{children}</QueryClientProvider>
)
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
const draftWrites = (overrides: Partial<CaseWrites> = {}) => ({
  saveField: vi.fn().mockResolvedValue(sampleCase), setFieldDirty: vi.fn(), revision: sampleCase.revision,
  isWriting: false, hasPendingDrafts: false, pauseReason: null,
  ...overrides,
}) as unknown as CaseWrites
function CaseEditor({ initial = sampleCase, onBack = vi.fn() }: { initial?: PreparationCase; onBack?: () => void }) {
  const item = useQuery({ queryKey: ['preparation', 'case', initial.id], queryFn: () => getCase(initial.id), initialData: initial, staleTime: Infinity })
  return <CaseDetail item={item.data} canEdit canManage users={[]} projects={[]} jurisdictionName={() => 'Denmark'} onBack={onBack} />
}
const renderField = (
  writes: CaseWrites,
  current = response,
  caseId = 'case-1',
) => (
  <CaseField
    key={caseId}
    caseId={caseId}
    field={field}
    response={current}
    blockers={[]}
    archived={false}
    canEdit
    canAccept
    writes={writes}
    jurisdictionName={() => 'Denmark'}
    onDirtyChange={vi.fn()}
  />
)

describe('preparation responses', () => {
  it('keeps false and zero as typed answers', () => {
    expect(parseFieldValue('yes_no', 'false')).toBe(false)
    expect(parseFieldValue('number', '0')).toBe(0)
    expect(fieldValueToString(false)).toBe('false')
    expect(fieldValueToString(0)).toBe('0')
  })
  it('generates unique stable field references after fields are removed or edited', () => {
    expect(nextPreparationFieldKey([])).toBe('field_1')
    expect(
      nextPreparationFieldKey([
        { ...field, key: 'field_1' },
        { ...field, key: 'field_3' },
      ]),
    ).toBe('field_2')
    expect(() => new RegExp('[A-Za-z](?:[A-Za-z0-9_]|-)*', 'v')).not.toThrow()
  })
  it('preserves an unsaved draft on refresh and isolates another case', async () => {
    const writes = draftWrites({ saveField: vi.fn().mockResolvedValue(null) })
    const client = makeClient()
    const view = render(
      <QueryClientProvider client={client}>
        {renderField(writes)}
      </QueryClientProvider>,
    )
    fireEvent.change(screen.getByRole('textbox', { name: 'Answer' }), {
      target: { value: 'My unsaved text' },
    })
    fireEvent.blur(screen.getByRole('textbox', { name: 'Answer' }))
    await waitFor(() =>
      expect(writes.saveField).toHaveBeenCalledWith('answer', {
        value: 'My unsaved text',
        not_applicable_reason: null,
        evidence_ids: [],
      }, expect.any(Function)),
    )
    view.rerender(
      <QueryClientProvider client={client}>
        {renderField(writes, {
          ...response,
          value: 'Another editor wrote this',
        })}
      </QueryClientProvider>,
    )
    expect(screen.getByRole('textbox', { name: 'Answer' })).toHaveValue(
      'My unsaved text',
    )
    view.rerender(
      <QueryClientProvider client={client}>
        {renderField(
          writes,
          { ...response, value: 'Other case value' },
          'case-2',
        )}
      </QueryClientProvider>,
    )
    expect(screen.getByRole('textbox', { name: 'Answer' })).toHaveValue(
      'Other case value',
    )
  })
  it('keeps yes/no unanswered until selected, saves No as false, and can clear it', async () => {
    const writes = draftWrites()
    render(
      <QueryClientProvider client={makeClient()}>
        <CaseField caseId="case-1" field={{ ...field, label: 'Is the company listed?', type: 'yes_no' }}
          response={response} blockers={[]} archived={false} canEdit canAccept writes={writes}
          jurisdictionName={() => 'Denmark'} onDirtyChange={vi.fn()} />
      </QueryClientProvider>,
    )
    expect(screen.getByRole('group', { name: 'Is the company listed?' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Yes' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'No' })).not.toBeChecked()
    fireEvent.blur(screen.getByRole('radio', { name: 'No' }))
    expect(writes.saveField).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('radio', { name: 'No' }))
    fireEvent.blur(screen.getByRole('radio', { name: 'No' }))
    await waitFor(() => expect(writes.saveField).toHaveBeenLastCalledWith('answer', expect.objectContaining({ value: false }), expect.any(Function)))
    fireEvent.click(screen.getByRole('button', { name: 'Clear answer' }))
    expect(screen.getByRole('radio', { name: 'No' })).not.toBeChecked()
    fireEvent.blur(screen.getByRole('radio', { name: 'No' }))
    await waitFor(() => expect(writes.saveField).toHaveBeenLastCalledWith('answer', expect.objectContaining({ value: null }), expect.any(Function)))
  })
  it('copies the current draft, reports denied clipboard access, and never saves by copying', async () => {
    const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('Denied'))
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    try {
      const writes = draftWrites()
      render(<QueryClientProvider client={makeClient()}>{renderField(writes)}</QueryClientProvider>)
      const copy = screen.getByRole('button', { name: 'Copy answer for Answer' })
      expect(copy).toBeDisabled()
      fireEvent.change(screen.getByRole('textbox', { name: 'Answer' }), { target: { value: 'Current draft' } })
      fireEvent.click(screen.getByRole('button', { name: 'Copy answer for Answer' }))
      await screen.findByText('Draft answer copied.')
      expect(writeText).toHaveBeenLastCalledWith('Current draft')
      fireEvent.click(screen.getByRole('button', { name: 'Copy answer for Answer' }))
      await screen.findByRole('alert')
      expect(screen.getByRole('alert')).toHaveTextContent('Could not copy')
      expect(screen.queryByText('Draft answer copied.')).not.toBeInTheDocument()
      expect(writes.saveField).not.toHaveBeenCalled()
    } finally {
      if (original) Object.defineProperty(navigator, 'clipboard', original)
      else Reflect.deleteProperty(navigator, 'clipboard')
    }
  })
  it('debounces idle drafts, skips unchanged answers and cancels delayed saves on unmount', async () => {
    vi.useFakeTimers()
    saveResponse.mockReset().mockResolvedValue({ ...sampleCase, revision: 3, responses: [{ ...response, value: 'Ready' }] })
    const view = render(<QueryClientProvider client={makeClient()}><CaseEditor /></QueryClientProvider>)
    const input = screen.getByRole('textbox', { name: 'Answer' })
    fireEvent.change(input, { target: { value: 'Temporary' } })
    fireEvent.change(input, { target: { value: '' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(saveResponse).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: 'Ready' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(799) })
    expect(saveResponse).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(saveResponse).toHaveBeenCalledTimes(1)
    fireEvent.blur(input)
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(saveResponse).toHaveBeenCalledTimes(1)
    fireEvent.change(input, { target: { value: 'Discarded on leave' } })
    view.unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(saveResponse).toHaveBeenCalledTimes(1)
  })

  it('pauses conflicting and queued drafts until the user compares and resolves them', async () => {
    vi.useFakeTimers()
    const secondField = { ...field, key: 'other', label: 'Other answer' }
    const initial = { ...sampleCase, fields: [field, secondField], responses: [response, { ...response, field_key: 'other' }] }
    let fail!: (error: unknown) => void
    saveResponse.mockReset().mockImplementationOnce(() => new Promise((_, reject) => { fail = reject }))
      .mockResolvedValueOnce({ ...initial, revision: 8, responses: [{ ...response, value: 'Latest server answer' }, { ...response, field_key: 'other', value: 'Second draft' }] })
    getCase.mockReset().mockResolvedValue({ ...initial, revision: 7, responses: [{ ...response, value: 'Latest server answer' }, { ...response, field_key: 'other', value: 'Other server answer' }] })
    render(<QueryClientProvider client={makeClient()}><CaseEditor initial={initial} /></QueryClientProvider>)
    const first = screen.getByRole('textbox', { name: 'Answer' })
    fireEvent.click(screen.getByRole('button', { name: 'View all questions' }))
    const second = screen.getByRole('textbox', { name: 'Other answer' })
    fireEvent.change(first, { target: { value: 'My first draft' } })
    fireEvent.blur(first)
    fireEvent.change(second, { target: { value: 'Second draft' } })
    fireEvent.blur(second)
    await act(async () => {})
    expect(saveResponse).toHaveBeenCalledTimes(1)
    await act(async () => fail({ isAxiosError: true, response: { status: 409 } }))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(first).toHaveValue('My first draft')
    expect(second).toHaveValue('Second draft')
    expect(screen.getByText('Latest server answer')).toBeInTheDocument()
    fireEvent.change(first, { target: { value: 'Revised local draft' } })
    fireEvent.blur(first)
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(saveResponse).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getAllByRole('button', { name: 'Discard my draft and use latest' })[0])
    expect(first).toHaveValue('Latest server answer')
    fireEvent.click(screen.getByRole('button', { name: 'Review and combine changes' }))
    expect(saveResponse).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Save combined answer' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(saveResponse).toHaveBeenCalledTimes(2)
    expect(saveResponse).toHaveBeenLastCalledWith('case-1', 'other', expect.objectContaining({ value: 'Second draft', expected_revision: 7 }))
  })

  it.each(['', 'Latest local draft'])('keeps an ambiguous failed save pending, even when the latest value is %j', async (latestValue) => {
    vi.useFakeTimers()
    saveResponse.mockReset().mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ ...sampleCase, revision: 3, responses: [{ ...response, value: latestValue || null }] })
    render(<QueryClientProvider client={makeClient()}><CaseEditor /></QueryClientProvider>)
    const input = screen.getByRole('textbox', { name: 'Answer' })
    fireEvent.change(input, { target: { value: 'Failed draft' } })
    fireEvent.blur(input)
    await act(async () => {})
    fireEvent.change(input, { target: { value: latestValue } })
    fireEvent.blur(input)
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(saveResponse).toHaveBeenCalledTimes(1)
    expect(input).toHaveValue(latestValue)
    fireEvent.click(screen.getByRole('button', { name: 'Retry saving' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(saveResponse).toHaveBeenCalledTimes(2)
    expect(saveResponse).toHaveBeenLastCalledWith('case-1', 'answer', expect.objectContaining({ value: latestValue || null }))
  })

  it('shows the latest saved answer when a draft is reverted after a background refresh', async () => {
    vi.useFakeTimers()
    saveResponse.mockReset()
    const client = makeClient()
    render(<QueryClientProvider client={client}><CaseEditor /></QueryClientProvider>)
    const input = screen.getByRole('textbox', { name: 'Answer' })
    fireEvent.change(input, { target: { value: 'Local draft' } })
    act(() => client.setQueryData(['preparation', 'case', 'case-1'], { ...sampleCase, revision: 8, responses: [{ ...response, value: 'New saved answer' }] }))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(input).toHaveValue('Local draft')
    fireEvent.change(input, { target: { value: '' } })
    expect(input).toHaveValue('New saved answer')
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(saveResponse).not.toHaveBeenCalled()
  })

  it('fences an older in-flight read so it cannot overwrite the saved answer', async () => {
    const client = makeClient()
    client.setQueryData(['preparation', 'case', 'case-1'], sampleCase)
    let save!: (item: PreparationCase) => void
    let read!: (item: PreparationCase) => void
    saveResponse.mockReset().mockImplementationOnce(() => new Promise<PreparationCase>((resolve) => { save = resolve }))
    const { result } = renderHook(() => useCaseWrites('case-1', 2), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> })
    let pending!: Promise<PreparationCase | null>
    await act(async () => { pending = result.current.saveField('answer', { value: 'Saved draft', not_applicable_reason: null, evidence_ids: [] }) })
    const reading = client.fetchQuery({ queryKey: ['preparation', 'case', 'case-1'], queryFn: () => new Promise<PreparationCase>((resolve) => { read = resolve }) }).catch(() => undefined)
    const updated = { ...sampleCase, revision: 3, responses: [{ ...response, value: 'Saved draft' }] }
    await act(async () => { save(updated); await pending })
    await act(async () => { read(sampleCase); await reading })
    expect(client.getQueryData(['preparation', 'case', 'case-1'])).toEqual(updated)
  })

  it('does not restore private case data to a cleared cache after its editor unmounts', async () => {
    const client = makeClient()
    let finish!: (item: PreparationCase) => void
    saveResponse.mockReset().mockImplementationOnce(() => new Promise<PreparationCase>((resolve) => { finish = resolve }))
    const { result, unmount } = renderHook(() => useCaseWrites('case-1', 2), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> })
    let pending!: Promise<PreparationCase | null>
    await act(async () => { pending = result.current.saveField('answer', { value: 'Private draft', not_applicable_reason: null, evidence_ids: [] }) })
    unmount()
    client.clear()
    await act(async () => { finish({ ...sampleCase, revision: 3 }); await pending })
    expect(client.getQueryData(['preparation', 'case', 'case-1'])).toBeUndefined()
  })

  it('keeps the metadata draft revision fenced across a background refresh', async () => {
    updateCase.mockReset().mockResolvedValue({ ...sampleCase, revision: 3 })
    const { result, rerender } = renderHook(({ revision }) => useCaseWrites('case-1', revision, true), { wrapper, initialProps: { revision: 2 } })
    rerender({ revision: 5 })
    await act(async () => { await result.current.updateCase({ name: 'Local name' }) })
    expect(updateCase).toHaveBeenCalledWith('case-1', { name: 'Local name', expected_revision: 2 })
  })

  it('serialises writes and advances the expected revision', async () => {
    let resolveFirst!: (value: PreparationCase) => void
    saveResponse
      .mockReset()
      .mockImplementationOnce(
        () =>
          new Promise<PreparationCase>((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValueOnce({ ...sampleCase, revision: 3 })
    const { result } = renderHook(() => useCaseWrites('case-1', 1), { wrapper })
    let first!: Promise<PreparationCase | null>
    let overlapping!: Promise<PreparationCase | null>
    act(() => {
      first = result.current.saveField('answer', {
        value: 'one',
        not_applicable_reason: null,
        evidence_ids: [],
      })
      overlapping = result.current.saveField('other', {
        value: 'two',
        not_applicable_reason: null,
        evidence_ids: [],
      })
    })
    await act(async () => {})
    expect(saveResponse).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolveFirst({ ...sampleCase, revision: 2 })
      expect((await first)?.revision).toBe(2)
      expect((await overlapping)?.revision).toBe(3)
    })
    expect(saveResponse).toHaveBeenLastCalledWith('case-1', 'other', {
      expected_revision: 2,
      value: 'two',
      not_applicable_reason: null,
      evidence_ids: [],
    })
  })
})

const archivedEvidence: PreparationEvidence = {
  id: 'ev-old',
  title: 'Archived note',
  kind: 'note',
  body: 'Past supporting context',
  link_url: null,
  filename: null,
  sha256: null,
  size_bytes: null,
  valid_from: null,
  valid_until: null,
  archived: true,
  created_at: '2026-09-29T00:00:00Z',
  created_by: 'user-1',
}

function renderEvidenceLibrary() {
  searchEvidence.mockReset().mockResolvedValue({ items: [], total: 0 })
  createEvidence.mockReset().mockResolvedValue(archivedEvidence)
  uploadEvidence.mockReset().mockResolvedValue(archivedEvidence)
  const router = createMemoryRouter([{
    element: <DraftNavigationProvider><Outlet /></DraftNavigationProvider>,
    children: [
      { path: '/evidence', element: <><EvidenceLibrary canEdit /><Link to="/other">Leave evidence library</Link></> },
      { path: '/other', element: <h1>Other workspace</h1> },
    ],
  }], { initialEntries: ['/evidence'] })
  render(<QueryClientProvider client={makeClient()}><RouterProvider router={router} /></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
  return router
}

function hasUnloadWarning() {
  const event = new Event('beforeunload', { cancelable: true })
  fireEvent(window, event)
  return event.defaultPrevented
}

describe('evidence library drafts', () => {
  it('does not warn for untouched defaults, whitespace-only fields, search or archived filters', async () => {
    const router = renderEvidenceLibrary()
    expect(hasUnloadWarning()).toBe(false)
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: '  ' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Note' }), { target: { value: '\n ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Back to evidence' }))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search evidence' }), { target: { value: 'Audit' } })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show archived evidence' }))
    expect(hasUnloadWarning()).toBe(false)
    fireEvent.click(screen.getByRole('link', { name: 'Leave evidence library' }))
    expect(await screen.findByRole('heading', { name: 'Other workspace' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    router.dispose()
  })

  it('retains note details after cancelling navigation and failed creation, then clears the warning after saving', async () => {
    const router = renderEvidenceLibrary()
    createEvidence.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(archivedEvidence)
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: 'Audit context' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Note' }), { target: { value: 'Supporting evidence' } })
    fireEvent.change(screen.getByLabelText('Valid from'), { target: { value: '2026-10-03' } })
    fireEvent.change(screen.getByRole('combobox', { name: /Visibility/ }), { target: { value: 'restricted' } })
    fireEvent.click(screen.getByRole('link', { name: 'Leave evidence library' }))
    expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('Audit context')
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Evidence could not be added')
    expect(screen.getByRole('textbox', { name: 'Note' })).toHaveValue('Supporting evidence')
    expect(screen.getByLabelText('Valid from')).toHaveValue('2026-10-03')
    expect(hasUnloadWarning()).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    expect(await screen.findByText('Evidence added with the selected visibility.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Note' })).toHaveValue('')
    expect(screen.getByLabelText('Valid from')).toHaveValue('')
    expect(screen.getByRole('combobox', { name: /Visibility/ })).toHaveValue('restricted')
    await waitFor(() => expect(hasUnloadWarning()).toBe(false))
    expect(createEvidence).toHaveBeenLastCalledWith({ visibility: 'restricted', title: 'Audit context', kind: 'note', body: 'Supporting evidence', valid_from: '2026-10-03' })
    router.dispose()
  })

  it('protects link and visibility edits, retaining saved preferences without a lingering warning', async () => {
    const router = renderEvidenceLibrary()
    let finish!: (value: PreparationEvidence) => void
    createEvidence.mockImplementationOnce(() => new Promise<PreparationEvidence>((resolve) => { finish = resolve }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Type' }), { target: { value: 'link' } })
    fireEvent.change(screen.getByRole('combobox', { name: /Visibility/ }), { target: { value: 'organisation' } })
    expect(hasUnloadWarning()).toBe(true)
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: 'Lab report' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Link URL' }), { target: { value: 'https://example.test/report' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    await waitFor(() => expect(createEvidence).toHaveBeenCalledWith({ visibility: 'organisation', title: 'Lab report', kind: 'link', link_url: 'https://example.test/report' }))
    expect(hasUnloadWarning()).toBe(true)
    expect(screen.getByRole('textbox', { name: 'Link URL' })).toBeDisabled()
    await act(async () => finish(archivedEvidence))
    expect(await screen.findByText('Evidence added with the selected visibility.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    expect(screen.getByRole('textbox', { name: 'Link URL' })).toHaveValue('')
    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveValue('link')
    expect(screen.getByRole('combobox', { name: /Visibility/ })).toHaveValue('organisation')
    await waitFor(() => expect(hasUnloadWarning()).toBe(false))
    router.dispose()
  })

  it('retains a selected file after failed upload for retry and clears the warning only after success', async () => {
    const router = renderEvidenceLibrary()
    uploadEvidence.mockRejectedValueOnce(new Error('Upload failed')).mockResolvedValueOnce(archivedEvidence)
    const selectedFile = new File(['Synthetic report'], 'report.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Type' }), { target: { value: 'file' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: 'Audit file' } })
    fireEvent.change(screen.getByLabelText('File', { exact: true }), { target: { files: [selectedFile] } })
    // jsdom does not update native file-input validity from synthetic files.
    fireEvent.submit(screen.getByRole('button', { name: 'Upload file' }).closest('form')!)
    expect(await screen.findByRole('alert')).toHaveTextContent('Evidence could not be added')
    fireEvent.click(screen.getByRole('button', { name: 'Back to evidence · Draft kept' }))
    expect(hasUnloadWarning()).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Resume evidence draft' }))
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('Audit file')
    expect((screen.getByLabelText('File', { exact: true }) as HTMLInputElement).files?.[0]).toBe(selectedFile)
    expect(hasUnloadWarning()).toBe(true)
    fireEvent.submit(screen.getByRole('button', { name: 'Upload file' }).closest('form')!)
    expect(await screen.findByText('Evidence added with the selected visibility.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    expect(uploadEvidence).toHaveBeenCalledTimes(2)
    for (const [form] of uploadEvidence.mock.calls as [FormData][]) {
      expect(form.get('file')).toBe(selectedFile)
      expect(form.get('visibility')).toBe('secret')
      expect(form.get('title')).toBe('Audit file')
    }
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('')
    await waitFor(() => expect(hasUnloadWarning()).toBe(false))
    router.dispose()
  })

  it('guards an in-flight upload and continues blocked navigation only after it succeeds', async () => {
    const router = renderEvidenceLibrary()
    let finish!: (value: PreparationEvidence) => void
    uploadEvidence.mockImplementationOnce(() => new Promise<PreparationEvidence>((resolve) => { finish = resolve }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Type' }), { target: { value: 'file' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), { target: { value: 'Uploading audit file' } })
    fireEvent.change(screen.getByLabelText('File', { exact: true }), { target: { files: [new File(['Synthetic'], 'report.pdf')] } })
    fireEvent.submit(screen.getByRole('button', { name: 'Upload file' }).closest('form')!)
    await waitFor(() => expect(uploadEvidence).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('textbox', { name: 'Title' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: /Visibility/ })).toBeDisabled()
    expect(hasUnloadWarning()).toBe(true)
    fireEvent.click(screen.getByRole('link', { name: 'Leave evidence library' }))
    expect(await screen.findByRole('dialog', { name: 'Changes are not saved yet' })).toBeVisible()
    expect(router.state.location.pathname).toBe('/evidence')
    await act(async () => finish(archivedEvidence))
    expect(await screen.findByRole('heading', { name: 'Other workspace' })).toBeVisible()
    await waitFor(() => expect(hasUnloadWarning()).toBe(false))
    router.dispose()
  })
})

describe('preparation editing and evidence', () => {
  it('keeps typing available during saves and persists newer input before acceptance', async () => {
    vi.useFakeTimers()
    let finish!: (value: PreparationCase) => void
    saveResponse.mockReset().mockImplementationOnce(() => new Promise<PreparationCase>((resolve) => { finish = resolve }))
      .mockResolvedValueOnce({ ...sampleCase, revision: 4, responses: [{ ...response, value: 'Newer draft' }] })
    acceptResponse.mockReset().mockResolvedValue({ ...sampleCase, revision: 5, responses: [{ ...response, value: 'Newer draft', accepted_at: '2026-09-29T12:00:00Z' }] })
    render(<QueryClientProvider client={makeClient()}><CaseEditor /></QueryClientProvider>)
    const input = screen.getByRole('textbox', { name: 'Answer' })
    fireEvent.change(input, { target: { value: 'First draft' } })
    fireEvent.blur(input)
    await act(async () => {})
    expect(input).toBeEnabled()
    fireEvent.change(input, { target: { value: 'Newer draft' } })
    fireEvent.blur(input)
    expect(screen.queryByRole('button', { name: 'Accept response' })).not.toBeInTheDocument()
    expect(saveResponse).toHaveBeenCalledTimes(1)
    await act(async () => finish({ ...sampleCase, revision: 3, responses: [{ ...response, value: 'First draft' }] }))
    expect(input).toHaveValue('Newer draft')
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(saveResponse).toHaveBeenLastCalledWith('case-1', 'answer', expect.objectContaining({ value: 'Newer draft', expected_revision: 3 }))
    expect(acceptResponse).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Accept response' }))
    await act(async () => {})
    expect(acceptResponse).toHaveBeenCalledWith('case-1', 'answer', 4)
  })

  it('locks case metadata controls while their save is unresolved', async () => {
    let finish!: (value: PreparationCase) => void
    updateCase.mockReset().mockImplementationOnce(
      () =>
        new Promise<PreparationCase>((resolve) => {
          finish = resolve
        }),
    )
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        <CaseDetail
          item={sampleCase}
          canEdit
          canManage
          users={[]}
          projects={[]}
          jurisdictionName={() => 'Denmark'}
          onBack={vi.fn()}
        />
      </QueryClientProvider>,
    )
    const disclosure = screen.getByText('Form details').closest('details')
    expect(disclosure).not.toHaveAttribute('open')
    expect(
      screen.getByText('Owner: Unassigned · Deadline: None'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByText('Form details'))
    fireEvent.change(screen.getByRole('textbox', { name: 'Form name' }), {
      target: { value: 'Changed case' },
    })
    fireEvent.click(screen.getByText('Form details'))
    fireEvent.click(screen.getByText('Form details'))
    expect(screen.getByRole('textbox', { name: 'Form name' })).toHaveValue(
      'Changed case',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Save form details' }))
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Form name' })).toBeDisabled(),
    )
    expect(screen.getByRole('combobox', { name: 'Owner' })).toBeDisabled()
    expect(screen.getByLabelText('Deadline')).toBeDisabled()
    await act(async () =>
      finish({ ...sampleCase, name: 'Changed case', revision: 3 }),
    )
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Form name' })).toBeEnabled(),
    )
  })

  it('labels fully accepted preparation as ready for handover', () => {
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        <CaseDetail
          item={{
            ...sampleCase,
            readiness: {
              ...sampleCase.readiness,
              ready: true,
              accepted_count: 1,
              answered_count: 1,
            },
          }}
          canEdit={false}
          canManage={false}
          users={[]}
          projects={[]}
          jurisdictionName={() => 'Denmark'}
          onBack={vi.fn()}
        />
      </QueryClientProvider>,
    )
    expect(screen.getByText('Required answers accepted')).toBeInTheDocument()
  })

  it('shows and removes selected archived evidence even when search omits it', async () => {
    getEvidence.mockReset().mockResolvedValue(archivedEvidence)
    searchEvidence.mockReset().mockResolvedValue({ items: [], total: 1000 })
    const writes = draftWrites()
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        {renderField(writes, { ...response, evidence_ids: ['ev-old'] })}
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Archived note')).toBeInTheDocument()
    expect(screen.getByText('Archived note').closest('li')).toHaveTextContent(
      'Archived',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    await waitFor(() => expect(searchEvidence).toHaveBeenCalled())
    fireEvent.click(
      screen.getByRole('button', { name: 'Remove Archived note' }),
    )
    fireEvent.blur(screen.getByRole('textbox', { name: 'Answer' }))
    await waitFor(() =>
      expect(writes.saveField).toHaveBeenCalledWith(
        'answer',
        expect.objectContaining({ evidence_ids: [] }),
        expect.any(Function),
      ),
    )
  })

  it('exposes selected evidence content and authenticated file download to readers', async () => {
    getEvidence.mockReset().mockImplementation((id: string) =>
      Promise.resolve(
        id === 'ev-old'
          ? archivedEvidence
          : {
              ...archivedEvidence,
              id: 'ev-file',
              title: 'Audit file',
              kind: 'file',
              filename: 'audit.pdf',
              body: 'File description',
              archived: false,
            },
      ),
    )
    download.mockReset().mockResolvedValue(undefined)
    const client = makeClient()
    render(
      <QueryClientProvider client={client}>
        <EvidenceAttachments ids={['ev-old', 'ev-file']} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Archived note')).toBeInTheDocument()
    expect(await screen.findByText('Audit file')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /Remove/ }),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByText('View note or description')[0])
    expect(screen.getByText('Past supporting context')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Download' }))
    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(
        'evidence/ev-file/download',
        'audit.pdf',
      ),
    )
  })

  it('links reused provenance and reports acceptance accurately', () => {
    const writes = draftWrites()
    const client = makeClient()
    const reused = {
      ...response,
      value: 'Copied answer',
      reused_from_case_id: 'source-1',
      reused_from_field_key: 'origin',
    }
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{renderField(writes, reused)}</MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByRole('link', { name: 'source case' })).toHaveAttribute(
      'href',
      '/preparation?case=source-1',
    )
    expect(screen.getByText(/Pending review for this case/)).toBeInTheDocument()
    view.rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          {renderField(writes, {
            ...reused,
            accepted_at: '2026-09-29T12:00:00Z',
          })}
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText(/Accepted for this case/)).toBeInTheDocument()
  })
})

it('keeps question order when a source form repeats a section heading', () => {
  const fields = [
    { ...field, key: 'one', label: '1. First question', section: 'Applicant' },
    { ...field, key: 'two', label: '2. Second question', section: 'Operations' },
    { ...field, key: 'three', label: '3. Third question', section: 'Applicant' },
  ]
  render(<QueryClientProvider client={makeClient()}><CaseDetail item={{ ...sampleCase, fields, responses: [] }} canEdit canManage={false} users={[]} projects={[]} jurisdictionName={() => 'Denmark'} onBack={vi.fn()} /></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'View all questions' }))
  expect(screen.getAllByRole('textbox').filter((input) => input.hasAttribute('aria-labelledby')).map((input) => input.getAttribute('aria-labelledby')).map((id) => document.getElementById(id!)?.textContent)).toEqual(['1. First question', '2. Second question', '3. Third question'])
})
