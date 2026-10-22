import { useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api/client'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, ProcessEvidence, ProcessTarget } from '../../types/documentation'
import { TD, TR } from '../ui/Table'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'
import { processTargetHref, reviewProcessHref, targetKey } from './processNavigation'

export default function RegisterEntryRow({ row, bound, canEdit, returnTo, onDetails, onEdit, onAssign, onReview, onMatch, onManage, onStandalone, onPreview }: {
  row: DocumentationExpectation; bound: boolean; canEdit: boolean; returnTo: string
  onDetails: () => void; onEdit: () => void; onAssign: () => void; onReview: () => void; onMatch: () => void; onManage: (target: ProcessTarget) => void
  onStandalone: () => void; onPreview: (id: string) => void
}) {
  const [error, setError] = useState('')
  const targets = row.process_targets || []
  const available = targets.filter(target => target.available)
  const singleHref = available.length === 1 && row.source_reference?.trim() === available[0].reference_id?.trim() ? processTargetHref(available[0], returnTo) : null
  const reviewHref = reviewProcessHref(row.process, returnTo)
  const actionClass = 'inline-flex min-h-8 max-w-full items-center rounded px-1 py-1 text-left text-xs font-semibold text-accent underline hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent'
  const download = async (item: ProcessEvidence) => {
    if (!item.download_href) return
    setError('')
    try { const result = await api.get<Blob>(item.download_href, { responseType: 'blob' }); const url = URL.createObjectURL(result.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = item.filename || item.title; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
    catch (caught) { setError(getApiErrorMessage(caught, 'The process document could not be downloaded.')) }
  }
  return <TR id={`documentation-row-${row.id}`} tabIndex={-1}>
    <TD className="align-top !px-3 !py-2"><p className="whitespace-pre-wrap break-words font-medium leading-normal">{row.required_documentation ?? row.title}</p><p className="mt-1 text-xs text-muted">Responsible owner: {row.owner_id ? row.owner_name || 'Assigned owner (unavailable)' : 'Unassigned'}</p></TD>
    <TD className="align-top !px-3 !py-2"><p className="whitespace-pre-wrap break-words leading-normal">{singleHref ? <Link className="text-accent underline" to={singleHref}>{row.source_reference}</Link> : row.source_reference || '—'}</p><p className="mt-1 text-xs text-muted">Certification review: {row.process ? row.process.available ? row.process.kind === 'review' ? reviewHref ? <Link className="text-accent underline" to={reviewHref}>{row.process.name}</Link> : row.process.name : 'Register licence process' : 'Unavailable' : 'Not linked'}{row.process?.kind === 'review' && row.process_inherited ? ' · Register default' : ''}</p>
      {bound ? <><ul className="mt-1 space-y-1">{available.map(target => { const href = processTargetHref(target, returnTo); return href && !singleHref ? <li key={targetKey(target)}><Link className="break-words text-accent underline" to={href}>{target.reference_id || 'Matched requirement'}</Link>{available.length > 1 && <span className="block break-words text-xs text-muted">{target.owner_name || target.case_name || target.set_name || target.title}</span>}</li> : null })}</ul>{targets.some(target => !target.available) && <p className="mt-1 text-xs text-muted">A matched process requirement is unavailable.</p>}{!targets.length && <p className="mt-1 text-xs text-muted">Reference needs an explicit match.</p>}</> : row.requirements.length > 0 && <ul className="mt-1 space-y-1">{row.requirements.map(link => <li key={link.requirement_id}><Link className="break-words text-accent underline" to={`/requirements/${link.requirement_id}`}>{link.reference_id || link.title || 'Linked requirement'}</Link></li>)}</ul>}
    </TD>
    <TD className="align-top !px-3 !py-2 whitespace-pre-wrap break-words leading-normal">{row.description || '—'}</TD>
    <TD className="align-top !px-3 !py-2"><p className="whitespace-pre-wrap break-words font-medium leading-normal">{row.document_name || (!row.coverage.length && !available.length ? '—' : '')}</p>
      {available.map(target => <section key={targetKey(target)} className="mt-1 space-y-1 border-t border-line pt-1 text-sm"><p className="break-words text-xs text-muted">{target.reference_id} · {target.kind === 'review_item' ? 'Assessment evidence' : target.case_name || 'Form evidence'}</p>{target.collection?.warning && <p className="text-xs text-muted">{target.collection.warning}</p>}<ul className="space-y-1">{target.collection?.items.map((item, index) => <li className="break-words" key={item.evidence_id || item.file_id || index}>{item.download_href ? <button type="button" className={actionClass} onClick={() => void download(item)} aria-label={`Download ${item.title}`}>{item.title}</button> : item.evidence_id && (item.evidence_kind === 'note' || item.evidence_kind === 'link') ? <button type="button" className={actionClass} onClick={() => onPreview(item.evidence_id!)} aria-label={`Open ${item.title}`}>{item.title}</button> : item.title}</li>)}</ul>{target.collection?.has_review_notes && <p className="text-xs text-muted">Assessment notes are recorded. Open the evidence collection to review them.</p>}{!target.collection?.items.length && !target.collection?.has_review_notes && !target.collection?.warning && <p className="text-xs text-muted">No documents in this process collection.</p>}</section>)}
      {bound && !targets.length && <p className="mt-1 text-xs text-muted">Match a process reference to use its document collection.</p>}
      {row.coverage.length > 0 && <><p className="mt-1 text-xs text-muted">{bound ? 'Standalone documents' : 'Linked documents'}</p><ul className="mt-1 space-y-1">{row.coverage.map(link => <li className="break-words" key={link.evidence_id}><button type="button" className={actionClass} onClick={() => onPreview(link.evidence_id)} aria-label={`Open ${link.evidence?.title || link.title || 'linked document'}`}>{link.evidence?.title || link.title || 'Linked document'}</button></li>)}</ul></>}
      {error && <p role="alert" className="mt-1 text-sm text-danger">{error}</p>}
    </TD>
    <TD className="align-top !px-3 !py-2">
      <div className="flex flex-wrap gap-1">
        <IconButton onClick={onDetails} title="Details" aria-label={`Details for ${row.title}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></svg></IconButton>
        {canEdit && <>
          <IconButton onClick={onEdit} title="Edit row" aria-label={`Edit row ${row.title}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><path d="m16 3 5 5-13 13H3v-5Z M14 5l5 5" /></svg></IconButton>
          <IconButton onClick={onAssign} title="Assign user" aria-label={`Assign user for ${row.title}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3 M19 7v6 M16 10h6" /></svg></IconButton>
          <IconButton onClick={onReview} title="Link certification review" aria-label={`Link certification review for ${row.title}`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7 .54l3-3a5 5 0 0 0-7-7l-1.72 1.71 M14 11a5 5 0 0 0-7-.54l-3 3a5 5 0 0 0 7 7l1.71-1.71" /></svg></IconButton>
          {bound && <IconButton onClick={onMatch} title={targets.length ? 'Change matches' : 'Match reference'} aria-label={targets.length ? 'Change matches' : 'Match reference'}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4" aria-hidden="true"><path d="m2 5 2 2 3-4 M10 5h12 m-20 8 2 2 3-4 M10 13h12 M2 21h5 M10 21h12" /></svg></IconButton>}
        </>}
      </div>
      {available.map(target => <div key={targetKey(target)} className="mt-1 space-y-1">
        {available.length > 1 && <p className="break-words text-xs text-muted">{target.reference_id}</p>}
        <button type="button" className={actionClass} onClick={() => onManage(target)}>{target.collection?.can_edit && !target.collection.readonly ? 'Manage documents' : 'View documents'}</button>
      </div>)}
      {canEdit && targets.length === 0 && <Button className="mt-1" size="sm" variant="ghost" onClick={onStandalone} aria-label={`Link document for ${row.title}`}>Link document</Button>}
    </TD>
  </TR>
}
