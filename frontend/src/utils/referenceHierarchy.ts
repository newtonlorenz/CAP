export type ReferenceHierarchyItem = {
  id: string
  reference_id: string
  parent_id: string | null
}

export type DerivedParentMatch = {
  parentId: string | null
  parentReferenceId: string | null
}

export type HierarchyMismatch = DerivedParentMatch & {
  isMismatch: boolean
}

export const normalizeHierarchyReference = (referenceId: string | null | undefined) =>
  (referenceId || '').trim().replace(/\.+$/, '')

export const buildHierarchyReferenceLookup = <T extends { id: string; reference_id: string }>(
  items: T[]
) => {
  const lookup = new Map<string, T>()
  items.forEach((item) => {
    const normalized = normalizeHierarchyReference(item.reference_id)
    if (!normalized || lookup.has(normalized)) return
    lookup.set(normalized, item)
  })
  return lookup
}

export const deriveParentFromReference = <T extends { id: string; reference_id: string }>(
  referenceId: string | null | undefined,
  referenceLookup: Map<string, T>,
  currentId?: string
): DerivedParentMatch => {
  const normalized = normalizeHierarchyReference(referenceId)
  if (!normalized || !normalized.includes('.')) {
    return {
      parentId: null,
      parentReferenceId: null,
    }
  }

  const parts = normalized.split('.').filter(Boolean)
  for (let end = parts.length - 1; end > 0; end -= 1) {
    const candidate = parts.slice(0, end).join('.')
    const match = referenceLookup.get(candidate)
    if (!match || match.id === currentId) continue
    return {
      parentId: match.id,
      parentReferenceId: candidate,
    }
  }

  return {
    parentId: null,
    parentReferenceId: null,
  }
}

export const getHierarchyMismatch = (
  item: ReferenceHierarchyItem,
  referenceLookup: Map<string, ReferenceHierarchyItem>
): HierarchyMismatch => {
  const derived = deriveParentFromReference(item.reference_id, referenceLookup, item.id)
  return {
    ...derived,
    isMismatch: (item.parent_id || null) !== derived.parentId,
  }
}
