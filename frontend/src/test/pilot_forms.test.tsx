import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AnswerReview from '../pages/AnswerReview'
import ContextualEvidenceUpload from '../components/preparation/ContextualEvidenceUpload'
import type { PilotPreparationCase, ReviewQueueItem } from '../types/pilotReview'

const mocks = vi.hoisted(() => ({ queue: vi.fn(), getCase: vi.fn(), accept: vi.fn(), returnAnswer: vi.fn(), post: vi.fn(), getEvidence: vi.fn() }))
vi.mock('../api/pilotReview', () => ({ pilotReviewApi: { reviewQueue: mocks.queue, getCase: mocks.getCase, acceptResponse: mocks.accept, returnResponse: mocks.returnAnswer, history: vi.fn().mockResolvedValue({ items: [] }) } }))
vi.mock('../api/client', () => ({ default: { post: mocks.post } }))
vi.mock('../api/preparation', () => ({ preparationApi: { getEvidence: mocks.getEvidence, download: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'reviewer-1', role: 'admin' } }) }))
vi.mock('../contexts/JurisdictionContext', () => ({ useJurisdiction: () => ({ jurisdictionId: 'denmark' }) }))

const form: PilotPreparationCase = {
  id: 'form-1', name: 'Ownership declaration', kind: 'licence_application', jurisdiction_id: 'denmark', project_id: null,
  owner_id: 'contributor-1', reviewer_id: 'reviewer-1', reviewer_name: 'Review owner', due_date: null, status: 'active', revision: 7,
  template_id: null, template_name: 'Ownership', template_revision: 1, created_at: '2026-10-01', updated_at: '2026-10-04',
  fields: [{ key: 'ownership', label: 'Describe the ownership structure.', section: 'Ownership', help_text: 'Include beneficial owners and supporting records.', type: 'multiline', required: true, options: [], reuse_key: null }, { key: 'directors', label: 'Name the directors.', section: 'Ownership', help_text: null, type: 'text', required: true, options: [], reuse_key: null }],
  responses: [{ field_key: 'ownership', value: 'The company is owned by its founders.', evidence_ids: [], not_applicable_reason: null, accepted_at: null, accepted_by: null, reused_from_case_id: null, reused_from_field_key: null }, { field_key: 'directors', value: 'Two directors.', evidence_ids: [], not_applicable_reason: null, accepted_at: null, accepted_by: null, reused_from_case_id: null, reused_from_field_key: null }],
  readiness: { required_count: 2, answered_count: 2, accepted_count: 0, blockers: [], ready: false },
}
const rows: ReviewQueueItem[] = form.fields.map(field => ({ case_id: form.id, case_name: form.name, jurisdiction_id: 'denmark', field_key: field.key, question: field.label, section: field.section, guidance: field.help_text, revision: 7, review_status: 'pending_review', reviewer_id: 'reviewer-1', reviewer_name: 'Review owner', owner_id: 'contributor-1', owner_name: 'Contributor', due_date: null, last_saved_at: null, last_saved_by: null, open_feedback_count: 0, can_approve: true }))
const show = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/answer-review']}><AnswerReview /></MemoryRouter></QueryClientProvider>)
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); mocks.queue.mockResolvedValue({ items: rows, total: 2, skip: 0, limit: 10 }); mocks.getCase.mockResolvedValue(form) })
afterEach(() => { vi.restoreAllMocks() })

