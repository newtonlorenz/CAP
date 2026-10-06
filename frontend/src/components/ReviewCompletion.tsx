import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import type { ReviewCycleWithItems } from '../types'
import Modal from './ui/Modal'

export default function ReviewCompletion({ cycle, canComplete, onChanged, hasUnsavedChanges = false }: {
  cycle: ReviewCycleWithItems; canComplete: boolean; onChanged: () => void; hasUnsavedChanges?: boolean
}) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const readiness = cycle.readiness
  if (!readiness) return null
  const closed = Boolean(cycle.closed_at)
  const complete = async () => {
    if (hasUnsavedChanges) return
    setBusy(true); setError('')
    try {
      await api.post(`/review-cycles/${cycle.id}/close`)
      setConfirming(false); onChanged()
    } catch (err) { setError(getApiErrorMessage(err, 'Unable to complete the review.')); onChanged() }
    finally { setBusy(false) }
  }
  return <section aria-label="Review readiness" className="my-3 border-t border-line pt-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold text-ink">{closed ? 'Completed assessment' : 'Readiness for completion'}</h2>
        <p className="mt-1 text-sm text-muted">{closed ? readiness.snapshot_warning || 'Scope, decisions and evidence are frozen. Further work belongs in a new review.' : `${readiness.ready} of ${readiness.applicable} applicable controls ready · ${readiness.not_applicable} not applicable · ${readiness.informational} informational`}</p>
      </div>
      {closed ? <Link className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white" to={`/reports?section=reviews&review=${cycle.id}`}>Reports and evidence package</Link> : canComplete && cycle.status === 'active' && <button type="button" onClick={() => setConfirming(true)} disabled={!readiness.can_close || hasUnsavedChanges} className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Complete assessment</button>}
    </div>
    {!closed && hasUnsavedChanges && <p role="status" className="mt-3 text-sm text-muted">Save your evidence and wait for current changes to finish before completing this review.</p>}
    {!closed && readiness.blocker_count > 0 && <details className="mt-2">
      <summary className="text-sm font-semibold text-ink">{readiness.blocker_count} {readiness.blocker_count === 1 ? 'requirement needs' : 'requirements need'} attention before completion</summary>
      <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm">
        {readiness.blockers.map((blocker, index) => <li key={blocker.item_id || index} className="flex flex-wrap gap-x-2">
          {blocker.item_id ? <Link className="font-semibold text-accent underline" to={`/review-cycles/${cycle.id}?mode=focus&item=${blocker.item_id}`}>{blocker.reference_id}</Link> : <span>{blocker.reference_id}</span>}
          <span className="text-muted">{blocker.reasons.join(' · ')}</span>
        </li>)}
      </ul>
    </details>}
    {error && !confirming && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    <Modal open={confirming} onClose={() => { if (!busy) setConfirming(false) }} title="Complete this review?">
      <p className="text-sm text-muted">This action freezes the reviewed scope, decisions, and supporting files. You can then download the reports and evidence package. Completion records internal readiness. Check submission and approval requirements with the receiving authority or certification body.</p>
      {error && <p role="alert" className="mt-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{error}</p>}
      <div className="mt-5 flex justify-end gap-3"><button type="button" disabled={busy} onClick={() => setConfirming(false)} className="rounded-lg border border-line-strong px-4 py-2">Continue assessment</button><button type="button" disabled={busy || hasUnsavedChanges} onClick={complete} className="rounded-lg bg-brand px-4 py-2 text-white">{busy ? 'Freezing assessment…' : 'Complete and freeze'}</button></div>
    </Modal>
  </section>
}
