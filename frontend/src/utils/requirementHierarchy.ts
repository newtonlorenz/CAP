import { compareReferenceIds } from './referenceIds'

export type HierarchyNode<T> = {
  item: T
  children: HierarchyNode<T>[]
}

export type FlattenedHierarchyItem<T> = {
  item: T
  depth: number
}

export type HierarchyAdapter<T> = {
  getId: (item: T) => string
  getReferenceId: (item: T) => string
  getParentId: (item: T) => string | null | undefined
  getSortOrder: (item: T) => number
}

const normalizeReferenceId = (value: string | null | undefined) =>
  (value || '').trim().replace(/\.+$/, '')

const getParentReferenceCandidates = (referenceId: string) => {
  const normalized = normalizeReferenceId(referenceId)
  if (!normalized.includes('.')) return []

  const parts = normalized.split('.').filter(Boolean)
  const candidates: string[] = []
  for (let end = parts.length - 1; end > 0; end -= 1) {
    candidates.push(parts.slice(0, end).join('.'))
  }
  return candidates
}

const getImmediateNumericParentReference = (referenceId: string) => {
  const normalized = normalizeReferenceId(referenceId)
  if (!/^\d+(?:\.\d+)+$/.test(normalized)) return null

  const parts = normalized.split('.')
  return parts.slice(0, -1).join('.')
}

export const buildHierarchyTree = <T>(
  items: T[],
  {
    getId,
    getReferenceId,
    getParentId,
    getSortOrder,
  }: HierarchyAdapter<T>
): HierarchyNode<T>[] => {
  const nodes = new Map<string, HierarchyNode<T>>()
  const referenceIndex = new Map<string, HierarchyNode<T>>()

  items.forEach((item) => {
    const node = { item, children: [] }
    nodes.set(getId(item), node)

    const normalizedReference = normalizeReferenceId(getReferenceId(item))
    if (normalizedReference && !referenceIndex.has(normalizedReference)) {
      referenceIndex.set(normalizedReference, node)
    }
  })

  const resolveParentNode = (node: HierarchyNode<T>) => {
    const explicitParentId = getParentId(node.item) || null
    const explicitParentNode = explicitParentId ? nodes.get(explicitParentId) || null : null
    const normalizedReference = normalizeReferenceId(getReferenceId(node.item))
    const immediateNumericParentReference = getImmediateNumericParentReference(normalizedReference)

    if (immediateNumericParentReference) {
      const immediateNumericParentNode = referenceIndex.get(immediateNumericParentReference)
      if (immediateNumericParentNode && immediateNumericParentNode !== node) {
        return immediateNumericParentNode
      }
    }

    if (explicitParentNode && explicitParentNode !== node) {
      return explicitParentNode
    }

    for (const candidate of getParentReferenceCandidates(normalizedReference)) {
      const fallbackParentNode = referenceIndex.get(candidate)
      if (fallbackParentNode && fallbackParentNode !== node) {
        return fallbackParentNode
      }
    }

    return null
  }

  const roots: HierarchyNode<T>[] = []
  nodes.forEach((node) => {
    const parentNode = resolveParentNode(node)
    if (parentNode) {
      parentNode.children.push(node)
      return
    }
    roots.push(node)
  })

  const sortNodes = (list: HierarchyNode<T>[]) => {
    list.sort((left, right) => {
      const refCompare = compareReferenceIds(
        getReferenceId(left.item),
        getReferenceId(right.item)
      )
      if (refCompare !== 0) return refCompare
      return getSortOrder(left.item) - getSortOrder(right.item)
    })
    list.forEach((child) => sortNodes(child.children))
  }

  sortNodes(roots)
  return roots
}

export const flattenHierarchyTree = <T>(nodes: HierarchyNode<T>[]): FlattenedHierarchyItem<T>[] => {
  const flattened: FlattenedHierarchyItem<T>[] = []

  const walk = (node: HierarchyNode<T>, depth: number) => {
    flattened.push({ item: node.item, depth })
    node.children.forEach((child) => walk(child, depth + 1))
  }

  nodes.forEach((node) => walk(node, 0))
  return flattened
}

// Preserve the resolved hierarchy, including numeric parents, when filters remove rows.
// Ancestors are navigation context, not additional filter matches.
export const withHierarchyContext = <T>(
  rows: FlattenedHierarchyItem<T>[],
  matches: (item: T) => boolean,
): Array<FlattenedHierarchyItem<T> & { isContext: boolean }> => {
  const ancestors: number[] = []
  const included = new Set<number>()
  const matching = new Set<number>()
  rows.forEach(({ item, depth }, index) => {
    while (ancestors.length && rows[ancestors[ancestors.length - 1]].depth >= depth) ancestors.pop()
    if (matches(item)) {
      matching.add(index)
      included.add(index)
      ancestors.forEach((ancestor) => included.add(ancestor))
    }
    ancestors.push(index)
  })
  return rows.flatMap((row, index) => included.has(index) ? [{ ...row, isContext: !matching.has(index) }] : [])
}
