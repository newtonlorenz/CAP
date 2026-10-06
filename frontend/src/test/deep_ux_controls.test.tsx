import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Modal from '../components/ui/Modal'
import DropdownMenu from '../components/ui/DropdownMenu'
import RichTextEditor from '../components/RichTextEditor'

describe('Keyboard journeys through shared controls', () => {
  it('closes only the top dialog and retains the underlying dialog focus and scroll lock', () => {
    function Nested() {
      const [inner, setInner] = useState(false)
      const [outer, setOuter] = useState(true)
      return <Modal open={outer} title="Outer" onClose={() => setOuter(false)}>
        <button onClick={() => setInner(true)}>Open inner</button>
        <Modal open={inner} title="Inner" onClose={() => setInner(false)}><input data-autofocus aria-label="Reason" /></Modal>
      </Modal>
    }
    render(<Nested />)
    screen.getByRole('button', { name: 'Open inner' }).focus()
    fireEvent.click(screen.getByRole('button', { name: 'Open inner' }))
    expect(screen.getByLabelText('Reason')).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Inner' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Outer' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open inner' })).toHaveFocus()
    expect(document.body).toHaveClass('overflow-hidden')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(document.body).not.toHaveClass('overflow-hidden')
  })

  it('includes rich text in the focus loop and skips hidden fields', () => {
    render(<Modal open title="Edit source" onClose={() => {}}><input type="hidden" /><input aria-label="Hidden" style={{ display: 'none' }} /><div contentEditable tabIndex={0} role="textbox" aria-label="Text" /></Modal>)
    screen.getByRole('button', { name: 'Close dialog' }).focus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(screen.getByRole('textbox', { name: 'Text' })).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(screen.getByRole('button', { name: 'Close dialog' })).toHaveFocus()
  })

  it('places a menu outside clipping ancestors and supports directional keys and focus restoration', async () => {
    const select = vi.fn()
    render(<div data-testid="clipped" style={{ overflow: 'hidden' }}><DropdownMenu items={[
      { key: 'one', label: 'First', onSelect: select }, { key: 'off', label: 'Unavailable', onSelect: select, disabled: true }, { key: 'last', label: 'Last', onSelect: select },
    ]} /></div>)
    const trigger = screen.getByRole('button', { name: 'Row actions' })
    fireEvent.keyDown(trigger, { key: 'ArrowUp' })
    expect(screen.getByRole('menuitem', { name: 'Last' })).toHaveFocus()
    expect(screen.getByTestId('clipped')).not.toContainElement(screen.getByRole('menu'))
    fireEvent.keyDown(document.activeElement!, { key: 'Home' })
    expect(screen.getByRole('menuitem', { name: 'First' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' })
    expect(screen.getByRole('menuitem', { name: 'Last' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
    expect(select).not.toHaveBeenCalled()
  })

  it('keeps the parent dialog open when Escape dismisses its menu', () => {
    const close = vi.fn()
    render(<Modal open title="Parent" onClose={close}><DropdownMenu items={[{ key: 'edit', label: 'Edit', onSelect: vi.fn() }]} /></Modal>)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    fireEvent.keyDown(screen.getByRole('menuitem'), { key: 'Escape' })
    expect(close).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Row actions' })).toHaveFocus()
  })

  it('applies formatting from the keyboard click and gives the editor a specific accessible name', () => {
    const execute = vi.fn()
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execute })
    render(<RichTextEditor value="Text" ariaLabel="Control text" onChange={vi.fn()} />)
    act(() => screen.getByRole('button', { name: 'Bold' }).focus())
    fireEvent.click(screen.getByRole('button', { name: 'Bold' }), { detail: 0 })
    expect(execute).toHaveBeenCalledWith('bold', false)
    expect(screen.getByRole('textbox', { name: 'Control text' })).toHaveFocus()
  })
})
