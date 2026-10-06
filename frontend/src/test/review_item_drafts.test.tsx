import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReviewItemWithRequirement } from '../types'

const toast = { error: vi.fn(), success: vi.fn(), info: vi.fn(), dismiss: vi.fn(), toasts: [] }
vi.mock('../contexts/ToastContext', () => ({ useToast: () => toast }))
vi.mock('../api/client', () => ({ default: { put: vi.fn() } }))
import api from '../api/client'
import { useReviewItemDrafts } from '../hooks/review/useReviewItemDrafts'

const item = (overrides: Partial<ReviewItemWithRequirement> = {}) => ({
  id: 'item-1', review_status: 'pending', requirement_current_status: 'not_started',
  review_evidence: 'Old evidence', ...overrides,
} as ReviewItemWithRequirement)
function deferred() {
  let resolve!: () => void
  let reject!: (reason: Error) => void
  const promise = new Promise<void>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.put).mockResolvedValue({}) })

describe('review item drafts', () => {
  it('serialises rapid writes and preserves newer values through stale refetches', async () => {
    const first = deferred(), second = deferred()
    vi.mocked(api.put).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const initial = item(), onSaved = vi.fn()
    const { result, rerender } = renderHook(({ items }) => useReviewItemDrafts('cycle-1', items, onSaved), { initialProps: { items: [initial] } })
    act(() => {
      result.current.changeStatus(initial, 'review_status', 'confirmed')
      result.current.changeStatus(initial, 'requirement_status', 'in_progress')
    })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    rerender({ items: [{ ...initial }] })
    expect(result.current.getDraft(initial)).toMatchObject({ review_status: 'confirmed', requirement_status: 'in_progress' })
    await act(async () => { first.resolve(); await first.promise })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.put).mock.calls[1][1]).toMatchObject({ review_status: 'confirmed', requirement_status: 'in_progress' })
    rerender({ items: [{ ...initial }] })
    await act(async () => { second.resolve(); await second.promise })
    rerender({ items: [{ ...initial }] })
    expect(result.current.getDraft(initial)).toMatchObject({ review_status: 'confirmed', requirement_status: 'in_progress' })
    expect(onSaved).toHaveBeenCalledTimes(2)
  })

  it('acknowledges evidence:null as empty text across a stale response', async () => {
    const save = deferred()
    vi.mocked(api.put).mockReturnValueOnce(save.promise)
    const initial = item()
    const { result, rerender } = renderHook(({ items }) => useReviewItemDrafts('cycle-1', items, vi.fn()), { initialProps: { items: [initial] } })
    act(() => { result.current.changeEvidence(initial, ''); result.current.saveEvidence(initial) })
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/review-cycles/cycle-1/items/item-1', { review_evidence: null }))
    await act(async () => { save.resolve(); await save.promise })
    rerender({ items: [{ ...initial }] })
    expect(result.current.getDraft(initial).review_evidence).toBe('')
    expect(result.current.hasUnsavedChanges).toBe(false)
    rerender({ items: [{ ...initial, review_evidence: null }] })
    expect(result.current.getDraft(initial).review_evidence).toBe('')
  })

  it('saves evidence edited during a pending status request after that request', async () => {
    const statusSave = deferred(), evidenceSave = deferred()
    vi.mocked(api.put).mockReturnValueOnce(statusSave.promise).mockReturnValueOnce(evidenceSave.promise)
    const initial = item()
    const { result, rerender } = renderHook(({ items }) => useReviewItemDrafts('cycle-1', items, vi.fn()), { initialProps: { items: [initial] } })
    act(() => {
      result.current.changeStatus(initial, 'requirement_status', 'in_progress')
      result.current.changeEvidence(initial, 'Latest evidence')
      result.current.saveEvidence(initial)
    })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.put).mock.calls[0][1]).toMatchObject({ requirement_status: 'in_progress', review_evidence: 'Old evidence' })
    await act(async () => { statusSave.resolve(); await statusSave.promise })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.put).mock.calls[1][1]).toEqual({ review_evidence: 'Latest evidence' })
    rerender({ items: [{ ...initial, requirement_current_status: 'in_progress' }] })
    expect(result.current.getDraft(initial).review_evidence).toBe('Latest evidence')
    await act(async () => { evidenceSave.resolve(); await evidenceSave.promise })
    rerender({ items: [{ ...initial, requirement_current_status: 'in_progress' }] })
    expect(result.current.getDraft(initial).review_evidence).toBe('Latest evidence')
  })

  it('keeps a failed choice and newer evidence for an explicit retry', async () => {
    const save = deferred()
    vi.mocked(api.put).mockReturnValueOnce(save.promise)
    const initial = item()
    const { result } = renderHook(() => useReviewItemDrafts('cycle-1', [initial], vi.fn()))
    act(() => { result.current.changeStatus(initial, 'requirement_status', 'not_applicable'); result.current.changeEvidence(initial, 'New note') })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    await act(async () => { save.reject(new Error('Forbidden')); try { await save.promise } catch { /* expected */ } })
    expect(result.current.getDraft(initial)).toMatchObject({ requirement_status: 'not_applicable', review_evidence: 'New note' })
    expect(result.current.saveStatusByItem['item-1']).toBe('error')
    expect(result.current.itemNeedsSave(initial)).toBe(true)
    act(() => result.current.retryItem(initial))
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.put).mock.calls[1][1]).toMatchObject({ requirement_status: 'not_applicable', review_evidence: 'New note' })
    await waitFor(() => expect(result.current.saveStatusByItem['item-1']).toBe('saved'))
    expect(result.current.itemNeedsSave(initial)).toBe(false)
  })

  it('ignores an old cycle response after the same hook moves to another cycle', async () => {
    const save = deferred()
    vi.mocked(api.put).mockReturnValueOnce(save.promise)
    const oldSaved = vi.fn(), newSaved = vi.fn(), initial = item()
    const { result, rerender } = renderHook(({ id, items, onSaved }) => useReviewItemDrafts(id, items, onSaved), { initialProps: { id: 'cycle-1', items: [initial], onSaved: oldSaved } })
    act(() => result.current.changeStatus(initial, 'review_status', 'confirmed'))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/review-cycles/cycle-1/items/item-1', { review_status: 'confirmed' }))
    const next = item({ review_status: 'rejected' })
    rerender({ id: 'cycle-2', items: [next], onSaved: newSaved })
    await act(async () => { save.resolve(); await save.promise })
    expect(newSaved).not.toHaveBeenCalled()
    expect(result.current.saveStatusByItem).toEqual({})
    expect(result.current.getDraft(next).review_status).toBe('rejected')
  })

  it('autosaves focused evidence without making a review decision', async () => {
    const initial = item()
    const { result } = renderHook(() => useReviewItemDrafts('cycle-1', [initial], vi.fn()))
    act(() => result.current.changeEvidence(initial, 'Focused evidence draft'))
    expect(result.current.saveStatusByItem['item-1']).toBe('dirty')
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/review-cycles/cycle-1/items/item-1', { review_evidence: 'Focused evidence draft' }), { timeout: 2000 })
    expect(result.current.getDraft(initial).review_status).toBe('pending')
  })

  it('keeps a newer focused evidence edit dirty when an earlier save finishes', async () => {
    const save = deferred(), initial = item()
    vi.mocked(api.put).mockReturnValueOnce(save.promise)
    const { result } = renderHook(() => useReviewItemDrafts('cycle-1', [initial], vi.fn()))
    act(() => { result.current.changeEvidence(initial, 'First evidence'); result.current.saveEvidence(initial) })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    act(() => result.current.changeEvidence(initial, 'Newer evidence'))
    await act(async () => { save.resolve(); await save.promise })
    expect(result.current.saveStatusByItem['item-1']).toBe('dirty')
    expect(result.current.itemNeedsSave(initial)).toBe(true)
    await waitFor(() => expect(vi.mocked(api.put).mock.calls[1]?.[1]).toEqual({ review_evidence: 'Newer evidence' }), { timeout: 2000 })
  })

  it('persists a reversion to original evidence after an earlier write is queued', async () => {
    const save = deferred(), initial = item()
    vi.mocked(api.put).mockReturnValueOnce(save.promise)
    const { result } = renderHook(() => useReviewItemDrafts('cycle-1', [initial], vi.fn()))
    act(() => { result.current.changeEvidence(initial, 'Temporary evidence'); result.current.saveEvidence(initial) })
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1))
    act(() => { result.current.changeEvidence(initial, 'Old evidence'); result.current.saveEvidence(initial) })
    await act(async () => { save.resolve(); await save.promise })
    await waitFor(() => expect(vi.mocked(api.put).mock.calls[1]?.[1]).toEqual({ review_evidence: 'Old evidence' }))
    expect(result.current.getDraft(initial).review_evidence).toBe('Old evidence')
  })
})
