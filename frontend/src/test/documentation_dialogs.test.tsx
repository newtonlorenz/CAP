import { useState } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import api from '../api/client'
import RegisterOwnerPicker from '../components/documentation/RegisterOwnerPicker'
import AuditorRequests from '../components/documentation/AuditorRequests'
import RegisterProcessPicker from '../components/documentation/RegisterProcessPicker'
import ProcessTargetPicker from '../components/documentation/ProcessTargetPicker'
import SpreadsheetImport from '../components/documentation/SpreadsheetImport'
import { SharedEvidenceDialog } from '../components/review/ReviewSharedEvidence'
import type { DocumentationExpectation, DocumentationRegister } from '../types/documentation'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

const register: DocumentationRegister = { id: 'register', name: 'Synthetic register', jurisdiction_id: 'jurisdiction',
  revision: 1, description: null, process: null, access: { visibility: 'secret', permissions: ['view', 'edit'], revision: 1 } }
const target = { kind: 'review_item', available: true, review_item_id: 'item', review_cycle_id: 'cycle',
  requirement_id: 'requirement', requirement_set_version_id: 'version', reference_id: 'SCP-1', title: 'Expected governance' }
const row = { id: 'row', register_id: register.id, revision: 1, source_reference: 'SCP-1', process_targets: [] } as unknown as DocumentationExpectation
const evidence = { id: 'evidence', title: 'Synthetic policy', kind: 'note', body: 'Synthetic policy content', archived: false }
const state = (rationale: string, changedAt: string) => ({ items: [{ evidence_id: evidence.id, title: evidence.title,
  kind: 'note', locator: 'Section 2', rationale, problems: [] }], evidence_changed_at: changedAt })
const preview = { id: 'preview', revision: 1, filename: 'synthetic.xlsx', input_fingerprint: 'a'.repeat(64),
  sheets: [{ name: 'Policies', header_row: 1, headers: ['Document / record required', 'SCP reference', 'Comment/explanation', 'Document'], warnings: [] }],
  rows: [{ key: 'Policies:2', sheet: 'Policies', row_number: 2, title: 'Synthetic imported policy',
    description: '', category: 'Policies', source_reference: 'SCP-1', metadata: {}, candidate_expectation_ids: [] }] }

type DialogKind = 'process' | 'mapping' | 'import' | 'evidence' | 'owner'

function Host({ kind, initialRow = row }: { kind: DialogKind; initialRow?: DocumentationExpectation }) {
  const [open, setOpen] = useState(true)
  const close = () => setOpen(false)
  return !open ? <p>Dialog closed</p> : kind === 'process' ? <RegisterProcessPicker register={register} onClose={close} onSaved={close} />
    : kind === 'mapping' ? <ProcessTargetPicker row={row} onClose={close} onSaved={close} />
      : kind === 'import' ? <SpreadsheetImport register={register} onClose={close} onImported={() => undefined} />
        : kind === 'owner' ? <RegisterOwnerPicker row={initialRow} onClose={close} onSaved={close} />
          : <SharedEvidenceDialog cycleId="cycle" itemId="item" onClose={close} />
}

function mount(kind: DialogKind, initialRow?: DocumentationExpectation) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
    <MemoryRouter><Host kind={kind} initialRow={initialRow} /></MemoryRouter>
  </QueryClientProvider>)
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.get).mockImplementation(async url => {
    if (url === '/users/mentions?limit=1000') return { data: { items: [
      { id: 'user-a', full_name: 'Synthetic Alice' }, { id: 'user-b', full_name: 'Synthetic Bob' },
    ], total: 2 } }
    if (url === '/documentation/registers/register/process-options') return { data: {
      review_cycles: { items: [{ kind: 'review', id: 'cycle', name: 'Synthetic assessment', available: true }], total: 1 },
      applications: { items: [], total: 0 },
    } }
    if (url === '/documentation/expectations/row/process-targets') return { data: { items: [target], total: 1 } }
    if (url === '/documentation/registers/register/expectations') return { data: { items: [], total: 0 } }
    if (url === '/review-cycles/cycle/items/item/shared-evidence') return { data: state('Original explanation', '2026-10-14T10:00:00Z') }
    if (new URL(url, 'http://synthetic.test').pathname === '/preparation/evidence') return { data: { items: [evidence], total: 1 } }
    throw new Error(`Unexpected synthetic API read: ${url}`)
  })
  vi.mocked(api.post).mockResolvedValue({ data: preview })
})
afterEach(cleanup)

