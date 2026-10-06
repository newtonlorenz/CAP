import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Followup } from '../components/applications/Followups'
import type { ApplicationFollowup } from '../types/applications'

vi.mock('../api/preparation', () => ({ preparationApi: {
  evidence: vi.fn(async () => ({ items: [{ id: 'evidence-1', title: 'Ownership note', kind: 'note', archived: false }], total: 1 })),
  getEvidence: vi.fn(async () => ({ id: 'evidence-1', title: 'Ownership note', kind: 'note', archived: false })),
} }))

const item: ApplicationFollowup = {
  id: 'query-1', question: 'Confirm ownership', response: 'Initial response',
  evidence_ids: [], owner_id: null, due_date: null, status: 'open',
  resolved_at: null, created_at: '2026-09-29T10:00:00Z',
}
const tick = (milliseconds = 0) => act(async () => { await vi.advanceTimersByTimeAsync(milliseconds) })
function mount(onSave = vi.fn<(body: Partial<ApplicationFollowup>) => Promise<boolean>>().mockResolvedValue(true), initialBusy = false) {
  const onDirtyChange = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = (busy: boolean) => <QueryClientProvider client={client}><Followup item={item} users={[]} canEdit canManage busy={busy} onSave={onSave} onDirtyChange={onDirtyChange} /></QueryClientProvider>
  const rendered = render(view(initialBusy))
  return { onSave, onDirtyChange, setBusy: (busy: boolean) => rendered.rerender(view(busy)) }
}
beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers() })
afterEach(() => vi.useRealTimers())

describe('application authority response drafts', () => {
  it('autosaves response and evidence while query details and resolution remain explicit', async () => {
    const { onSave, onDirtyChange } = mount()
    fireEvent.click(screen.getByText('Edit query and assignment'))
    fireEvent.change(screen.getByRole('textbox', { name: 'Query text' }), { target: { value: 'Updated authority query' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Response' }), { target: { value: 'Ownership confirmed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add evidence' }))
    await tick(20)
    fireEvent.click(screen.getByRole('button', { name: 'Attach Ownership note' }))
    await tick(800)
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ response: 'Ownership confirmed', evidence_ids: ['evidence-1'] })
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)
    expect(screen.getByRole('button', { name: 'Resolve query' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Save query details' }))
    await tick()
    expect(onSave).toHaveBeenNthCalledWith(2, { question: 'Updated authority query', owner_id: null, due_date: null })
    fireEvent.click(screen.getByRole('button', { name: 'Resolve query' }))
    await tick()
    expect(onSave).toHaveBeenNthCalledWith(3, { status: 'resolved' })
  })

  it('defers a dirty response while another application write is busy', async () => {
    const { onSave, onDirtyChange, setBusy } = mount(undefined, true)
    fireEvent.change(screen.getByRole('textbox', { name: 'Response' }), { target: { value: 'Waiting draft' } })
    fireEvent.blur(screen.getByRole('textbox', { name: 'Response' }))
    await tick(1600)
    expect(onSave).not.toHaveBeenCalled()
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)
    setBusy(false)
    await tick(800)
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ response: 'Waiting draft', evidence_ids: [] })
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })

  it('keeps newer typing dirty until its own serial save completes', async () => {
    let complete!: (saved: boolean) => void
    const onSave = vi.fn<(body: Partial<ApplicationFollowup>) => Promise<boolean>>()
      .mockImplementationOnce(() => new Promise((resolve) => { complete = resolve }))
      .mockResolvedValue(true)
    const { onDirtyChange, setBusy } = mount(onSave)
    const response = screen.getByRole('textbox', { name: 'Response' })
    fireEvent.change(response, { target: { value: 'First draft' } }); fireEvent.blur(response)
    expect(onSave).toHaveBeenCalledTimes(1)
    setBusy(true)
    expect(response).toBeEnabled()
    fireEvent.change(response, { target: { value: 'Latest draft' } })
    await act(async () => complete(true))
    expect(response).toHaveValue('Latest draft')
    expect(screen.getByText('Unsaved')).toBeInTheDocument()
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)
    setBusy(false)
    await tick(800)
    expect(onSave).toHaveBeenNthCalledWith(2, { response: 'Latest draft', evidence_ids: [] })
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })

  it('retains a rejected draft through conflict and explicitly reconfirms an original value', async () => {
    const onSave = vi.fn<(body: Partial<ApplicationFollowup>) => Promise<boolean>>().mockResolvedValueOnce(false).mockResolvedValue(true)
    const { onDirtyChange, setBusy } = mount(onSave)
    const response = screen.getByRole('textbox', { name: 'Response' })
    fireEvent.change(response, { target: { value: 'Unacknowledged write' } }); fireEvent.blur(response)
    await tick()
    expect(screen.getByText('Not saved')).toBeInTheDocument()
    setBusy(true)
    fireEvent.change(response, { target: { value: 'Initial response' } }); fireEvent.blur(response)
    await tick(1600)
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: 'Retry save' })).not.toBeInTheDocument()
    expect(onDirtyChange).toHaveBeenLastCalledWith(true)
    setBusy(false)
    await tick(1600)
    expect(onSave).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Retry save' }))
    await tick()
    expect(onSave).toHaveBeenNthCalledWith(2, { response: 'Initial response', evidence_ids: [] })
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(onDirtyChange).toHaveBeenLastCalledWith(false)
  })
})
