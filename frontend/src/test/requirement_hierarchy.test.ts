import { describe, expect, it } from 'vitest'
import {
  buildHierarchyTree,
  flattenHierarchyTree,
} from '../utils/requirementHierarchy'

type TestItem = {
  id: string
  reference_id: string
  parent_id: string | null
  sort_order: number
}

const buildFlattenedRefs = (items: TestItem[]) =>
  flattenHierarchyTree(
    buildHierarchyTree(items, {
      getId: (item) => item.id,
      getReferenceId: (item) => item.reference_id,
      getParentId: (item) => item.parent_id,
      getSortOrder: (item) => item.sort_order,
    })
  ).map(({ item, depth }) => `${'  '.repeat(depth)}${item.reference_id}`)

describe('requirementHierarchy', () => {
  it('keeps correctly linked parents as-is', () => {
    const refs = buildFlattenedRefs([
      { id: 'root', reference_id: '3.4', parent_id: null, sort_order: 1 },
      { id: 'section', reference_id: '3.4.2', parent_id: 'root', sort_order: 2 },
      { id: 'child', reference_id: '3.4.2.1', parent_id: 'section', sort_order: 3 },
    ])

    expect(refs).toEqual(['3.4', '  3.4.2', '    3.4.2.1'])
  })

  it('repairs missing parents from the immediate numeric reference prefix', () => {
    const refs = buildFlattenedRefs([
      { id: 'root', reference_id: '3.5', parent_id: null, sort_order: 1 },
      { id: 'section', reference_id: '3.5.1', parent_id: null, sort_order: 2 },
      { id: 'child', reference_id: '3.5.1.1', parent_id: null, sort_order: 3 },
    ])

    expect(refs).toEqual(['3.5', '  3.5.1', '    3.5.1.1'])
  })

  it('overrides wrong stored parents when the immediate numeric parent exists', () => {
    const refs = buildFlattenedRefs([
      { id: 'root', reference_id: '3.5', parent_id: null, sort_order: 1 },
      { id: 'section', reference_id: '3.5.1', parent_id: null, sort_order: 2 },
      { id: 'child', reference_id: '3.5.1.4', parent_id: 'root', sort_order: 3 },
    ])

    expect(refs).toEqual(['3.5', '  3.5.1', '    3.5.1.4'])
  })

  it('keeps orphaned and non-numeric dotted references stable when no numeric parent exists', () => {
    const refs = buildFlattenedRefs([
      { id: 'legacy-root', reference_id: 'Legacy', parent_id: null, sort_order: 1 },
      { id: 'orphan', reference_id: '9.1', parent_id: 'legacy-root', sort_order: 2 },
      { id: 'alpha-root', reference_id: '3.3.1.a', parent_id: null, sort_order: 3 },
      { id: 'alpha-child', reference_id: '3.3.1.a.1', parent_id: null, sort_order: 4 },
    ])

    expect(refs).toEqual([
      '3.3.1.a',
      '  3.3.1.a.1',
      'Legacy',
      '  9.1',
    ])
  })
})
