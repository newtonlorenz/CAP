import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ToastProvider, useToast } from '../contexts/ToastContext'
import ToastViewport from '../components/ToastViewport'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import DecisionModal from '../components/ui/DecisionModal'
import DropdownMenu from '../components/ui/DropdownMenu'
import Modal from '../components/ui/Modal'

describe('ToastContext + ToastViewport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('should enqueue and auto-dismiss a toast', async () => {
    const Producer = () => {
      const toast = useToast()
      return (
        <button type="button" onClick={() => toast.success('Saved')}>
          Fire
        </button>
      )
    }

    render(
      <ToastProvider>
        <Producer />
        <ToastViewport />
      </ToastProvider>
    )

    fireEvent.click(screen.getByRole('button', { name: 'Fire' }))
    expect(screen.getByText('Saved')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(6000)
    })
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })
})

describe('ConfirmDialog', () => {
  it('should call onConfirm and onClose', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(
      <ConfirmDialog
        open
        title="Delete?"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('renders through DecisionModal adapter without rationale input', () => {
    render(
      <ConfirmDialog
        open
        title="Delete?"
        description="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />
    )

    expect(screen.queryByLabelText(/rationale/i)).not.toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
  })
})

describe('DecisionModal', () => {
  it('blocks confirm when required rationale is empty and allows when filled', () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    const { rerender } = render(
      <DecisionModal
        open
        title="Delete event"
        description="Provide a rationale."
        confirmLabel="Delete"
        rationaleMode="required"
        rationaleLabel="Deletion rationale"
        rationaleValue=""
        onRationaleChange={vi.fn()}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )

    const confirmButton = screen.getByRole('button', { name: 'Delete' })
    expect(confirmButton).toBeDisabled()

    rerender(
      <DecisionModal
        open
        title="Delete event"
        description="Provide a rationale."
        confirmLabel="Delete"
        rationaleMode="required"
        rationaleLabel="Deletion rationale"
        rationaleValue="cleanup duplicate record"
        onRationaleChange={vi.fn()}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('allows optional rationale confirm and cancel callbacks', () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    render(
      <DecisionModal
        open
        title="Approve"
        confirmLabel="Approve"
        rationaleMode="optional"
        rationaleValue=""
        onRationaleChange={vi.fn()}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('Modal focus behavior', () => {
  it('preserves focused input across parent rerenders while open', () => {
    const { rerender } = render(
      <Modal open title="Edit extraction" onClose={() => {}}>
        <input aria-label="Extraction reference" />
      </Modal>
    )

    const input = screen.getByLabelText('Extraction reference')
    input.focus()
    fireEvent.change(input, { target: { value: '1.2.3' } })
    expect(input).toHaveFocus()

    rerender(
      <Modal open title="Edit extraction" onClose={() => {}}>
        <input aria-label="Extraction reference" />
      </Modal>
    )

    expect(screen.getByLabelText('Extraction reference')).toHaveFocus()
  })
})

describe('DropdownMenu', () => {
  it('should open and invoke an item', async () => {
    const onSelect = vi.fn()
    render(
      <DropdownMenu
        ariaLabel="Row actions"
        items={[
          { key: 'open', label: 'Open', onSelect },
          { key: 'disabled', label: 'Disabled', onSelect: vi.fn(), disabled: true },
        ]}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Disabled' })).toBeDisabled()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Open' }))
    expect(onSelect).toHaveBeenCalledTimes(1)
  })
})
