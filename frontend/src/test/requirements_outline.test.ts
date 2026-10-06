import { describe, expect, it } from 'vitest'
import { buildOutlineTree } from '../utils/requirementsOutline'

describe('buildOutlineTree', () => {
  it('builds nested nodes from a pre-order flattened list', () => {
    const tree = buildOutlineTree(
      [
        { key: 'a', targetId: 't-a', referenceId: '1', title: 'One', depth: 0 },
        { key: 'b', targetId: 't-b', referenceId: '1.1', title: 'One One', depth: 1 },
        { key: 'c', targetId: 't-c', referenceId: '1.1.1', title: 'One One One', depth: 2 },
        { key: 'd', targetId: 't-d', referenceId: '2', title: 'Two', depth: 0 },
      ],
      2
    )

    expect(tree).toHaveLength(2)
    expect(tree[0]!.label).toBe('1 One')
    expect(tree[0]!.children).toHaveLength(1)
    expect(tree[0]!.children[0]!.label).toBe('1.1 One One')
    expect(tree[0]!.children[0]!.children).toHaveLength(1)
    expect(tree[0]!.children[0]!.children[0]!.label).toBe('1.1.1 One One One')
    expect(tree[1]!.label).toBe('2 Two')
  })

  it('skips items deeper than maxDepth', () => {
    const tree = buildOutlineTree(
      [
        { key: 'a', targetId: 't-a', referenceId: '1', title: null, depth: 0 },
        { key: 'b', targetId: 't-b', referenceId: '1.1', title: null, depth: 1 },
        { key: 'c', targetId: 't-c', referenceId: '1.1.1', title: null, depth: 2 },
        { key: 'd', targetId: 't-d', referenceId: '1.1.1.1', title: null, depth: 3 },
      ],
      2
    )

    expect(tree).toHaveLength(1)
    expect(tree[0]!.children).toHaveLength(1)
    expect(tree[0]!.children[0]!.children).toHaveLength(1)
    expect(tree[0]!.children[0]!.children[0]!.label).toBe('1.1.1')
  })

  it('handles multiple roots and sibling ordering', () => {
    const tree = buildOutlineTree(
      [
        { key: 'a', targetId: 't-a', referenceId: '1', title: null, depth: 0 },
        { key: 'b', targetId: 't-b', referenceId: '1.1', title: null, depth: 1 },
        { key: 'c', targetId: 't-c', referenceId: '2', title: null, depth: 0 },
        { key: 'd', targetId: 't-d', referenceId: '2.1', title: null, depth: 1 },
      ],
      2
    )

    expect(tree.map((n) => n.label)).toEqual(['1', '2'])
    expect(tree[0]!.children.map((n) => n.label)).toEqual(['1.1'])
    expect(tree[1]!.children.map((n) => n.label)).toEqual(['2.1'])
  })

  it('preserves optional flag metadata on nodes', () => {
    const tree = buildOutlineTree(
      [
        {
          key: 'a',
          targetId: 't-a',
          referenceId: '1',
          title: 'Flagged node',
          depth: 0,
          isFlagged: true,
          flagReason: 'anchor_mismatch',
        },
      ],
      2
    )

    expect(tree).toHaveLength(1)
    expect(tree[0]!.isFlagged).toBe(true)
    expect(tree[0]!.flagReason).toBe('anchor_mismatch')
  })
})
