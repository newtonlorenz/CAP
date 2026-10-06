import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Button from '../components/ui/Button'
import CopyButton from '../components/ui/CopyButton'
import DraftSaveStatus from '../components/ui/DraftSaveStatus'
import Modal from '../components/ui/Modal'
import Tooltip from '../components/ui/Tooltip'

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

describe('Shared tooltips', () => {
  it('waits briefly on hover, stays available over the help, and renders outside clipped content', () => {
    vi.useFakeTimers()
    const { container } = render(<div style={{ overflow: 'hidden' }}><Tooltip content="Full requirement name"><button>Requirement</button></Tooltip></div>)
    const trigger = screen.getByRole('button', { name: 'Requirement' })
    fireEvent.pointerEnter(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(250))
    const help = screen.getByRole('tooltip')
    expect(container).not.toContainElement(help)
    expect(trigger).toHaveAccessibleDescription('Full requirement name')
    fireEvent.pointerLeave(trigger)
    fireEvent.pointerEnter(help)
    act(() => vi.advanceTimersByTime(100))
    expect(help).toBeInTheDocument()
    fireEvent.pointerLeave(help)
    act(() => vi.advanceTimersByTime(100))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('opens on keyboard focus and consumes Escape before the parent dialog', () => {
    const close = vi.fn()
    render(<Modal open title="Edit requirement" onClose={close}><Button title="Applies these changes">Save</Button></Modal>)
    const trigger = screen.getByRole('button', { name: 'Save' })
    act(() => trigger.focus())
    expect(trigger).toHaveAccessibleDescription('Applies these changes')
    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    expect(close).not.toHaveBeenCalled()
    expect(trigger).toHaveFocus()
    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(close).toHaveBeenCalledOnce()
  })

  it('explains a disabled action by keyboard while keeping the action disabled', () => {
    const save = vi.fn()
    render(<Button disabled title="Choose a jurisdiction first" aria-label="Create review" onClick={save}>Create review</Button>)
    const trigger = screen.getByRole('group', { name: 'Create review' })
    act(() => trigger.focus())
    expect(trigger).toHaveAccessibleDescription('Choose a jurisdiction first')
    expect(screen.getByRole('button', { name: 'Create review' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Create review' }))
    fireEvent.keyDown(trigger, { key: 'Enter' })
    expect(save).not.toHaveBeenCalled()
  })
})

describe('Shared copy feedback', () => {
  it('reports unavailable clipboard access without claiming a copy succeeded', async () => {
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
    try {
      render(<CopyButton value="Draft text" />)
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      expect(await screen.findByRole('alert')).toHaveTextContent('Could not copy. Select the text and copy it manually.')
      expect(screen.queryByText('Copied.')).not.toBeInTheDocument()
    } finally {
      if (original) Object.defineProperty(navigator, 'clipboard', original)
      else Reflect.deleteProperty(navigator, 'clipboard')
    }
  })

  it('does not show an old copy result as confirmation of a newly edited value', async () => {
    let resolveCopy!: () => void
    const writeText = vi.fn().mockImplementationOnce(() => new Promise<void>((resolve) => { resolveCopy = resolve }))
      .mockResolvedValue(undefined)
    const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    try {
      const { rerender } = render(<CopyButton value="Original draft" />)
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      rerender(<CopyButton value="Updated draft" />)
      await act(async () => { resolveCopy() })
      expect(screen.queryByText('Copied.')).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
      expect(await screen.findByText('Copied.')).toBeInTheDocument()
      expect(writeText).toHaveBeenLastCalledWith('Updated draft')
    } finally {
      if (original) Object.defineProperty(navigator, 'clipboard', original)
      else Reflect.deleteProperty(navigator, 'clipboard')
    }
  })
})

it('offers explicit save recovery for an error without retrying a conflicting draft', () => {
  const retry = vi.fn()
  const { rerender } = render(<DraftSaveStatus state="error" onRetry={retry} message="Your draft is kept here." />)
  expect(screen.getByRole('alert')).toHaveTextContent('Not saved · Your draft is kept here.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry save' }))
  expect(retry).toHaveBeenCalledOnce()
  rerender(<DraftSaveStatus state="conflict" onRetry={retry} message="Reload the latest version before saving." />)
  expect(screen.getByRole('alert')).toHaveTextContent('Conflict')
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
