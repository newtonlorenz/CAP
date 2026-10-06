import { useState, type FormEvent } from 'react'
import type { ApplicationStatus } from '../../types/applications'
import Button from '../ui/Button'
import { Field, inputClass } from './Fields'
export default function LifecycleActions({ status, ready, busy, hasOpenQueries, canManage, canApprove, onAction }: {
  status: ApplicationStatus; ready: boolean; busy: boolean; hasOpenQueries: boolean; canManage: boolean; canApprove: boolean
  onAction: (action: string, body: { notes?: string; reason?: string; submitted_at?: string; reference?: string; outcome?: string }) => Promise<boolean>
}) {
  const [action, setAction] = useState('')
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')
  const [reference, setReference] = useState('')
  const [submittedAt, setSubmittedAt] = useState('')
  const [outcome, setOutcome] = useState('')
  const labels: Record<string, string> = { 'request-review': 'Send for internal review', approve: 'Approve and freeze pack', 'return-to-draft': 'Return to draft', 'record-submission': 'Record submission', 'start-follow-up': 'Start follow-up', complete: 'Record outcome and complete' }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (await onAction(action, { ...(notes.trim() ? { notes: notes.trim() } : {}), ...(action === 'return-to-draft' ? { reason: reason.trim() } : {}), ...(action === 'record-submission' ? { reference: reference.trim(), submitted_at: new Date(submittedAt).toISOString() } : {}), ...(action === 'complete' ? { outcome: outcome.trim() } : {}) })) { setAction(''); setNotes(''); setReason(''); setReference(''); setSubmittedAt(''); setOutcome('') }
  }
  const choose = (value: string) => {
    if (value === 'record-submission' && action !== value) { const now = new Date(); setSubmittedAt(new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 23)) }
    setAction(action === value ? '' : value)
  }
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-2">
      {canManage && status === 'draft' && <Button variant="primary" disabled={busy || !ready} onClick={() => choose('request-review')}>Send for internal review</Button>}
      {canApprove && status === 'in_review' && <Button variant="primary" disabled={busy || !ready} onClick={() => choose('approve')}>Approve pack internally</Button>}
      {canManage && status === 'approved' && <Button variant="primary" disabled={busy || !ready} onClick={() => choose('record-submission')}>Record submission</Button>}
      {canManage && status === 'submitted' && <Button disabled={busy} onClick={() => choose('start-follow-up')}>Start follow-up</Button>}
      {canManage && (status === 'submitted' || status === 'follow_up') && <Button disabled={busy || hasOpenQueries} onClick={() => choose('complete')}>Record outcome</Button>}
      {(canManage || canApprove) && status !== 'draft' && <Button disabled={busy} onClick={() => choose('return-to-draft')}>Return to draft</Button>}
    </div>
    {hasOpenQueries && (status === 'submitted' || status === 'follow_up') && <p className="text-sm text-warning">Resolve all authority queries before recording the final outcome. An internal pack approval does not record a licence decision.</p>}
    {action && <form onSubmit={submit} className="rounded-xl border border-line p-4"><fieldset disabled={busy} className="space-y-4">
      <h4 className="font-semibold">{labels[action]}</h4>
      {action === 'approve' && <p className="text-sm text-muted">Freeze an immutable version of the included forms and accompanying evidence for internal approval. This does not record an authority decision.</p>}
      {action === 'record-submission' && <><p className="text-sm text-muted">Record a submission already made to the authority. CAP does not send the pack.</p><Field label="Submission reference"><input required className={inputClass} value={reference} onChange={(e) => setReference(e.target.value)} /></Field><Field label="Submitted at (local time)"><input required type="datetime-local" step="0.001" className={inputClass} value={submittedAt} onChange={(e) => setSubmittedAt(e.target.value)} /></Field></>}
      {action === 'return-to-draft' && <><p className="text-sm text-muted">Revise the working application and obtain a new approval before another submission. Earlier approved packs and submission records remain in history.</p><Field label="Reason for reopening"><textarea required className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} /></Field></>}
      {action === 'complete' && <Field label="Authority decision / outcome"><textarea required className={inputClass} rows={3} placeholder="Record the decision, reference and any conditions." value={outcome} onChange={(e) => setOutcome(e.target.value)} /></Field>}
      <Field label="Decision notes"><textarea className={inputClass} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <div className="flex gap-2"><Button type="submit" variant="primary" loading={busy}>Confirm: {labels[action]}</Button><Button onClick={() => setAction('')}>Cancel</Button></div>
    </fieldset></form>}
  </div>
}
