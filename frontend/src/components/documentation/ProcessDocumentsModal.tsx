import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../../api/client'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, ProcessTarget } from '../../types/documentation'
import type { PreparationCase } from '../../types/preparation'
import { useAuth } from '../../contexts/AuthContext'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { useCaseWrites } from '../../hooks/preparation/useCaseWrites'
import EvidenceAttachments from '../preparation/EvidenceAttachments'
import ContextualEvidenceUpload from '../preparation/ContextualEvidenceUpload'
import { SharedEvidenceDialog } from '../review/ReviewSharedEvidence'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'
import LoadError from '../ui/LoadError'
import { processTargetHref, targetKey } from './processNavigation'

const EMPTY_IDS: string[] = []

export default function ProcessDocumentsModal({ rowId, target, returnTo, onClose }: { rowId: string; target: ProcessTarget; returnTo: string; onClose: () => void }) {
  const [sharedOpen, setSharedOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [error, setError] = useState('')
  const row = useQuery({ queryKey: ['documentation', 'process-documents', rowId], queryFn: async () => (await api.get<DocumentationExpectation>(`/documentation/expectations/${rowId}`)).data })
  const current = row.data?.process_targets?.find(value => value.available && targetKey(value) === targetKey(target))
  const href = current ? processTargetHref(current, returnTo) : null
  const applicationHref = current?.kind === 'application_response' && href ? (() => { const value = new URL(href, 'https://cap.invalid'); ['case', 'field', 'evidence'].forEach(key => value.searchParams.delete(key)); return `${value.pathname}${value.search}` })() : null
  const close = () => { if (pending) setDiscard(true); else onClose() }
  return <><Modal open title="Process documents" size="lg" onClose={close} footer={<Button onClick={close}>Close documents</Button>}><div className="space-y-4">
    {row.isLoading && <p role="status">Loading the current evidence collection…</p>}{row.isError && <LoadError subject="Process documents" onRetry={() => void row.refetch()} />}
    {row.isSuccess && !current && <p role="alert" className="text-sm text-muted">This target is no longer available in the linked process. Return to the register to review its mapping.</p>}
    {current && <><div><h3 className="font-semibold">{current.reference_id} · {current.title}</h3><p className="mt-1 text-sm text-muted">These documents belong to the {current.kind === 'review_item' ? 'assessment requirement' : 'licence form question'}. Changes appear in both views.</p>{href && <Link className="mt-2 inline-block text-sm text-accent underline" to={href}>Open evidence collection</Link>}</div>
      {current.collection?.warning && <p role="alert" className="text-sm text-muted">{current.collection.warning}</p>}
      {current.kind === 'review_item' ? <><ul className="space-y-3">{current.collection?.items.map((item, index) => <li key={item.evidence_id || item.file_id || index} className="space-y-1 border-t border-line pt-3 text-sm"><strong className="break-words">{item.title}</strong>{item.locator && <p>{item.locator}</p>}{item.rationale && <p className="whitespace-pre-wrap">{item.rationale}</p>}{item.body && <p className="whitespace-pre-wrap break-words">{item.body}</p>}{item.link_url && /^https?:\/\//i.test(item.link_url) && <a className="text-accent underline" href={item.link_url} target="_blank" rel="noreferrer">Open process evidence link</a>}{item.problems?.length ? <p className="text-muted">{item.problems.join(', ')}</p> : null}{item.download_href && <button type="button" className="text-accent underline" onClick={async () => { try { const result = await api.get<Blob>(item.download_href!, { responseType: 'blob' }); const url = URL.createObjectURL(result.data); const anchor = document.createElement('a'); anchor.href = url; anchor.download = item.filename || item.title; document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) } catch (caught) { setError(getApiErrorMessage(caught, 'The process document could not be downloaded.')) } }}>Download document</button>}</li>)}</ul>{current.collection?.has_review_notes && <div className="space-y-1 text-sm"><strong>Assessment notes</strong><p className="whitespace-pre-wrap break-words text-muted">{current.collection.review_notes_summary || 'Notes are recorded in the evidence collection.'}</p></div>}{!current.collection?.items.length && !current.collection?.has_review_notes && !current.collection?.warning && <p className="text-sm text-muted">No documents are attached to this assessment requirement.</p>}{current.collection?.can_edit && !current.collection.readonly ? <Button onClick={() => setSharedOpen(true)}>Link library evidence</Button> : <p className="text-sm text-muted">This collection is read-only. Editing requires access to the process and an active assessment.</p>}{sharedOpen && current.review_cycle_id && current.review_item_id && <SharedEvidenceDialog cycleId={current.review_cycle_id} itemId={current.review_item_id} onClose={() => setSharedOpen(false)} />}</> : current.case_id && current.field_key ? <div className="space-y-3">{current.collection?.application_status !== 'draft' && applicationHref && <Link className="text-sm text-accent underline" to={applicationHref}>Open licence application</Link>}<ApplicationProcessDocuments target={current} onPending={setPending} onRefreshMapping={() => void row.refetch()} /></div> : null}
    </>}{error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </div></Modal><ConfirmDialog open={discard} title="Leave document changes?" description="Unsaved document selections will be discarded. An upload already completed remains in the evidence library." confirmLabel="Leave changes" onClose={() => setDiscard(false)} onConfirm={onClose} /></>
}

function ApplicationProcessDocuments({ target, onPending, onRefreshMapping }: { target: ProcessTarget; onPending: (pending: boolean) => void; onRefreshMapping: () => void }) {
  const form = useQuery({ queryKey: ['preparation', 'case', target.case_id], queryFn: () => preparationApi.getCase(target.case_id!), refetchOnWindowFocus: false })
  return form.isLoading ? <p role="status">Loading form evidence…</p> : form.isError ? <LoadError subject="Form evidence" onRetry={() => void form.refetch()} /> : form.data ? <FormDocuments key={`${target.case_id}:${target.field_key}`} item={form.data} target={target} onPending={onPending} onRefreshMapping={() => { onRefreshMapping(); void form.refetch() }} /> : null
}

function FormDocuments({ item, target, onPending, onRefreshMapping }: { item: PreparationCase; target: ProcessTarget; onPending: (pending: boolean) => void; onRefreshMapping: () => void }) {
  const { user } = useAuth()
  const response = item.responses.find(value => value.field_key === target.field_key)
  const initialIds = useMemo(() => response?.evidence_ids || EMPTY_IDS, [response?.evidence_ids])
  const fieldSource = item.fields.find(field => field.key === target.field_key)?.source
  const sourceMatches = Boolean(target.requirement_id && target.requirement_set_version_id && fieldSource?.requirement_id === target.requirement_id && fieldSource?.requirement_set_version_id === target.requirement_set_version_id)
  const [ids, setIds] = useState(initialIds)
  const [baseline, setBaseline] = useState(initialIds)
  const [uploadPending, setUploadPending] = useState(false)
  const [message, setMessage] = useState('')
  const dirty = JSON.stringify(ids) !== JSON.stringify(baseline)
  const writes = useCaseWrites(item.id, item.revision, dirty)
  const { setFieldDirty } = writes
  const editable = Boolean(sourceMatches && target.collection?.can_edit && !target.collection.readonly && target.collection.application_status === 'draft' && item.status !== 'archived' && item.access?.permissions.includes('edit') && ['admin', 'manager', 'contributor'].includes(user?.role || ''))
  useDraftNavigationGuard(dirty || writes.isWriting || uploadPending)
  useEffect(() => { if (!dirty && !writes.isWriting && !uploadPending && JSON.stringify(baseline) !== JSON.stringify(initialIds)) { setIds(initialIds); setBaseline(initialIds) } }, [dirty, writes.isWriting, uploadPending, baseline, initialIds])
  useEffect(() => { setFieldDirty('register-documents', dirty); return () => setFieldDirty('register-documents', false) }, [dirty, setFieldDirty])
  useEffect(() => { onPending(dirty || writes.isWriting || uploadPending); return () => onPending(false) }, [dirty, writes.isWriting, uploadPending, onPending])
  const save = async (next = ids) => {
    if (!editable) return false
    setMessage('')
    const saved = await writes.saveField(target.field_key!, { value: response?.value ?? null, not_applicable_reason: response?.not_applicable_reason ?? null, evidence_ids: next })
    if (!saved) return false
    const attached = saved.responses.find(value => value.field_key === target.field_key)?.evidence_ids || []
    setIds(attached); setBaseline(attached); writes.setFieldDirty('register-documents', false)
    setMessage('Documents saved to the existing form question. Review acceptance is separate.')
    return true
  }
  if (!sourceMatches) return <div className="space-y-3"><p role="alert" className="text-sm text-muted">This form question now refers to a different requirement version or is unavailable. Refresh the register mapping before changing documents.</p><Button onClick={onRefreshMapping}>Refresh process mapping</Button></div>
  return <div className="space-y-4"><EvidenceAttachments ids={ids} onChange={editable && !writes.conflicted ? setIds : undefined} disabled={!editable || writes.isWriting || writes.conflicted || uploadPending} />{editable && <ContextualEvidenceUpload caseId={item.id} ids={ids} disabled={writes.isWriting || writes.conflicted} attach={save} onBusyChange={setUploadPending} />}{writes.error && <p role="alert" className="text-sm text-danger">{writes.error}</p>}{writes.conflicted && <div className="space-y-3"><p className="whitespace-pre-wrap text-sm">Current answer: {String(response?.value ?? 'Empty')}{response?.not_applicable_reason ? ` · Not applicable: ${response.not_applicable_reason}` : ''}</p><p className="text-sm">Current documents: {response?.evidence_ids.length || 0}. Compare them with your selected documents before continuing.</p><EvidenceAttachments ids={response?.evidence_ids || []} /><Button disabled={!writes.conflictReady} onClick={() => { if (writes.resumeWrites()) setMessage('Your reviewed document selection is ready to save. The current answer and applicability reason will be preserved.') }}>Keep reviewed document selections</Button></div>}{writes.pauseReason === 'error' && <Button onClick={() => writes.resumeWrites()}>Retry document save</Button>}{editable ? <Button variant="primary" disabled={!dirty || writes.isWriting || writes.conflicted || uploadPending} onClick={() => void save()}>Save documents</Button> : <p className="text-sm text-muted">{target.collection?.application_status && target.collection.application_status !== 'draft' ? 'Return the application to draft to change this collection.' : 'This collection is read-only. Editing requires permission to the included form.'}</p>}{message && <p role="status" className="text-sm">{message}</p>}</div>
}
