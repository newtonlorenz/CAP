import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import DecisionModal from '../components/ui/DecisionModal'

describe('DecisionModal', () => {
  it('requires rationale in required mode', () => {
    const onConfirm = vi.fn()

    render(
      <DecisionModal
        open
        title="Delete timeline event"
        description="Provide a reason"
        confirmLabel="Delete"
        confirmVariant="destructive"
        rationaleMode="required"
        rationaleValue=""
        onRationaleChange={vi.fn()}
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />
    )

    const confirmButton = screen.getByRole('button', { name: 'Delete' })
    expect(confirmButton).toBeDisabled()
    fireEvent.click(confirmButton)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('fires confirm and cancel exactly once in optional mode', () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(
      <DecisionModal
        open
        title="Approve set"
        description="Optional comment"
        confirmLabel="Approve"
        confirmVariant="primary"
        rationaleMode="optional"
        rationaleValue="Looks good"
        onRationaleChange={vi.fn()}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
