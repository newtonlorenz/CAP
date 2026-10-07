import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { pilotReviewApi } from '../api/pilotReview'
import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import type { ReviewQueueFilters, ReviewQueueItem } from '../types/pilotReview'
import { formatDateTime } from '../utils/dateFormat'
import Button from '../components/ui/Button'
import EvidenceAttachments from '../components/preparation/EvidenceAttachments'
import EvidencePreview from '../components/preparation/EvidencePreview'
import AnswerHistory from '../components/preparation/AnswerHistory'
import PilotIcon from '../components/preparation/PilotIcon'
import '../components/preparation/pilot.css'

const PAGE_SIZE = 10
export default function AnswerReview() {
  const { jurisdictionId } = useJurisdiction()
  const { user } = useAuth()
  const positionKey = `cap-answer-review:${user?.id || 'signed-out'}:${jurisdictionId}`
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const [returnOpen, setReturnOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [preview, setPreview] = useState('')
  const [reviewConfirmed, setReviewConfirmed] = useState(true)
  const reviewedRevision = useRef<{ key: string; revision: number } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const listElement = useRef<HTMLDivElement>(null)
  const page = Math.max(0, Number(params.get('page')) || 0)
  const status = params.get('status') === 'changes_requested' ? 'changes_requested' : params.get('status') === 'all' ? 'all' : 'pending_review'
  const filters: ReviewQueueFilters = { jurisdiction_id: jurisdictionId || undefined, case_id: params.get('case_filter') || undefined, q: params.get('q') || undefined, status, changed_evidence: params.get('changed') === '1' || undefined, overdue: params.get('overdue') === '1' || undefined, unassigned: params.get('unassigned') === '1' || undefined, include_excluded: params.get('excluded') === '1', skip: page * PAGE_SIZE, limit: PAGE_SIZE }
  const queue = useQuery({ queryKey: ['preparation', 'review-queue', filters], queryFn: () => pilotReviewApi.reviewQueue(filters), enabled: Boolean(jurisdictionId) })
  const items = queue.data?.items || []
  const caseId = params.get('case') || items[0]?.case_id || ''
  const fieldKey = params.get('field') || items[0]?.field_key || ''
  const selectedRow = items.find(item => item.case_id === caseId && item.field_key === fieldKey)
  const detail = useQuery({ queryKey: ['preparation', 'case', caseId], queryFn: () => pilotReviewApi.getCase(caseId), enabled: Boolean(caseId) })
  const form = detail.data
  const field = form?.fields.find(item => item.key === fieldKey)
  const response = form?.responses.find(item => item.field_key === fieldKey)
  const currentPreview = response?.evidence_ids.includes(preview) ? preview : response?.evidence_ids[0] || ''
  const questionIndex = form?.fields.findIndex(item => item.key === fieldKey) ?? -1
  const ownerName = selectedRow?.owner_name || (form?.owner_id ? 'Assigned contributor' : 'Contributor unassigned')
  const canApprove = Boolean(user && ['admin', 'manager'].includes(user.role) && (selectedRow?.can_approve ?? Boolean(form?.access?.permissions.includes('approve'))))
  const hasAnswer = Boolean(response && (response.value !== null || response.not_applicable_reason || response.evidence_ids.length))
  useDraftNavigationGuard(Boolean(comment.trim()) || busy)
  const update = (changes: Record<string, string | null>, replace = false) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) }
    setParams(next, { replace })
  }
  useEffect(() => {
    if (!params.toString()) {
      try { const saved = sessionStorage.getItem(positionKey); if (saved) setParams(saved, { replace: true }) } catch { /* URL navigation still retains state when storage is unavailable. */ }
    }
  // Restore once for each market; filters and selection otherwise remain in the URL.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionKey])
  useEffect(() => { try { if (params.toString()) sessionStorage.setItem(positionKey, params.toString()) } catch { /* Optional navigation convenience. */ } }, [params, positionKey])
  useEffect(() => {
    setPreview(''); setError(''); setComment(''); setReturnOpen(false); setReviewConfirmed(true)
    heading.current?.focus()
  }, [caseId, fieldKey])
  useEffect(() => {
    if (!form) return
    const key = `${caseId}:${fieldKey}`
    if (reviewedRevision.current?.key === key && reviewedRevision.current.revision !== form.revision && !busy) {
      setReviewConfirmed(false)
      setError('This form changed while you were reviewing. Review the latest saved answer and evidence before deciding.')
    }
    reviewedRevision.current = { key, revision: form.revision }
  }, [caseId, fieldKey, form, busy])
  useEffect(() => {
    try { if (listElement.current) listElement.current.scrollTop = Number(sessionStorage.getItem(`${positionKey}:scroll:${page}`)) || 0 } catch { /* No persisted scroll available. */ }
  }, [queue.data, positionKey, page])
  const select = (row: Pick<ReviewQueueItem, 'case_id' | 'field_key'>) => {
    if (busy) return
    update({ case: row.case_id, field: row.field_key })
  }
  const changeFilter = (key: string, value: string | null) => update({ [key]: value, ...(key === 'status' ? { changed: null } : {}), page: null, case: null, field: null })
  const advance = async (message: string, afterMutation: boolean) => {
    const index = items.findIndex(item => item.case_id === caseId && item.field_key === fieldKey)
    const next = items[index + 1]
    if (afterMutation) await client.invalidateQueries({ queryKey: ['preparation', 'review-queue'] })
    if (next) select(next)
    else if (!afterMutation && (page + 1) * PAGE_SIZE < (queue.data?.total || 0)) update({ page: String(page + 1), case: null, field: null })
    else if (afterMutation) {
      const fresh = await queue.refetch()
      if (fresh.data?.items[0]) select(fresh.data.items[0])
      else update({ page: page > 0 ? String(page - 1) : null, case: null, field: null })
    } else if (items[0] && items[0] !== selectedRow) select(items[0])
    setAnnouncement(message)
    window.setTimeout(() => heading.current?.focus(), 0)
  }
  const decide = async (action: 'accept' | 'return') => {
    if (!form || !field || busy || !reviewConfirmed || !canApprove || (action === 'return' && !comment.trim())) return
    setBusy(true); setError('')
    try {
      const updated = action === 'accept' ? await pilotReviewApi.acceptResponse(form.id, field.key, form.revision) : await pilotReviewApi.returnResponse(form.id, field.key, { expected_revision: form.revision, comment: comment.trim() })
      await client.cancelQueries({ queryKey: ['preparation', 'case', form.id], exact: true })
      client.setQueryData(['preparation', 'case', form.id], updated)
      setComment(''); setReturnOpen(false)
      // Route transitions happen only after the server's decision acknowledgement.
      const index = items.findIndex(item => item.case_id === caseId && item.field_key === fieldKey)
      const next = items[index + 1]
      await client.invalidateQueries({ queryKey: ['preparation', 'review-queue'] })
      await client.invalidateQueries({ queryKey: ['dashboard'] })
      const fresh = await queue.refetch()
      if (next) update({ case: next.case_id, field: next.field_key })
      else if (fresh.data?.items[0]) update({ case: fresh.data.items[0].case_id, field: fresh.data.items[0].field_key })
      else update({ page: page > 0 ? String(page - 1) : null, case: null, field: null })
      setAnnouncement(action === 'accept' ? 'Answer and attached evidence accepted. Review queue advanced.' : `Changes requested from ${ownerName}. Review queue advanced.`)
      window.setTimeout(() => heading.current?.focus(), 0)
    } catch (caught) {
      setError(getApiErrorMessage(caught, 'The decision could not be saved. Your queue position and comment are retained.'))
      setReviewConfirmed(false)
      await detail.refetch()
    } finally { setBusy(false) }
  }
  return <div className="pilot-review-page">
    <header className="pilot-review-heading"><div><h1>Answer review</h1><p>{queue.data ? `${queue.data.total} ${status === 'changes_requested' ? 'returned' : status === 'all' ? '' : 'pending'} answers in your accessible forms` : 'Review answers and their supporting evidence'}</p></div></header>
    <nav className="pilot-overview-tabs" aria-label="Overview sections"><Link to="/">My work</Link><Link to="/?view=team">Team work</Link><span aria-current="page">Answer review</span></nav>
    <div className="pilot-review-workspace">
      <div className="pilot-review-filters">{params.has('case_filter') && <button type="button" className="text-accent underline" onClick={() => changeFilter('case_filter', null)}>All forms</button>}<div className="pilot-review-status-tabs">{[['pending_review', 'Pending acceptance'], ['changes_requested', 'Changes requested'], ['all', 'All answers']].map(([key, label]) => <button key={key} type="button" className={status === key && !params.has('changed') ? 'is-active' : ''} onClick={() => changeFilter('status', key === 'pending_review' ? null : key)}>{label}</button>)}<button type="button" className={params.get('changed') === '1' ? 'is-active' : ''} onClick={() => update({ status: null, changed: '1', page: null, case: null, field: null })}>Changed evidence</button></div><label className="pilot-review-search"><PilotIcon name="search" size={18} /><input type="search" aria-label="Find an answer" placeholder="Find an answer" value={params.get('q') || ''} onChange={event => changeFilter('q', event.target.value || null)} /></label><label><input type="checkbox" checked={params.get('overdue') === '1'} onChange={event => changeFilter('overdue', event.target.checked ? '1' : null)} />Overdue</label><label><input type="checkbox" checked={params.get('unassigned') === '1'} onChange={event => changeFilter('unassigned', event.target.checked ? '1' : null)} />Unassigned</label><label><input type="checkbox" checked={params.get('excluded') === '1'} onChange={event => changeFilter('excluded', event.target.checked ? '1' : null)} />Include excluded forms</label></div>
      <div className="pilot-review-columns"><aside className="pilot-review-queue" aria-label="Answer review queue"><header><h2>Answers you can review</h2><p>{queue.data?.total ?? '—'} answers · Page {page + 1} of {Math.max(1, Math.ceil((queue.data?.total || 0) / PAGE_SIZE))}</p></header>{form && field && !selectedRow && <div className="pilot-pinned-answer"><small>Opened answer · Outside this queue page</small><strong>{form.name}</strong><span>{field.label}</span><button type="button" className="text-accent underline" onClick={() => update({ case_filter: form.id, page: null, q: null, status: 'all', changed: null, overdue: null, unassigned: null })}>Show this form’s answers</button></div>}<div className="pilot-review-list" ref={listElement} onScroll={event => { try { sessionStorage.setItem(`${positionKey}:scroll:${page}`, String(event.currentTarget.scrollTop)) } catch { /* Optional persisted scroll. */ } }}>
        {queue.isLoading ? <p role="status">Loading review queue…</p> : queue.isError ? <p role="alert">The review queue could not be loaded. <Button onClick={() => void queue.refetch()}>Retry</Button></p> : !items.length ? <div className="pilot-empty"><h3>No answers match</h3><p>{status === 'pending_review' ? 'There are no pending answers for these filters.' : 'Try another filter to find an answer.'}</p></div> : items.map(item => <button key={`${item.case_id}:${item.field_key}`} type="button" disabled={busy} className={`pilot-review-row ${item.case_id === caseId && item.field_key === fieldKey ? 'is-selected' : ''}`} aria-current={item.case_id === caseId && item.field_key === fieldKey ? 'true' : undefined} onClick={() => select(item)}><PilotIcon name="file" size={25} /><span><strong>{item.case_name}</strong><small>{item.question}</small><small>{item.owner_name || 'Contributor unassigned'}</small></span><span className="pilot-row-state"><i className={`pilot-dot ${item.review_status === 'accepted' ? 'ready' : 'pending'}`} />{item.review_status === 'accepted' ? 'Accepted' : item.review_status === 'changes_requested' ? 'Changes requested' : item.open_feedback_count ? 'Feedback open' : item.change_kind === 'evidence_changed' ? 'Evidence changed' : item.change_kind === 'answer_updated' ? 'Answer updated' : item.change_kind === 'new_answer' ? 'New answer' : 'Pending acceptance'}</span></button>)}
      </div><footer><Button size="sm" disabled={page === 0 || busy} onClick={() => update({ page: page > 1 ? String(page - 1) : null, case: null, field: null })}>Previous page</Button><span>{page + 1}</span><Button size="sm" disabled={busy || (page + 1) * PAGE_SIZE >= (queue.data?.total || 0)} onClick={() => update({ page: String(page + 1), case: null, field: null })}>Next page</Button><small>Queue position is kept when you return.</small></footer></aside>
      <section className="pilot-review-detail" aria-label="Selected answer"><div role="status" className="sr-only" aria-live="polite">{announcement}</div>
        {!caseId ? <div className="pilot-empty"><h2>Choose an answer to review</h2><p>The question, answer and evidence will appear here.</p></div> : detail.isLoading ? <p role="status">Loading answer…</p> : detail.isError ? <p role="alert">The selected form could not be loaded. <Button onClick={() => void detail.refetch()}>Retry</Button></p> : !field || form?.summary_only ? <p role="alert">This question is not available. Choose another answer in the queue.</p> : <>
          <div className="pilot-review-content"><div className="pilot-review-context"><Link to={`/preparation?case=${encodeURIComponent(caseId)}`}>{form?.name}</Link><span>Question {questionIndex + 1} of {form?.fields.length}</span><div className="pilot-review-question-nav"><Button size="sm" disabled={busy || questionIndex <= 0} onClick={() => update({ case: caseId, field: form!.fields[questionIndex - 1].key })}>Previous question</Button><select aria-label="Question in this form" value={fieldKey} disabled={busy} onChange={event => update({ case: caseId, field: event.target.value })}>{form?.fields.map((question, index) => <option key={question.key} value={question.key}>{index + 1} of {form.fields.length}</option>)}</select><Button size="sm" disabled={busy || questionIndex >= (form?.fields.length || 0) - 1} onClick={() => update({ case: caseId, field: form!.fields[questionIndex + 1].key })}>Next question</Button></div></div>
          <h2 ref={heading} tabIndex={-1}>{field.label}</h2><p className={response?.accepted_at ? 'text-success' : 'text-warning'}><i className={`pilot-dot ${response?.accepted_at ? 'ready' : 'pending'}`} />{response?.accepted_at ? 'Accepted' : response?.review_status === 'changes_requested' ? 'Changes requested' : 'Pending acceptance'}</p>{field.help_text && <p className="pilot-review-guidance">{field.help_text}</p>}
          <section className="pilot-review-answer"><h3>Answer</h3><div>{response?.not_applicable_reason ? `Not applicable: ${response.not_applicable_reason}` : response?.value == null ? 'No answer text provided.' : typeof response.value === 'boolean' ? response.value ? 'Yes' : 'No' : String(response.value)}</div></section>
          <div className="pilot-change-note"><p>{response?.last_saved_at ? `Answer last saved ${formatDateTime(response.last_saved_at)}.` : 'Review the saved answer and attached evidence together.'}</p><small>Changing an answer or its evidence clears the earlier acceptance.</small></div>
          {response?.feedback?.filter(item => !item.resolved_at).map(item => <section key={item.id} className="pilot-feedback"><h3>Open feedback · {item.created_by_name || 'Reviewer'}</h3><p>{item.comment}</p><small>Accepting this answer resolves this feedback.</small></section>)}
          <h3 className="pilot-evidence-heading">Evidence attached to this answer</h3><EvidenceAttachments ids={response?.evidence_ids || []} />
          {(response?.evidence_ids.length || 0) > 1 && <label className="pilot-preview-select">Preview attachment<select value={currentPreview} onChange={event => setPreview(event.target.value)}>{response!.evidence_ids.map((id, index) => <option key={id} value={id}>Attachment {index + 1}</option>)}</select></label>}
          {!!response?.evidence_ids.length && <EvidencePreview key={currentPreview} id={currentPreview} />}
          <AnswerHistory caseId={caseId} fieldKey={fieldKey} revision={form!.revision} />
          {error && <div role="alert" className="pilot-feedback"><p>{error}</p><p>Review the latest answer and evidence before deciding again. Your queue position is unchanged.</p><Button disabled={detail.isFetching || detail.isError} onClick={() => { setReviewConfirmed(true); setError('') }}>I have reviewed the latest answer</Button></div>}
          {returnOpen && <form className="pilot-return-form" onSubmit={event => { event.preventDefault(); void decide('return') }}><h3>Return for changes</h3><p>Next action: {ownerName}</p><label>Comment for the contributor<textarea required rows={4} value={comment} disabled={busy} onChange={event => setComment(event.target.value)} placeholder="Explain what needs to change before this answer can be accepted." /></label><Button variant="primary" type="submit" disabled={busy || !comment.trim() || !reviewConfirmed}>Send back for changes</Button><Button variant="ghost" disabled={busy} onClick={() => { setReturnOpen(false); setComment('') }}>Cancel</Button></form>}
          </div><footer className="pilot-review-actions"><p>Acceptance covers this answer and its attached evidence.</p><Button variant="primary" loading={busy} disabled={busy || !canApprove || !hasAnswer || Boolean(response?.accepted_at) || !reviewConfirmed || returnOpen} onClick={() => void decide('accept')}>Accept answer &amp; next</Button><Button disabled={busy || !canApprove || !hasAnswer || !reviewConfirmed} onClick={() => setReturnOpen(true)}>Return for changes</Button><Button variant="ghost" disabled={busy || Boolean(comment.trim())} onClick={() => void advance('Skipped for now. No decision was recorded.', false)}>Skip for now</Button>{!canApprove && <small>You do not have approval access to this form.</small>}{!form?.owner_id && <small>Contributor unassigned. Returned work will need an owner.</small>}</footer>
        </>}
      </section></div>
    </div>
  </div>
}