it('distinguishes repeated process references by wording, source, section and version and saves only the chosen identity', async () => {
  const first = { ...target, title: target.reference_id, set_name: 'Synthetic SCP 02 · Annex A', version_number: 4,
    owner_name: 'Synthetic Alice', process_name: 'Synthetic certification review',
    requirement_text: 'Retain an oversight record.\nInclude each approved decision.', requirement_text_truncated: true,
    requirement_context: [{ reference_id: '3', title: 'Governance' }, { reference_id: '3.1', title: 'Decision records' }],
    href: '/review-cycles/cycle?mode=focus&item=item' }
  const second = { ...first, review_item_id: 'other-item', requirement_id: 'other-requirement',
    requirement_set_version_id: 'other-version', version_number: 2, set_name: 'Synthetic SCP 07 · Annex B',
    requirement_text: 'Retain a supplier register.', requirement_text_truncated: false, requirement_context: [],
    href: '/review-cycles/cycle?mode=focus&item=other-item' }
  vi.mocked(api.get).mockResolvedValue({ data: { items: [first, second], total: 2 } })
  vi.mocked(api.put).mockRejectedValueOnce(new Error('Synthetic save failure')).mockResolvedValueOnce({ data: row })
  mount('mapping')
  const firstChoice = await screen.findByRole('checkbox', { name: /Retain an oversight record/ })
  const secondChoice = screen.getByRole('checkbox', { name: /Retain a supplier register/ })
  expect(screen.getByText('3 Governance › 3.1 Decision records')).toBeInTheDocument()
  expect(screen.getByText('Synthetic SCP 02 · Annex A · Version 4')).toBeInTheDocument()
  expect(screen.getByText('Synthetic SCP 07 · Annex B · Version 2')).toBeInTheDocument()
  expect(screen.getAllByText('Owner: Synthetic Alice')).toHaveLength(2)
  expect(screen.getAllByText('Assessment requirement · Synthetic certification review')).toHaveLength(2)
  const fullRequirement = screen.getAllByRole('link', { name: 'Open full requirement (new tab)' })[0]
  expect(fullRequirement).toHaveAttribute('href', first.href)
  expect(fullRequirement).toHaveAttribute('target', '_blank')
  expect(screen.getByText('Wording preview. Open the full requirement to read all text.')).toBeInTheDocument()
  fireEvent.click(firstChoice)
  fireEvent.click(secondChoice)
  fireEvent.click(firstChoice)
  expect(firstChoice).not.toBeChecked()
  expect(secondChoice).toBeChecked()
  expect(screen.getByRole('heading', { name: 'Selected references (1)' })).toBeInTheDocument()
  const save = screen.getByRole('button', { name: 'Save reference matches' })
  fireEvent.click(save)
  await screen.findByRole('alert')
  expect(secondChoice).toBeChecked()
  fireEvent.click(save)
  await screen.findByText('Dialog closed')
  expect(vi.mocked(api.put).mock.calls[1]).toEqual(['/documentation/expectations/row/process-targets', {
    revision: 1, targets: [{ review_item_id: 'other-item', requirement_id: 'other-requirement', requirement_set_version_id: 'other-version' }],
  }])
})

