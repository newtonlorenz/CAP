export type FlattenedNavItem = {
  key: string
  targetId: string
  referenceId: string
  title?: string | null
  depth: number
  isContext?: boolean
  isFlagged?: boolean
  flagReason?: string | null
}

export type OutlineNode = {
  depth?: number
  key: string
  targetId: string
  label: string
  isContext?: boolean
  isFlagged?: boolean
  flagReason?: string | null
  children: OutlineNode[]
}

export const defaultOutlineLabel = (referenceId: string, title?: string | null) => {
  const trimmedTitle = (title || '').trim()
  return trimmedTitle ? `${referenceId} ${trimmedTitle}` : referenceId
}

export const buildOutlineTree = (items: FlattenedNavItem[], maxDepth = 2): OutlineNode[] => {
  const roots: OutlineNode[] = []
  const stack: Array<{ depth: number; node: OutlineNode }> = []

  items.forEach((item) => {
    if (item.depth > maxDepth) return

    const node: OutlineNode = {
      key: item.key,
      depth: item.depth,
      isContext: item.isContext,
      targetId: item.targetId,
      label: defaultOutlineLabel(item.referenceId, item.title),
      isFlagged: !!item.isFlagged,
      flagReason: item.flagReason || null,
      children: [],
    }

    while (stack.length && stack[stack.length - 1]!.depth >= item.depth) {
      stack.pop()
    }

    const parent = stack[stack.length - 1]
    if (parent) {
      parent.node.children.push(node)
    } else {
      roots.push(node)
    }
    stack.push({ depth: item.depth, node })
  })

  return roots
}
