import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import RequirementsImport from '../components/preparation/RequirementsImport'
import { preparationApi } from '../api/preparation'
import type { PreparationField, PreparationRequirementsPreview } from '../types/preparation'

vi.mock('../api/preparation', () => ({ preparationApi: { requirementSets: vi.fn(), requirementVersions: vi.fn(), requirementsPreview: vi.fn() } }))

const source: PreparationRequirementsPreview['source'] = {
  kind: 'extracted_requirements', document_id: 'annex-a', name: 'Annex A', status: 'draft', jurisdiction_id: 'dk',
  version_id: null, version_number: null, version_status: null, has_source: true, extraction_run_id: 'extraction-a', extraction_status: 'completed',
}
const field = (index: number): PreparationField => ({
  key: `extracted_${index}`, label: `${index}. Describe control ${index}`, section: index < 100 ? 'Technical controls' : 'Reporting',
  help_text: index === 101 ? 'Retain the complete source instruction. '.repeat(80) : null,
  type: 'multiline', required: true, options: [], reuse_key: null,
  source: {
    kind: 'extracted_requirement', document_id: 'annex-a', document_name: 'Annex A', document_status: 'draft', jurisdiction_id: 'dk',
    requirement_id: null, extracted_requirement_id: `extracted-${index}`, requirement_set_version_id: null, version_number: null, version_status: null,
    reference_id: String(index), source_extraction_id: `extracted-${index}`, extraction_run_id: 'extraction-a', extraction_status: 'completed', extraction_review_status: 'pending', text_sha256: 'a'.repeat(64),
  },
})
function sourceField(index: number, snapshot: PreparationRequirementsPreview['source']): PreparationField {
  const question = field(index)
  const identity = snapshot.kind === 'requirements' ? snapshot.version_id : snapshot.extraction_run_id
  return { ...question, key: `${identity}_${index}`, source: {
    ...question.source!,
    kind: snapshot.kind === 'requirements' ? 'requirement' : 'extracted_requirement',
    requirement_id: snapshot.kind === 'requirements' ? `${identity}-requirement-${index}` : null,
    extracted_requirement_id: snapshot.kind === 'extracted_requirements' ? `${identity}-extracted-${index}` : null,
    requirement_set_version_id: snapshot.version_id, version_number: snapshot.version_number, version_status: snapshot.version_status,
    extraction_run_id: snapshot.extraction_run_id, extraction_status: snapshot.extraction_status,
  } }
}
function renderImport(props: Partial<ComponentProps<typeof RequirementsImport>> = {}) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RequirementsImport jurisdictionId="dk" existing={[]} onImport={vi.fn()} initialOpen {...props} /></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(preparationApi.requirementSets).mockResolvedValue({ items: [{ document_id: 'annex-a', jurisdiction_id: 'dk', name: 'Annex A', filename: 'annex-a.pdf', document_type: 'annex', document_status: 'draft', archived_at: null, requirements_total: 0, requirements_active: 0 }], total: 1 })
  vi.mocked(preparationApi.requirementVersions).mockResolvedValue({ items: [], total: 0 })
})

