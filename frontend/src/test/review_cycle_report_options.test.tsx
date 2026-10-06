import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ReviewCycleReportOptions from '../components/ReviewCycleReportOptions'

describe('ReviewCycleReportOptions', () => {
  it('renders reviewer display options', () => {
    render(
      <ReviewCycleReportOptions
        open
        value="both"
        onChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText(/names \+ emails/i)).toBeInTheDocument()
    expect(screen.getByText(/names only/i)).toBeInTheDocument()
    expect(screen.getByText(/emails only/i)).toBeInTheDocument()
  })
})
