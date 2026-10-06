import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Library from '../pages/Library'
import { preparationApi } from '../api/preparation'

vi.mock('../api/preparation', () => ({ preparationApi: {
  templates: vi.fn(), starters: vi.fn(), cases: vi.fn(), importCapabilities: vi.fn(),
  requirementSets: vi.fn(), requirementVersions: vi.fn(), requirementsPreview: vi.fn(),
} }))
vi.mock('../api/client', () => ({ default: { get: vi.fn(async () => ({ data: { items: [], total: 0 } })) } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'manager', role: 'manager' } }) }))
vi.mock('../contexts/JurisdictionContext', () => ({
  useJurisdiction: () => ({
    jurisdictionId: 'dk', jurisdictions: [{ id: 'dk', name: 'Denmark' }], jurisdictionById: { dk: { name: 'Denmark' } },
  }),
}))

function show(query: string) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[`/library?${query}`]}><Library /></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(preparationApi.importCapabilities).mockResolvedValue({ jev: { enabled: false, revision: 0, model: null } })
  vi.mocked(preparationApi.templates).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(preparationApi.starters).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(preparationApi.cases).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(preparationApi.requirementSets).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(preparationApi.requirementVersions).mockResolvedValue({ items: [], total: 0 })
})

it('opens a handed-off draft source as form questions without requiring certification approval', async () => {
  vi.mocked(preparationApi.requirementsPreview).mockResolvedValue({
    source: { document_id: 'annex', name: 'Draft annex', status: 'draft', jurisdiction_id: 'dk', kind: 'extracted_requirements', version_id: null, version_number: null, version_status: null, has_source: true, extraction_run_id: 'extract', extraction_status: 'completed' },
    fields: [{ key: 'company', label: 'Company name', section: 'Applicant', help_text: null, type: 'text', required: true, options: [], reuse_key: null }],
    unavailable: [], total: 1, skip: 0, limit: 100,
    warnings: ['This extracted source has not yet been approved.'],
  })
  show('section=templates&sourceDocument=annex&jurisdiction=dk&kind=licence_application')
  expect(screen.getByRole('heading', { name: 'Form templates', level: 1 })).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Library sections' })).not.toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Resource collections' })).not.toBeInTheDocument()
  expect(await screen.findByRole('checkbox', { name: /Company name/ })).toBeChecked()
  expect(screen.getByText('This extracted source has not yet been approved.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Add 1 selected questions to form' }))
  expect(await screen.findByDisplayValue('Company name')).toBeInTheDocument()
  await waitFor(() => expect(preparationApi.requirementsPreview).toHaveBeenCalledWith(expect.objectContaining({ document_id: 'annex', jurisdiction_id: 'dk' })))
})

it('opens bookmarked standalone forms without an application template restriction', async () => {
  show('section=forms&returnTo=%2Fcertification-projects%3Fproject%3Dproject-1')
  expect(screen.getByRole('heading', { name: 'Existing forms', level: 1 })).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Library sections' })).not.toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Resource collections' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Return to your workspace' })).toHaveAttribute('href', '/certification-projects?project=project-1')
  expect(await screen.findByRole('combobox', { name: 'Kind' })).toBeEnabled()
  expect(screen.getByRole('option', { name: 'All kinds' })).toBeInTheDocument()
})

it.each([
  ['section=evidence', 'Evidence'],
  ['', 'Form templates'],
  ['section=unknown', 'Form templates'],
  ['section=requirements', 'Requirements'],
])('names the bookmarked resource %s without duplicate navigation', (query, heading) => {
  show(query)
  expect(screen.getByRole('heading', { name: heading, level: 1 })).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Library sections' })).not.toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Resource collections' })).not.toBeInTheDocument()
})
