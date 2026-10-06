import { describe, expect, it } from 'vitest'
import {
  buildHierarchyReferenceLookup,
  deriveParentFromReference,
  getHierarchyMismatch,
} from '../utils/referenceHierarchy'

describe('referenceHierarchy', () => {
  const items = [
    { id: 'root', reference_id: '3.2', parent_id: null },
    { id: 'section', reference_id: '3.2.5', parent_id: 'root' },
    { id: 'child', reference_id: '3.2.5.3', parent_id: 'root' },
    { id: 'alpha', reference_id: '3.3.1.a', parent_id: null },
  ]

  it('derives the longest existing dotted prefix as the parent', () => {
    const lookup = buildHierarchyReferenceLookup(items)

    expect(deriveParentFromReference('3.2.5.3', lookup, 'child')).toEqual({
      parentId: 'section',
      parentReferenceId: '3.2.5',
    })
  })

  it('returns no parent for top-level references', () => {
    const lookup = buildHierarchyReferenceLookup(items)

    expect(deriveParentFromReference('5', lookup)).toEqual({
      parentId: null,
      parentReferenceId: null,
    })
  })

  it('handles non-numeric dotted references and reports mismatches', () => {
    const lookup = buildHierarchyReferenceLookup(items)

    expect(deriveParentFromReference('3.3.1.a.1', lookup)).toEqual({
      parentId: 'alpha',
      parentReferenceId: '3.3.1.a',
    })
    expect(getHierarchyMismatch(items[2], lookup).isMismatch).toBe(true)
  })
})
