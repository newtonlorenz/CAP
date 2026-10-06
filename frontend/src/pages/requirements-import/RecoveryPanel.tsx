import { useState } from 'react'
import type { ExtractedRequirement } from '../../types'

export type RecoveryDecision = {
  action: 'correct' | 'attach_continuation' | 'exclude'
  reference_id?: string
  parent_reference?: string
  corrected_text?: string
  requirement_type?: string
  target_id?: string
}

type Props = {
  rows: ExtractedRequirement[]
  allRows: ExtractedRequirement[]
  sourceUrl: string
  working: boolean
  onResolve: (id: string, decision: RecoveryDecision) => void
}

export default function RecoveryPanel({ rows, allRows, sourceUrl, working, onResolve }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [reference, setReference] = useState('')
  const [parent, setParent] = useState('')
  const [text, setText] = useState('')
  const [kind, setKind] = useState('mandatory')
  const [targetId, setTargetId] = useState('')
  if (!rows.length) return null

  const select = (row: ExtractedRequirement) => {
    setSelectedId(row.id)
    setReference(row.reference_id.startsWith('unresolved-') ? '' : row.reference_id)
    setParent(row.reference_id.includes('.') && !row.reference_id.startsWith('unresolved-') ? row.reference_id.split('.').slice(0, -1).join('.') : '')
    setText(row.text)
    setKind(row.requirement_type)
    setTargetId('')
  }

  return <section aria-label="Structured import recovery" className="mb-6 rounded-lg border border-warning-line bg-warning-soft p-4">
    <h2 className="text-lg font-semibold text-ink">Resolve source structure</h2>
    <p className="mt-1 text-sm text-muted">Check each source page. Correct its reference and parent, attach an orphan continuation, or exclude it.</p>
    <p className="mt-1 text-sm text-muted">These {rows.length} candidates block approval until resolved. Source text remains available after correction.</p>
    <div className="mt-4 space-y-4">
      {rows.map(row => <article key={row.id} className="rounded-md border border-line bg-surface p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-ink">{row.reference_id.startsWith('unresolved-') ? 'Reference needs correction' : row.reference_id}</p>
            <p className="text-xs text-warning">{row.review_reason || 'Source structure needs review'}</p>
          </div>
          <a className="text-sm text-accent underline" href={`${sourceUrl}#page=${row.page_number}`} target="_blank" rel="noopener noreferrer">Source PDF, page {row.page_number}</a>
        </div>
        <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink">{row.source_excerpt || row.original_text}</p>
        {selectedId !== row.id ? <button type="button" onClick={() => select(row)} className="mt-3 rounded border border-line-strong px-3 py-1.5 text-sm text-ink">Resolve candidate</button> :
          <div className="mt-3 space-y-3 border-t border-line pt-3">
            <div className="grid gap-3 md:grid-cols-2">
              <label className="text-sm text-ink">Correct source reference<input aria-label="Correct source reference" value={reference} onChange={event => setReference(event.target.value)} className="mt-1 block w-full rounded border border-line-strong px-3 py-2" placeholder="2.3.1" /></label>
              <label className="text-sm text-ink">Immediate parent reference<input aria-label="Immediate parent reference" value={parent} onChange={event => setParent(event.target.value)} className="mt-1 block w-full rounded border border-line-strong px-3 py-2" placeholder="2.3 or empty for root" /></label>
            </div>
            <label className="block text-sm text-ink">Corrected text<textarea aria-label="Corrected text" value={text} onChange={event => setText(event.target.value)} rows={3} className="mt-1 block w-full rounded border border-line-strong px-3 py-2" /></label>
            <label className="block text-sm text-ink">Requirement type<select aria-label="Recovered requirement type" value={kind} onChange={event => setKind(event.target.value)} className="mt-1 block w-full rounded border border-line-strong px-3 py-2"><option value="mandatory">Mandatory</option><option value="recommended">Recommended</option><option value="informational">Informational</option><option value="not_applicable">Not applicable</option></select></label>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={working || !reference.trim() || !text.trim()} onClick={() => onResolve(row.id, { action: 'correct', reference_id: reference.trim(), parent_reference: parent.trim(), corrected_text: text, requirement_type: kind })} className="rounded bg-brand px-3 py-2 text-sm text-white disabled:opacity-50">Save correction</button>
              <button type="button" disabled={working} onClick={() => onResolve(row.id, { action: 'exclude' })} className="rounded border border-danger-line px-3 py-2 text-sm text-danger disabled:opacity-50">Exclude candidate</button>
              <button type="button" onClick={() => setSelectedId(null)} className="rounded border border-line-strong px-3 py-2 text-sm text-ink">Cancel</button>
            </div>
            {/orphan_continuation|ambiguous_unnumbered_table_row/.test(row.review_reason || '') && <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
              <label className="text-sm text-ink">Attach to numbered requirement<select aria-label="Continuation target" value={targetId} onChange={event => setTargetId(event.target.value)} className="mt-1 block w-full rounded border border-line-strong px-3 py-2"><option value="">Select a requirement</option>{allRows.filter(item => item.id !== row.id && item.status !== 'rejected' && /^\d+(?:\.\d+)*$/.test(item.reference_id)).map(item => <option key={item.id} value={item.id}>{item.reference_id} · page {item.page_number}</option>)}</select></label>
              <button type="button" disabled={working || !targetId} onClick={() => onResolve(row.id, { action: 'attach_continuation', target_id: targetId })} className="rounded border border-line-strong px-3 py-2 text-sm text-ink disabled:opacity-50">Attach continuation</button>
            </div>}
          </div>}
      </article>)}
    </div>
  </section>
}