it('renders every audit reconciliation category and links unreviewed rows and unsuitable request evidence to their owners', async () => {
  const entry = { ...row, title: 'Synthetic policy awaiting review' }
  const request = { id: 'request', revision: 1, case_id: 'audit-form', case_name: 'Synthetic audit form',
    field_key: 'policy_request', project_id: 'project', request_id: 'AUD-1', request_wording: 'Provide the policy',
    list_revision: 'v1', due_date: null, period: null, direction: 'operator_input', expectations: [],
    evidence: [{ id: evidence.id, title: evidence.title, problems: ['expired'] }], unmatched: false }
  vi.mocked(api.get).mockImplementation(async url => {
    if (url === '/documentation/registers/register/reconciliation') return { data: {
      requests_without_matches: [], missing_evidence: [], partial_coverage: [], unreviewed_coverage: [entry],
      requests_with_unsuitable_evidence: [request], unsuitable_evidence: [], expectations_absent_from_requests: [],
      notice: 'Audit omissions are scope gaps, not compliance decisions.',
    } }
    if (url === '/documentation/registers/register/auditor-requests') return { data: { items: [], total: 0 } }
    if (url === '/documentation/registers/register/audit-fields') return { data: { cases: [] } }
    throw new Error(`Unexpected synthetic API read: ${url}`)
  })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>
    <MemoryRouter><AuditorRequests register={register} projectId="project" canEdit={false} /></MemoryRouter>
  </QueryClientProvider>)
  await screen.findByText('Audit omissions are scope gaps, not compliance decisions.')
  for (const heading of ['Requests without matches (0)', 'Expectations missing evidence (0)', 'Partial coverage (0)',
    'Unreviewed coverage (1)', 'Requests with stale, expired or unavailable evidence (1)',
    'Stale, expired or unavailable evidence (0)', 'Obligations omitted from this audit list (0)']) {
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
  }
  expect(screen.getByRole('link', { name: entry.title })).toHaveAttribute('href',
    '/certification-projects?project=project&section=documentation&register=register&docSection=all&expectation=row')
  expect(screen.getByRole('link', { name: 'AUD-1: Provide the policy' })).toHaveAttribute('href',
    '/preparation?case=audit-form&field=policy_request')
})

