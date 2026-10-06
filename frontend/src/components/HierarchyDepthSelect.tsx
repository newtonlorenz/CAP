import { useId } from 'react'
import type { HierarchyLevels } from '../hooks/useHierarchyDepth'

export default function HierarchyDepthSelect({ levels, maxLevels, onChange }: {
  levels: HierarchyLevels
  maxLevels: number
  onChange: (levels: HierarchyLevels) => void
}) {
  const id = useId()
  const optionLevels = Math.max(1, maxLevels, levels === 'all' ? 1 : levels)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor={id} className="text-sm text-muted">Show levels</label>
      <select
        id={id}
        value={levels === 'all' ? 'all' : levels}
        onChange={(event) => onChange(event.target.value === 'all' ? 'all' : Number(event.target.value))}
        className="min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-2 py-1.5 text-sm text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <option value="1">Top level</option>
        {Array.from({ length: Math.max(0, optionLevels - 1) }, (_, index) => index + 2).map((count) => (
          <option key={count} value={count}>{count} levels</option>
        ))}
        <option value="all">All levels</option>
      </select>
    </div>
  )
}
