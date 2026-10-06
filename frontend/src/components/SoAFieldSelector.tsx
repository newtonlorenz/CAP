import Modal from './ui/Modal'
import { useMemo } from 'react'

import { ALL_SOA_FIELD_KEYS, READABLE_SOA_FIELD_KEYS, SOA_FIELD_GROUPS } from '../utils/soaFields'

type SoAFieldSelectorProps = {
  open: boolean
  selected: string[]
  onChange: (next: string[]) => void
  onClose: () => void
  onConfirm: () => void
  title?: string
}

export default function SoAFieldSelector({
  open,
  selected,
  onChange,
  onClose,
  onConfirm,
  title = 'Statement of Applicability Fields',
}: SoAFieldSelectorProps) {
  const selectedSet = useMemo(() => new Set(selected), [selected])

  if (!open) return null

  const setOrderedSelection = (next: Set<string>) => {
    const ordered = ALL_SOA_FIELD_KEYS.filter((fieldKey) => next.has(fieldKey))
    onChange(ordered)
  }

  const toggleField = (key: string) => {
    const next = new Set(selectedSet)
    if (next.has(key)) {
      next.delete(key)
    } else {
      next.add(key)
    }
    setOrderedSelection(next)
  }

  const selectAll = () => onChange([...ALL_SOA_FIELD_KEYS])
  const unselectAll = () => onChange([])

  const selectGroup = (keys: string[]) => {
    const next = new Set(selectedSet)
    keys.forEach((key) => next.add(key))
    setOrderedSelection(next)
  }

  const unselectGroup = (keys: string[]) => {
    const next = new Set(selectedSet)
    keys.forEach((key) => next.delete(key))
    setOrderedSelection(next)
  }

  return (
    <Modal open={open} title={title} onClose={onClose} size="lg">
        <div className="mb-4 flex flex-wrap gap-2">
          <button type="button" onClick={() => onChange([...READABLE_SOA_FIELD_KEYS])} className="rounded-full border border-line-strong px-3 py-1 text-sm text-ink">Recommended fields</button>
          <button
            type="button"
            onClick={selectAll}
            className="rounded-full border border-line-strong bg-surface/85 px-3 py-1 text-sm text-ink hover:border-brand-line hover:text-accent"
          >
            Select all
          </button>
          <button
            type="button"
            onClick={unselectAll}
            className="rounded-full border border-line-strong bg-surface/85 px-3 py-1 text-sm text-ink hover:border-brand-line hover:text-accent"
          >
            Unselect all
          </button>
          <span className="text-sm text-muted">
            {selected.length} selected
          </span>
        </div>

        <div className="space-y-6">
          {SOA_FIELD_GROUPS.map((group) => {
            const groupKeys = group.fields.map((field) => field.key)
            const selectedCount = groupKeys.filter((key) => selectedSet.has(key)).length
            const allSelected = selectedCount === groupKeys.length
            const indeterminate = selectedCount > 0 && !allSelected
            return (
              <div key={group.id}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <label className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = indeterminate
                      }}
                      onChange={() => (allSelected ? unselectGroup(groupKeys) : selectGroup(groupKeys))}
                    />
                    {group.label}
                  </label>
                  <div className="flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => selectGroup(groupKeys)}
                      className="rounded-full border border-line-strong bg-surface/85 px-2.5 py-1 text-ink hover:border-brand-line hover:text-accent"
                    >
                      Select section
                    </button>
                    <button
                      type="button"
                      onClick={() => unselectGroup(groupKeys)}
                      className="rounded-full border border-line-strong bg-surface/85 px-2.5 py-1 text-ink hover:border-brand-line hover:text-accent"
                    >
                      Unselect section
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {group.fields.map((field) => (
                    <label
                      key={field.key}
                      className="flex items-center gap-2 text-sm text-ink"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSet.has(field.key)}
                        onChange={() => toggleField(field.key)}
                      />
                      <span>{field.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-line-strong bg-surface/85 px-4 py-2 text-ink hover:border-brand-line hover:text-accent"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={selected.length === 0}
            className="rounded-lg border border-transparent bg-brand px-4 py-2 text-white transition-all hover:bg-brand-hover disabled:opacity-50"
          >
            Download
          </button>
        </div>
    </Modal>
  )
}