it.each(['process', 'mapping', 'import', 'owner'] as const)('keeps a %s draft after local dismissal until discard is explicit', async kind => {
  mount(kind)
  if (kind === 'owner') {
    const owner = await screen.findByRole('combobox', { name: 'Owner' })
    await within(owner).findByRole('option', { name: 'Synthetic Bob' })
    fireEvent.change(owner, { target: { value: 'user-b' } })
  }
  if (kind === 'process') fireEvent.click(await screen.findByRole('radio', { name: 'Synthetic assessment' }))
  if (kind === 'mapping') fireEvent.click(await screen.findByRole('checkbox', { name: /SCP-1/ }))
  if (kind === 'import') {
    fireEvent.change(screen.getByLabelText('Documentation spreadsheet', { exact: true }), {
      target: { files: [new File(['synthetic contents'], 'synthetic.xlsx')] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Preview spreadsheet' }))
    await screen.findByRole('heading', { name: 'Synthetic imported policy' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Import action for row 2 in Policies' }), { target: { value: 'skip' } })
  }
  if (kind === 'mapping') fireEvent.keyDown(window, { key: 'Escape' })
  else fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  const confirmation = await screen.findByRole('dialog', { name: 'Discard unsaved changes?' })
  expect(screen.queryByText('Dialog closed')).not.toBeInTheDocument()
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Discard unsaved changes?' })).not.toBeInTheDocument())
  if (kind === 'owner') expect(screen.getByRole('combobox', { name: 'Owner' })).toHaveValue('user-b')
  if (kind === 'process') expect(screen.getByRole('radio', { name: 'Synthetic assessment' })).toBeChecked()
  if (kind === 'mapping') expect(screen.getByRole('checkbox', { name: /SCP-1/ })).toBeChecked()
  if (kind === 'import') expect(screen.getByRole('combobox', { name: 'Import action for row 2 in Policies' })).toHaveValue('skip')
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Discard unsaved changes?' })).getByRole('button', { name: 'Discard changes' }))
  expect(await screen.findByText('Dialog closed')).toBeInTheDocument()
  expect(api.put).not.toHaveBeenCalled()
  expect(api.patch).not.toHaveBeenCalled()
})

it.each(['keep', 'current'] as const)('requires explicit comparison after an evidence conflict before choosing %s links', async choice => {
  let loaded = false
  vi.mocked(api.get).mockImplementation(async url => {
    if (new URL(url, 'http://synthetic.test').pathname === '/preparation/evidence') return { data: { items: [evidence], total: 1 } }
    if (url === '/review-cycles/cycle/items/item/shared-evidence') {
      const data = loaded ? state('Concurrent server explanation', '2026-10-14T11:00:00Z') : state('Original explanation', '2026-10-14T10:00:00Z')
      loaded = true
      return { data }
    }
    throw new Error(`Unexpected synthetic API read: ${url}`)
  })
  vi.mocked(api.put).mockRejectedValueOnce(Object.assign(new Error('Concurrent source change'), {
    isAxiosError: true, response: { status: 409, data: { detail: 'Concurrent source change' } },
  })).mockResolvedValueOnce({ data: state('My preserved explanation', '2026-10-14T12:00:00Z') })
  mount('evidence')
  const explanation = await screen.findByRole('textbox', { name: 'Assessment explanation' })
  fireEvent.change(explanation, { target: { value: 'My preserved explanation' } })
  const save = screen.getByRole('button', { name: 'Save evidence links' })
  fireEvent.click(save)
  await screen.findByRole('button', { name: 'Load current evidence links' })
  expect(explanation).toHaveValue('My preserved explanation')
  expect(save).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Load current evidence links' }))
  await screen.findByText(/Concurrent server explanation/)
  expect(explanation).toHaveValue('My preserved explanation')
  expect(save).toBeDisabled()
  if (choice === 'keep') {
    fireEvent.click(screen.getByRole('button', { name: 'Keep reviewed evidence selections' }))
    expect(save).toBeEnabled()
    fireEvent.click(save)
    await screen.findByText('Dialog closed')
    expect(vi.mocked(api.put).mock.calls[1][1]).toEqual({ expected_evidence_changed_at: '2026-10-14T11:00:00Z',
      links: [{ evidence_id: evidence.id, locator: 'Section 2', rationale: 'My preserved explanation' }] })
  } else {
    fireEvent.click(screen.getByRole('button', { name: 'Use current evidence links' }))
    expect(explanation).toHaveValue('Concurrent server explanation')
    expect(save).toBeDisabled()
    expect(api.put).toHaveBeenCalledTimes(1)
  }
})

it.each(['update', 'create', 'skip'] as const)('rejects repeated import-target pages and submits only the target appropriate to the final %s choice', async action => {
  let retry = false
  let reads = 0
  const first = { id: 'existing-first', title: 'Existing first row', revision: 4 }
  const second = { id: 'existing-second', title: 'Existing second row', revision: 7 }
  vi.mocked(api.get).mockImplementation(async url => {
    if (url !== '/documentation/registers/register/expectations') throw new Error(`Unexpected synthetic API read: ${url}`)
    const item = reads++ % 2 === 0 || !retry ? first : second
    return { data: { items: [item], total: 2 } }
  })
  vi.mocked(api.post).mockImplementation(async url => ({ data: url.endsWith('/preview') ? preview : {
    created: action === 'create' ? 1 : 0, updated: action === 'update' ? 1 : 0, skipped: action === 'skip' ? 1 : 0, repeated: 0,
  } }))
  mount('import')
  fireEvent.change(screen.getByLabelText('Documentation spreadsheet'), {
    target: { files: [new File(['synthetic contents'], 'synthetic.xlsx')] },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Preview spreadsheet' }))
  await screen.findByRole('heading', { name: 'Synthetic imported policy' })
  fireEvent.change(screen.getByRole('combobox', { name: 'Import action for row 2 in Policies' }), { target: { value: 'update' } })
  await screen.findByRole('button', { name: 'Retry existing rows' })
  const targets = screen.getByRole('combobox', { name: 'Update target for row 2 in Policies' })
  expect(within(targets).queryByRole('option', { name: 'Existing first row' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Confirm import' })).toBeDisabled()
  retry = true
  reads = 0
  fireEvent.click(screen.getByRole('button', { name: 'Retry existing rows' }))
  await within(targets).findByRole('option', { name: 'Existing second row' })
  expect(screen.getByRole('combobox', { name: 'Import action for row 2 in Policies' })).toHaveValue('update')
  fireEvent.change(targets, { target: { value: second.id } })
  if (action !== 'update') {
    fireEvent.change(screen.getByRole('combobox', { name: 'Import action for row 2 in Policies' }), { target: { value: action } })
    expect(screen.queryByRole('combobox', { name: 'Update target for row 2 in Policies' })).not.toBeInTheDocument()
  }
  fireEvent.click(screen.getByRole('checkbox', { name: 'I reviewed the worksheet mappings, duplicate choices, and unresolved source references.' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm import' }))
  await screen.findByText(`Import complete. ${action === 'create' ? 1 : 0} created, ${action === 'update' ? 1 : 0} updated, ${action === 'skip' ? 1 : 0} skipped, 0 already imported.`)
  expect(vi.mocked(api.post).mock.calls[1][1]).toEqual({ revision: 1, choices: [action === 'update'
    ? { row_key: 'Policies:2', action: 'update', expectation_id: second.id, expectation_revision: second.revision }
    : { row_key: 'Policies:2', action }] })
})


it.each([
  { action: 'assign', initial: null, expected: 'user-b' },
  { action: 'clear', initial: 'user-a', expected: null },
])('saves an optional row owner when choosing $action without sending unrelated row changes', async ({ action, initial, expected }) => {
  vi.mocked(api.patch).mockResolvedValue({ data: { ...row, owner_id: expected, revision: 2 } })
  mount('owner', { ...row, owner_id: initial, owner_name: initial ? 'Synthetic Alice' : undefined })
  const owner = await screen.findByRole('combobox', { name: 'Owner' })
  await within(owner).findByRole('option', { name: 'Synthetic Bob' })
  expect(owner).toHaveValue(initial || '')
  if (action === 'assign') fireEvent.change(owner, { target: { value: 'user-b' } })
  else fireEvent.click(screen.getByRole('button', { name: 'Clear assignment' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save assignment' }))
  await screen.findByText('Dialog closed')
  expect(api.patch).toHaveBeenCalledWith('/documentation/expectations/row', { revision: 1, owner_id: expected })
})

it.each(['keep', 'current'] as const)('preserves an owner draft on conflict until the user explicitly chooses %s assignment', async choice => {
  const originalRead = vi.mocked(api.get).getMockImplementation()!
  vi.mocked(api.get).mockImplementation(async (url, config) => url === '/documentation/expectations/row'
    ? { data: { ...row, revision: 4, owner_id: 'user-a', owner_name: 'Synthetic Alice' } }
    : originalRead(url, config))
  vi.mocked(api.patch).mockRejectedValueOnce(Object.assign(new Error('Concurrent row assignment'), {
    isAxiosError: true, response: { status: 409, data: { detail: 'Concurrent row assignment' } },
  })).mockResolvedValueOnce({ data: { ...row, revision: 5, owner_id: 'user-b', owner_name: 'Synthetic Bob' } })
  mount('owner', { ...row, owner_id: null })
  const owner = await screen.findByRole('combobox', { name: 'Owner' })
  await within(owner).findByRole('option', { name: 'Synthetic Bob' })
  fireEvent.change(owner, { target: { value: 'user-b' } })
  const save = screen.getByRole('button', { name: 'Save assignment' })
  fireEvent.click(save)
  await screen.findByRole('button', { name: 'Load current assignment' })
  expect(owner).toHaveValue('user-b')
  expect(save).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'Keep reviewed assignment' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load current assignment' }))
  await screen.findByText('Current owner: Synthetic Alice')
  expect(screen.getByText('Your selection: Synthetic Bob')).toBeInTheDocument()
  expect(owner).toHaveValue('user-b')
  expect(save).toBeDisabled()
  if (choice === 'keep') {
    fireEvent.click(screen.getByRole('button', { name: 'Keep reviewed assignment' }))
    expect(save).toBeEnabled()
    fireEvent.click(save)
    await screen.findByText('Dialog closed')
    expect(api.patch).toHaveBeenLastCalledWith('/documentation/expectations/row', { revision: 4, owner_id: 'user-b' })
  } else {
    fireEvent.click(screen.getByRole('button', { name: 'Use current assignment' }))
    expect(owner).toHaveValue('user-a')
    expect(save).toBeDisabled()
    expect(api.patch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await screen.findByText('Dialog closed')
  }
})
