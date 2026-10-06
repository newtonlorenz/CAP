import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ReviewCompletion from '../components/ReviewCompletion'
import type { ReviewCycleWithItems } from '../types'
import api from '../api/client'
vi.mock('../api/client', () => ({ default: { post: vi.fn() } }))
const cycle = { id: 'review-1', status: 'active', readiness: { can_close: true, total: 2, applicable: 1, ready: 1, not_applicable: 1, informational: 0, blocker_count: 0, blockers: [] } } as unknown as ReviewCycleWithItems
beforeEach(() => vi.resetAllMocks())
it('blocks completion while evidence changes are unsaved', () => {
 render(<MemoryRouter><ReviewCompletion cycle={cycle} canComplete onChanged={vi.fn()} hasUnsavedChanges /></MemoryRouter>)
 expect(screen.getByRole('button', { name: 'Complete assessment' })).toBeDisabled()
 expect(screen.getByRole('status')).toHaveTextContent('Save your evidence')
})
it('requires confirmation then hands over the frozen review', async () => {
 vi.mocked(api.post).mockResolvedValue({ data: {} })
 const changed = vi.fn()
 render(<MemoryRouter><ReviewCompletion cycle={cycle} canComplete onChanged={changed} /></MemoryRouter>)
 fireEvent.click(screen.getByRole('button', { name: 'Complete assessment' }))
 expect(api.post).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button', { name: 'Complete and freeze' }))
 await waitFor(() => expect(changed).toHaveBeenCalledOnce())
 expect(api.post).toHaveBeenCalledWith('/review-cycles/review-1/close')
})
it('links blockers to their focused requirement and explains server refusal', async () => {
 const blocked = { ...cycle, readiness: { ...cycle.readiness!, can_close: false, blocker_count: 1, blockers: [{ item_id: 'item-1', reference_id: '3.1.1.1', reasons: ['Add supporting evidence'] }] } }
 render(<MemoryRouter><ReviewCompletion cycle={blocked} canComplete onChanged={vi.fn()} /></MemoryRouter>)
 expect(screen.getByRole('button', { name: 'Complete assessment' })).toBeDisabled()
 fireEvent.click(screen.getByText('1 requirement needs attention before completion'))
 expect(screen.getByRole('link', { name: '3.1.1.1' })).toHaveAttribute('href', '/review-cycles/review-1?mode=focus&item=item-1')
})
it('links completed assessments to their selected reports', () => {
 render(<MemoryRouter><ReviewCompletion cycle={{...cycle, closed_at: '2026-09-20T10:00:00Z'}} canComplete onChanged={vi.fn()} /></MemoryRouter>)
 expect(screen.getByRole('link', { name: 'Reports and evidence package' })).toHaveAttribute('href', '/reports?section=reviews&review=review-1')
 expect(screen.queryByRole('button', { name: 'Complete assessment' })).not.toBeInTheDocument()
})

it('keeps completion errors visible inside the open confirmation dialog', async () => {
 vi.mocked(api.post).mockRejectedValue(new Error('Unable to freeze evidence'))
 render(<MemoryRouter><ReviewCompletion cycle={cycle} canComplete onChanged={vi.fn()} /></MemoryRouter>)
 fireEvent.click(screen.getByRole('button', { name: 'Complete assessment' }))
 fireEvent.click(screen.getByRole('button', { name: 'Complete and freeze' }))
 const dialog = screen.getByRole('dialog')
 await waitFor(() => expect(within(dialog).getByRole('alert')).toBeVisible())
 expect(within(dialog).getByRole('button', { name: 'Complete and freeze' })).toBeEnabled()
})