it.each([
  { kind: 'requirement version', initial: { ...source, kind: 'requirements' as const, version_id: 'version-1', version_number: 1, version_status: 'approved', extraction_run_id: null, extraction_status: null }, replacement: { ...source, kind: 'requirements' as const, version_id: 'version-2', version_number: 2, version_status: 'draft', extraction_run_id: null, extraction_status: null } },
  { kind: 'PDF extraction', initial: source, replacement: { ...source, extraction_run_id: 'extraction-b' } },
])('clears a replaced $kind during pagination and imports only the new selected source in order', async ({ initial, replacement }) => {
  let currentSource = initial
  vi.mocked(preparationApi.requirementsPreview).mockImplementation(async ({ skip = 0 }) => ({
    source: currentSource, fields: Array.from({ length: skip === 0 ? 100 : 2 }, (_, index) => sourceField(skip + index + 1, currentSource)), unavailable: [], total: 102, skip, limit: 100, warnings: [],
  }))
  const imported = vi.fn(), dirty = vi.fn()
  renderImport({ existing: Array.from({ length: 400 }, (_, index) => ({ ...field(index), key: `existing_${index}` })), onImport: imported, onDirtyChange: dirty })
  await screen.findByRole('option', { name: 'Annex A · Draft' })
  fireEvent.change(screen.getByLabelText('Requirement set in this jurisdiction'), { target: { value: 'annex-a' } })
  expect(await screen.findByText('0 selected · 100 available spaces')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add selected questions to form' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Next points' }))
  await screen.findByText('Points 101–102 of 102')
  fireEvent.click(screen.getByRole('checkbox', { name: /101\. Describe control 101/ }))
  expect(screen.getByText('2 selected · 100 available spaces')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Previous points' }))
  await waitFor(() => expect(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ })).toBeEnabled())
  currentSource = replacement
  fireEvent.click(screen.getByRole('button', { name: 'Next points' }))
  await screen.findByText(/The source changed while you were browsing/)
  await waitFor(() => expect(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ })).toBeEnabled())
  expect(screen.getByText('0 selected · 100 available spaces')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add selected questions to form' })).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ })).not.toBeChecked()
  fireEvent.click(screen.getByRole('button', { name: 'Next points' }))
  await screen.findByText('Points 101–102 of 102')
  await waitFor(() => expect(screen.getByRole('checkbox', { name: /101\. Describe control 101/ })).toBeEnabled())
  fireEvent.click(screen.getByRole('checkbox', { name: /101\. Describe control 101/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Previous points' }))
  await screen.findByText('Points 1–100 of 102')
  await waitFor(() => expect(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ })).toBeEnabled())
  fireEvent.click(screen.getByRole('checkbox', { name: /1\. Describe control 1$/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Add 2 selected questions to form' }))
  expect(imported).toHaveBeenCalledWith([sourceField(1, replacement), sourceField(101, replacement)], replacement)
  await waitFor(() => expect(dirty).toHaveBeenLastCalledWith(false))
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
}, 10_000)

it('keeps default extraction separate from an explicitly selected empty version and clears prior selections', async () => {
  vi.mocked(preparationApi.requirementVersions).mockResolvedValue({ items: [
    { id: 'approved', organization_id: null, document_id: 'annex-a', version_number: 1, status: 'approved', is_current: true, based_on_version_id: null, change_summary: null, created_by: 'author', approved_by: 'reviewer', created_at: '', approved_at: '', locked_at: '' },
    { id: 'draft', organization_id: null, document_id: 'annex-a', version_number: 2, status: 'draft', is_current: false, based_on_version_id: 'approved', change_summary: null, created_by: 'author', approved_by: null, created_at: '', approved_at: null, locked_at: null },
  ], total: 2 })
  const approvedQuestion: PreparationField = { ...field(1), key: 'req_1', source: {
    ...field(1).source!, kind: 'requirement', requirement_id: 'requirement-1', extracted_requirement_id: null,
    requirement_set_version_id: 'approved', version_number: 1, version_status: 'approved', extraction_run_id: null,
    extraction_status: null, extraction_review_status: null,
  } }
  vi.mocked(preparationApi.requirementsPreview).mockImplementation(async ({ version_id }) => {
    if (!version_id) return { source, fields: [field(2)], unavailable: [], total: 1, skip: 0, limit: 100, warnings: [] }
    return {
      source: { ...source, kind: 'requirements', version_id, version_number: version_id === 'draft' ? 2 : 1, version_status: version_id === 'draft' ? 'draft' : 'approved', extraction_run_id: null },
      fields: version_id === 'draft' ? [] : [approvedQuestion], unavailable: [], total: version_id === 'draft' ? 0 : 1, skip: 0, limit: 100, warnings: [],
    }
  })
  const imported = vi.fn()
  renderImport({ onImport: imported })
  await screen.findByRole('option', { name: 'Annex A · Draft' })
  fireEvent.change(screen.getByLabelText('Requirement set in this jurisdiction'), { target: { value: 'annex-a' } })
  await screen.findByText(/Extracted PDF text.*Awaiting requirement review/)
  fireEvent.change(screen.getByLabelText('Source version'), { target: { value: 'draft' } })
  await screen.findByText('Source v2 · Draft')
  expect(screen.getByText(/No active questions in this source version/)).toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Add selected questions to form' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Source version'), { target: { value: 'approved' } })
  await screen.findByText('Source v1 · Approved')
  fireEvent.click(screen.getByRole('button', { name: 'Add 1 selected questions to form' }))
  expect(imported).toHaveBeenCalledWith([approvedQuestion], expect.objectContaining({ version_id: 'approved', version_status: 'approved' }))
  expect(JSON.stringify(imported.mock.calls)).not.toContain('Describe control 2')
})
