import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ReviewCycleReportsModal } from '../pages/ReviewCycles'
import type { ReviewCycle } from '../types'

const cycle: ReviewCycle = {
  id: 'cycle-1',
  jurisdiction_id: 'jurisdiction-1',
  name: 'Quarterly Review',
  description: null,
  scope: 'all',
  scope_filter: null,
  deadline: null,
  status: 'active',
  created_by: 'user-1',
  closed_at: null,
  closed_by: null,
  snapshot_id: null,
  created_at: new Date().toISOString(),
}

describe('ReviewCycleReportsModal', () => {
  it('renders explicit gap analysis format actions', () => {
    render(
      <ReviewCycleReportsModal
        open
        cycle={cycle}
        reviewerDisplay="both"
        onReviewerDisplayChange={vi.fn()}
        isDownloading={null}
        onClose={vi.fn()}
        onDownload={vi.fn()}
        onDownloadSoA={vi.fn()}
        onDownloadReviewCycleReport={vi.fn()}
      />
    )

    expect(screen.getByText(/gap analysis/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^xlsx$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^pdf$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^csv$/i })).toBeInTheDocument()
  })
})
