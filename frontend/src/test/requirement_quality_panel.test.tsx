import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import RequirementQualityPanel from '../components/requirements/RequirementQualityPanel'
import api from '../api/client'
vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), defaults: { baseURL: '/api/v1' } } }))
const props = { documentId: 'document-a', hasSource: true, archived: false, enabled: true, revision: 4, canManage: true, currentExtractionId: 'extraction-current', documentStatus: 'approved' }
const run = { id: 'run-a', status: 'partial', mode: 'recheck', model: 'jev-1.13.0', coverage: { checked: 2, total: 5, source_blocks_checked: 3, source_blocks_total: 8 }, usage: {}, warnings: ['Source check budget exhausted'], findings: [] }
function show(overrides: Partial<typeof props> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><p>Ordinary requirements remain editable</p><RequirementQualityPanel {...props} {...overrides} /></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.get).mockImplementation(async (path) => ({ data: String(path).endsWith('/versions') ? { items: [{ id: 'approved-version', version_number: 2, status: 'approved' }, { id: 'older-version', version_number: 1, status: 'approved' }] } : String(path).endsWith('/run-a') ? run : { items: [] } }) as never)
})
it('keeps ordinary requirements available without Jev or source', () => {
  show({ hasSource: false, enabled: false })
  expect(screen.getByText(/no source PDF/)).toBeInTheDocument()
  expect(screen.getByText(/ordinary import and review remain available/)).toBeInTheDocument()
  expect(screen.getByText('Ordinary requirements remain editable')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Check against source' })).not.toBeInTheDocument()
})
it('requires Jev consent and checks the chosen approved version', async () => {
  vi.mocked(api.post).mockResolvedValue({ data: { ...run, status: 'pending' } })
  show()
  const selector = screen.getByRole('combobox', { name: 'Requirements to check' })
  await waitFor(() => expect(selector).toHaveValue('version:approved-version'))
  const check = screen.getByRole('button', { name: 'Check against source' })
  expect(check).toBeDisabled()
  const consent = screen.getByRole('checkbox', { name: 'Allow source text and requirements to be sent to Jev for this check.' })
  fireEvent.click(consent)
  fireEvent.change(selector, { target: { value: 'version:older-version' } })
  expect(consent).not.toBeChecked()
  expect(check).toBeDisabled()
  fireEvent.click(consent)
  fireEvent.click(check)
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/documents/document-a/quality-runs', { allow_external_ai: true, jev_settings_revision: 4, version_id: 'older-version' }))
})
it('shows partial coverage and source-backed automatic corrections', async () => {
  const detail = { ...run, findings: [{ id: 'finding-a', kind: 'accuracy', requirement_id: 'requirement-a', source_page: 3, source_excerpt: 'The applicant must retain records.', before: { requirement_type: 'recommended' }, after: { requirement_type: 'mandatory' }, applied: true, answers: {} }] }
  vi.mocked(api.get).mockImplementation(async (path) => ({ data: String(path).endsWith('/quality-runs') ? { items: [run] } : String(path).endsWith('/run-a') ? detail : { items: [] } }) as never)
  show()
  expect(await screen.findByText('Check incomplete')).toBeInTheDocument()
  expect(screen.getByText('2 of 5 requirements checked; 3 of 8 source blocks checked.')).toBeInTheDocument()
  expect(screen.getByText('Source check budget exhausted')).toBeInTheDocument()
  fireEvent.click(await screen.findByText('1 findings to review'))
  expect(screen.getByText(/Automatically corrected · needs review/)).toBeInTheDocument()
  expect(screen.getByText(/recommended →/)).toBeInTheDocument()
  expect(screen.getByText('requirement type:').parentElement).toHaveTextContent('mandatory')
  expect(screen.getByRole('link', { name: 'Source page 3' })).toHaveAttribute('href', '/api/v1/documents/document-a/source#page=3')
  expect(screen.getByText('The applicant must retain records.')).toBeInTheDocument()
})
it('cancels the displayed running check', async () => {
  const active = { ...run, status: 'running' }
  vi.mocked(api.get).mockImplementation(async (path) => ({ data: String(path).endsWith('/quality-runs') ? { items: [active] } : String(path).endsWith('/run-a') ? active : { items: [] } }) as never)
  vi.mocked(api.post).mockResolvedValue({ data: { ...run, status: 'cancelled' } })
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel source check' }))
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/documents/document-a/quality-runs/run-a/cancel'))
})
it('retains requirements when history loading fails', async () => {
  vi.mocked(api.get).mockRejectedValue(new Error('History unavailable'))
  show()
  expect(await screen.findByRole('alert')).toHaveTextContent('Source-check history could not be loaded. Your requirements remain available.')
  expect(screen.getByText('Ordinary requirements remain editable')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check against source' })).toBeDisabled()
})


it.each(['document', 'revision'])('ignores a delayed source-check result after changing %s', async (changed) => {
  let finish!: (value: unknown) => void
  vi.mocked(api.post).mockReturnValue(new Promise(resolve => { finish = resolve }) as never)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const panel = (values: typeof props) => <QueryClientProvider client={queryClient}><RequirementQualityPanel {...values} /></QueryClientProvider>
  const view = render(panel(props))
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Requirements to check' })).toHaveValue('version:approved-version'))
  fireEvent.click(screen.getByRole('checkbox', { name: /Allow source text and requirements/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Check against source' }))
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  const next = changed === 'document' ? { ...props, documentId: 'document-b' } : { ...props, revision: 5 }
  view.rerender(panel(next))
  const consent = screen.getByRole('checkbox', { name: /Allow source text and requirements/ })
  expect(consent).not.toBeChecked()
  fireEvent.click(consent)
  await act(async () => { finish({ data: { ...run, id: 'old-delayed-run' } }) })
  expect(consent).toBeChecked()
  expect(screen.queryByText('Check incomplete')).not.toBeInTheDocument()
  expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('old-delayed-run'))
})

it('shows classification and hierarchy uncertainty even when source support is strong', async () => {
  const certain = { choice: 'source-1', confidence: 1, probabilities: { 'source-1': 1 } }
  const finding = { id: 'classification', kind: 'accuracy', requirement_id: 'requirement-a', source_page: 2, source_excerpt: 'Classification needs checking', before: {}, after: {}, applied: false, answers: { supported: { noul: 1 }, source: certain, type: { choice: 'uncertain', confidence: 1, probabilities: { uncertain: 1 } }, parent: { choice: 'root', confidence: 1, probabilities: { root: 1 } } } }
  const hierarchy = { ...finding, id: 'hierarchy', source_excerpt: 'Hierarchy needs checking', answers: { ...finding.answers, type: { choice: 'mandatory', confidence: 1, probabilities: { mandatory: 1 } }, parent: { choice: 'root', confidence: 1, probabilities: { root: .9, other: .1 } } } }
  const detail = { ...run, status: 'completed', findings: [finding, hierarchy] }
  vi.mocked(api.get).mockImplementation(async path => ({ data: String(path).endsWith('/quality-runs') ? { items: [detail] } : String(path).endsWith('/run-a') ? detail : { items: [] } }) as never)
  show()
  fireEvent.click(await screen.findByText('2 findings to review'))
  expect(screen.getByText('Classification needs checking')).toBeInTheDocument()
  expect(screen.getByText('Hierarchy needs checking')).toBeInTheDocument()
})
