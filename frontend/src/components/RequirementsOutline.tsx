import { useEffect, useMemo, useState } from 'react'
import type { OutlineNode } from '../utils/requirementsOutline'
import Tooltip from './ui/Tooltip'
import HierarchyDepthSelect from './HierarchyDepthSelect'
import { useHierarchyDepth, type HierarchyLevels } from '../hooks/useHierarchyDepth'

type OutlineGroup = {
  key: string
  title: string
  nodes: OutlineNode[]
}

function countLevels(nodes: OutlineNode[], fallbackDepth = 0): number {
  return nodes.reduce((max, node) => {
    const depth = node.depth ?? fallbackDepth
    return Math.max(max, depth + 1, countLevels(node.children, depth + 1))
  }, 0)
}

function targetPath(nodes: OutlineNode[], targetId: string, groupKey: string, ancestors: string[] = []): string[] | null {
  for (const node of nodes) {
    if (node.targetId === targetId) return ancestors
    const found = targetPath(node.children, targetId, groupKey, [...ancestors, `${groupKey}:${node.key}`])
    if (found) return found
  }
  return null
}

export default function RequirementsOutline({
  groups,
  onNavigate,
  selectedTargetId,
  levels,
  onLevelsChange,
  showDepthControl = true,
  maxLevels: totalLevels,
}: {
  groups: OutlineGroup[]
  onNavigate: (targetId: string) => void
  selectedTargetId?: string
  levels?: HierarchyLevels
  onLevelsChange?: (levels: HierarchyLevels) => void
  showDepthControl?: boolean
  maxLevels?: number
}) {
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})
  const [collapsedNodes, setCollapsedNodes] = useState<Record<string, boolean>>({})
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const preference = useHierarchyDepth()
  const visibleLevels = levels ?? preference.levels

  const groupList = useMemo(() => groups.filter((g) => g.nodes.length > 0), [groups])
  const maxLevels = useMemo(() => Math.max(1, totalLevels ?? 1, ...groupList.map((group) => countLevels(group.nodes))), [groupList, totalLevels])
  const selectedPathKey = useMemo(() => {
    if (!selectedTargetId) return ''
    for (const group of groupList) {
      const ancestors = targetPath(group.nodes, selectedTargetId, group.key)
      if (ancestors) return JSON.stringify({ groupKey: group.key, ancestors })
    }
    return ''
  }, [groupList, selectedTargetId])

  useEffect(() => {
    setCollapsedGroups({})
    setCollapsedNodes({})
  }, [visibleLevels])

  useEffect(() => {
    if (!selectedPathKey) return
    const { groupKey, ancestors } = JSON.parse(selectedPathKey) as { groupKey: string; ancestors: string[] }
    setCollapsedGroups((current) => ({ ...current, [groupKey]: false }))
    setCollapsedNodes((current) => ({ ...current, ...Object.fromEntries(ancestors.map((key) => [key, false])) }))
  }, [selectedPathKey, selectedTargetId])

  const changeVisibleLevels = (next: HierarchyLevels) => {
    const updateLevels = onLevelsChange ?? preference.changeLevels
    updateLevels(next)
    setCollapsedGroups({})
    setCollapsedNodes({})
  }

  const iconColSize = 24 // px; keep label alignment stable with/without expand affordance

  const toggleGroup = (key: string) => {
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const toggleNode = (key: string, isCollapsed: boolean) => {
    setCollapsedNodes((prev) => ({ ...prev, [key]: !isCollapsed }))
  }

  const renderNodes = (nodes: OutlineNode[], fallbackDepth: number, groupKey: string, revealChildren = false) => {
    return nodes.map((node) => {
      const depth = node.depth ?? fallbackDepth
      const namespacedKey = `${groupKey}:${node.key}`
      // Hiding headings must not promote their children into the selected levels.
      if (!revealChildren && visibleLevels !== 'all' && depth >= visibleLevels) {
        if (collapsedNodes[namespacedKey] !== false && (node.targetId !== selectedTargetId || collapsedGroups[groupKey] !== false)) return null
      }
      const defaultCollapsed = visibleLevels !== 'all' && node.children.every((child) => (child.depth ?? depth + 1) >= visibleLevels)
      const isCollapsed = collapsedNodes[namespacedKey] ?? defaultCollapsed
      const isActive = selectedTargetId ? selectedTargetId === node.targetId : activeKey === namespacedKey
      const hasChildren = node.children.length > 0

      return (
        <div key={namespacedKey}>
          <div
            className={`flex items-center gap-1 rounded px-2 py-1 text-sm transition ${
              isActive ? 'bg-strong text-white' : 'text-ink hover:bg-subtle'
            }`}
            style={{ paddingLeft: `${8 + depth * 12}px` }}
          >
            <div
              className="shrink-0"
              style={{ width: `${iconColSize}px`, height: `${iconColSize}px` }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${node.label}`}
                  aria-expanded={!isCollapsed}
                  onClick={() => toggleNode(namespacedKey, isCollapsed)}
                  className={`flex h-full w-full items-center justify-center rounded ${
                    isActive ? 'hover:bg-surface/10' : 'hover:bg-line'
                  }`}
                >
                  <span className="inline-block text-xs leading-none">
                    {isCollapsed ? '>' : 'v'}
                  </span>
                </button>
              ) : null}
            </div>

            <Tooltip content={node.isFlagged ? `${node.label} (flagged: ${node.flagReason || 'Extraction review'})` : node.label}><button
              type="button"
              onClick={() => {
                setActiveKey(namespacedKey)
                onNavigate(node.targetId)
              }}
              disabled={node.isContext}
              title={node.isContext ? 'Parent context; does not match the current filters' : undefined}
              data-testid="requirements-outline-row"
              aria-current={isActive ? 'true' : undefined}
              data-target-id={node.targetId}
              data-node-key={namespacedKey}
              className="min-w-0 flex-1 text-left disabled:text-muted"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="block min-w-0 flex-1 truncate">{node.label}</span>
                {node.isFlagged ? (
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      isActive ? 'bg-warning-soft text-warning' : 'bg-warning-soft text-warning'
                    }`}
                  >
                    Flagged
                  </span>
                ) : null}
              </span>
            </button></Tooltip>
          </div>

          {hasChildren && !isCollapsed && (
            <div className="mt-0.5">{renderNodes(node.children, depth + 1, groupKey, collapsedNodes[namespacedKey] === false)}</div>
          )}
        </div>
      )
    })
  }

  return (
    <div role="region" aria-label="Requirements outline" className="rounded-lg border border-line bg-surface">
      <div className="sticky top-0 z-10 space-y-2 rounded-t-lg border-b border-line bg-surface px-3 py-2">
        {showDepthControl && <HierarchyDepthSelect levels={visibleLevels} maxLevels={maxLevels} onChange={changeVisibleLevels} />}
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Outline</div>
      </div>
      <div className="p-2 space-y-2">
        {groupList.length === 0 && <p className="p-1 text-sm text-muted">No outline items.</p>}
        {groupList.map((group) => {
          const isCollapsed = !!collapsedGroups[group.key]
          return (
            <div key={group.key} className="rounded-md border border-line">
              <button
                type="button"
                onClick={() => toggleGroup(group.key)}
                aria-expanded={!isCollapsed}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
              >
                <span className="min-w-0 truncate text-sm font-semibold text-ink">
                  {group.title}
                </span>
                <span
                  aria-hidden="true"
                  className="text-xs text-muted"
                >
                  {isCollapsed ? '>' : 'v'}
                </span>
              </button>
              {!isCollapsed && (
                <div className="border-t border-line p-2">
                  {renderNodes(group.nodes, 0, group.key)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