describe('answer review decisions', () => {
  it('shows the exact question and guidance and advances only after acceptance acknowledgement', async () => {
    let acknowledge!: (value: PilotPreparationCase) => void
    mocks.accept.mockImplementation(() => new Promise(resolve => { acknowledge = resolve }))
    show()
    await screen.findByRole('heading', { name: 'Describe the ownership structure.' })
    expect(screen.getByText('Include beneficial owners and supporting records.')).toBeVisible()
    expect(screen.getByText('The company is owned by its founders.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Accept answer & next' }))
    expect(mocks.accept).toHaveBeenCalledWith('form-1', 'ownership', 7)
    expect(screen.getByRole('heading', { name: 'Describe the ownership structure.' })).toBeVisible()
    await act(async () => acknowledge({ ...form, revision: 8 }))
    await screen.findByRole('heading', { name: 'Name the directors.' })
    expect(screen.getByText('Answer and attached evidence accepted. Review queue advanced.')).toBeInTheDocument()
  })
  it('requires a comment and sends it with the reviewed revision', async () => {
    mocks.returnAnswer.mockResolvedValue({ ...form, revision: 8 })
    show()
    await screen.findByRole('heading', { name: 'Describe the ownership structure.' })
    fireEvent.click(screen.getByRole('button', { name: 'Return for changes' }))
    expect(screen.getByRole('button', { name: 'Send back for changes' })).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Comment for the contributor' }), { target: { value: 'Please attach the signed ownership chart.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send back for changes' }))
    await waitFor(() => expect(mocks.returnAnswer).toHaveBeenCalledWith('form-1', 'ownership', { expected_revision: 7, comment: 'Please attach the signed ownership chart.' }))
    await screen.findByRole('heading', { name: 'Name the directors.' })
  })
  it('retains the selected answer after a revision conflict and requires fresh review', async () => {
    mocks.accept.mockRejectedValue(new Error('The form changed'))
    show()
    await screen.findByRole('heading', { name: 'Describe the ownership structure.' })
    fireEvent.click(screen.getByRole('button', { name: 'Accept answer & next' }))
    await screen.findByRole('button', { name: 'I have reviewed the latest answer' })
    expect(screen.getByRole('heading', { name: 'Describe the ownership structure.' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Accept answer & next' })).toBeDisabled()
    expect(mocks.getCase).toHaveBeenCalledTimes(2)
  })
  it('keeps page navigation separate from question navigation and makes no decision when skipping', async () => {
    mocks.queue.mockResolvedValue({ items: rows, total: 24, skip: 0, limit: 10 })
    show()
    await screen.findByRole('heading', { name: 'Describe the ownership structure.' })
    fireEvent.click(screen.getByRole('button', { name: 'Next question' }))
    await screen.findByRole('heading', { name: 'Name the directors.' })
    expect(mocks.queue.mock.calls.every(([filters]) => filters.skip === 0)).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Skip for now' }))
    await waitFor(() => expect(mocks.queue).toHaveBeenCalledWith(expect.objectContaining({ skip: 10 })))
    expect(mocks.accept).not.toHaveBeenCalled()
    expect(mocks.returnAnswer).not.toHaveBeenCalled()
  })
})

describe('contextual evidence upload', () => {
  it('merges a completed upload with the latest attachments rather than the upload-start list', async () => {
    let finishUpload!: (value: unknown) => void
    const attach = vi.fn().mockResolvedValue(true)
    mocks.post.mockImplementation(() => new Promise(resolve => { finishUpload = resolve }))
    const view = render(<ContextualEvidenceUpload ids={['original']} disabled={false} attach={attach} />)
    fireEvent.change(screen.getByLabelText('Upload evidence for this answer'), { target: { files: [new File(['chart'], 'New chart.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and attach' }))
    view.rerender(<ContextualEvidenceUpload ids={['original', 'intervening-attachment']} disabled={false} attach={attach} />)
    await act(async () => finishUpload({ data: { id: 'new-upload', filename: 'New chart.pdf', title: 'New chart' } }))
    expect(attach).toHaveBeenCalledWith(['original', 'intervening-attachment', 'new-upload'])
  })
  it('retains the current attachment and retries attachment without uploading twice', async () => {
    const attach = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    mocks.post.mockResolvedValue({ data: { id: 'new-evidence', filename: 'Signed chart.pdf', title: 'Signed chart' } })
    render(<ContextualEvidenceUpload ids={['old-evidence']} disabled={false} attach={attach} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Attachment action' }), { target: { value: 'old-evidence' } })
    fireEvent.change(screen.getByLabelText('Upload evidence for this answer'), { target: { files: [new File(['chart'], 'Signed chart.pdf', { type: 'application/pdf' })] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload replacement and attach' }))
    await screen.findByText(/file uploaded, but was not attached/)
    expect(attach).toHaveBeenCalledWith(['new-evidence'])
    expect(screen.queryByText(/attached to this answer/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry attaching uploaded file' }))
    await screen.findByText(/Signed chart.pdf attached to this answer/)
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(attach).toHaveBeenCalledTimes(2)
  })
  it('never attempts attachment if upload fails', async () => {
    const attach = vi.fn()
    mocks.post.mockRejectedValue(new Error('Network interrupted'))
    render(<ContextualEvidenceUpload ids={['old-evidence']} disabled={false} attach={attach} />)
    fireEvent.change(screen.getByLabelText('Upload evidence for this answer'), { target: { files: [new File(['chart'], 'Signed chart.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Upload and attach' }))
    await screen.findByRole('button', { name: 'Retry upload' })
    expect(attach).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('current attachment is unchanged')
  })
})
