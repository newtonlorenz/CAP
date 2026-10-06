import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RequirementsOutline from '../components/RequirementsOutline'
import type { OutlineNode } from '../utils/requirementsOutline'

const groups = [
  { key: 'first', title: 'First set', nodes: [{ key: 'root', targetId: 'root-a', label: '1 Root', children: [
    { key: 'child', targetId: 'child-a', label: '1.1 Child', children: [
      { key: 'leaf-a', targetId: 'leaf-a', label: '1.1.1 Detail', children: [] },
      { key: 'leaf-b', targetId: 'leaf-b', label: '1.1.2 Detail', children: [] },
    ] },
  ] }] },
  { key: 'second', title: 'Second set', nodes: [{ key: 'root', targetId: 'root-b', label: '2 Root', children: [
    { key: 'child', targetId: 'child-b', label: '2.1 Child', children: [] },
  ] }] },
]
const row = (name: string) => screen.queryByRole('button', { name })
const choose = (value: string) => fireEvent.change(screen.getByRole('combobox', { name: 'Show levels' }), { target: { value } })

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

describe('RequirementsOutline depth selection', () => {
  it('sets the visible depth across sets, allows individual expansion and resets it with a new preset', () => {
    const onNavigate = vi.fn()
    render(<RequirementsOutline groups={groups} onNavigate={onNavigate} />)
    choose('1')
    expect(row('1 Root')).toBeInTheDocument()
    expect(row('2 Root')).toBeInTheDocument()
    expect(row('1.1 Child')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Expand 1 Root' }))
    expect(row('1.1 Child')).toBeInTheDocument()
    expect(row('2.1 Child')).not.toBeInTheDocument()
    expect(row('1.1.1 Detail')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '1.1 Child' }))
    expect(onNavigate).toHaveBeenCalledWith('child-a')
    choose('2')
    expect(row('2.1 Child')).toBeInTheDocument()
    expect(row('1.1.1 Detail')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'First set' }))
    choose('all')
    expect(row('1.1.1 Detail')).toBeInTheDocument()
    expect(row('2.1 Child')).toBeInTheDocument()
  })

  it('remembers the depth between pages and tolerates a shallower filtered hierarchy', () => {
    const first = render(<RequirementsOutline groups={groups} onNavigate={vi.fn()} />)
    choose('2'); first.unmount()
    const second = render(<RequirementsOutline groups={[{ ...groups[0], nodes: [{ ...groups[0].nodes[0], children: [] }] }]} onNavigate={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('2')
    second.rerender(<RequirementsOutline groups={groups} onNavigate={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('2')
    expect(row('1.1 Child')).toBeInTheDocument()
    expect(row('1.1.1 Detail')).not.toBeInTheDocument()
  })

  it('reveals the selected path on navigation without undoing an explicit collapse on a data refresh', () => {
    localStorage.setItem('cap:outline-levels', '1')
    const view = render(<RequirementsOutline groups={groups} selectedTargetId="leaf-a" onNavigate={vi.fn()} />)
    expect(row('1.1.1 Detail')).toHaveAttribute('aria-current', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Collapse 1 Root' }))
    view.rerender(<RequirementsOutline groups={structuredClone(groups)} selectedTargetId="leaf-a" onNavigate={vi.fn()} />)
    expect(row('1.1.1 Detail')).not.toBeInTheDocument()
    view.rerender(<RequirementsOutline groups={groups} selectedTargetId="leaf-b" onNavigate={vi.fn()} />)
    expect(row('1.1.2 Detail')).toHaveAttribute('aria-current', 'true')
    expect(row('2.1 Child')).not.toBeInTheDocument()
    choose('1')
    expect(row('1.1.2 Detail')).not.toBeInTheDocument()
  })

  it('offers every depth present, including hierarchies deeper than nine levels', () => {
    let children: OutlineNode[] = []
    for (let level = 10; level >= 1; level--) children = [{ key: `level-${level}`, targetId: `level-${level}`, label: `Level ${level}`, children }]
    render(<RequirementsOutline groups={[{ key: 'deep', title: 'Deep set', nodes: children }]} onNavigate={vi.fn()} />)
    expect(screen.getByRole('option', { name: '10 levels' })).toBeInTheDocument()
    choose('9')
    expect(row('Level 9')).toBeInTheDocument()
    expect(row('Level 10')).not.toBeInTheDocument()
    choose('all')
    expect(row('Level 10')).toBeInTheDocument()
  })

  it('keeps the depth control at the top of an empty filtered outline', () => {
    localStorage.setItem('cap:outline-levels', '3')
    render(<RequirementsOutline groups={[]} onNavigate={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('3')
    expect(screen.getByText('No outline items.')).toBeInTheDocument()
  })

  it('works when browser storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Unavailable') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable') })
    render(<RequirementsOutline groups={groups} onNavigate={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Show levels' })).toHaveValue('all')
    choose('1')
    expect(row('1.1 Child')).not.toBeInTheDocument()
    choose('all')
    expect(row('1.1.1 Detail')).toBeInTheDocument()
  })
})
