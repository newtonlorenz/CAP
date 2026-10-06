import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import type { UserMention } from '../../types'
import type { ApplicationFollowup } from '../../types/applications'
import { formatDate } from '../../utils/dateFormat'
import Button from '../ui/Button'
import DraftSaveStatus from '../ui/DraftSaveStatus'
import EvidenceAttachments from '../preparation/EvidenceAttachments'
import { Field, OwnerField, inputClass } from './Fields'

export function NewFollowup({ users, busy, onSave, onDirtyChange }: { users: UserMention[]; busy: boolean; onDirtyChange: (dirty: boolean) => void; onSave: (body: { question: string; owner_id: string | null; due_date: string | null }) => Promise<boolean> }) {
  const [dirty, setDirty] = useState(false)
  useEffect(() => { onDirtyChange(dirty) }, [dirty, onDirtyChange])
  const [question, setQuestion] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [dueDate, setDueDate] = useState('')
  const save = async (event: FormEvent) => { event.preventDefault(); if (await onSave({ question: question.trim(), owner_id: ownerId || null, due_date: dueDate || null })) { setQuestion(''); setOwnerId(''); setDueDate(''); setDirty(false) } }
  return <form onSubmit={save} onChange={() => setDirty(true)}><fieldset disabled={busy} className="space-y-4">
    <Field label="Authority query"><textarea className={inputClass} required rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} /></Field>
    <div className="grid gap-4 sm:grid-cols-2"><OwnerField users={users} value={ownerId} onChange={setOwnerId} /><Field label="Response deadline"><input type="date" className={inputClass} value={dueDate} onChange={(e) => setDueDate(e.target.value)} /></Field></div>
    <Button type="submit" disabled={!question.trim()} >Add authority query</Button>
  </fieldset></form>
}
type ResponseDraft = { response: string; evidence_ids: string[] }
const responseDraft = (item: ApplicationFollowup): ResponseDraft => ({ response: item.response || '', evidence_ids: item.evidence_ids })
const responsePayload = (draft: ResponseDraft): ResponseDraft => ({ response: draft.response.trim(), evidence_ids: [...draft.evidence_ids].sort() })
const responseSnapshot = (draft: ResponseDraft) => JSON.stringify(responsePayload(draft))

export function Followup({ item, users, canEdit, canManage, busy, onSave, onDirtyChange }: { item: ApplicationFollowup; users: UserMention[]; canEdit: boolean; canManage: boolean; busy: boolean; onDirtyChange: (dirty: boolean) => void; onSave: (body: Partial<ApplicationFollowup>) => Promise<boolean> }) {
  const [draft, setDraft] = useState(() => responseDraft(item))
  const current = useRef(draft)
  const [acknowledged, setAcknowledged] = useState(() => responseSnapshot(draft))
  const acknowledgedRef = useRef(acknowledged)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [saveError, setSaveError] = useState('')
  const failed = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const active = useRef(true)
  const latest = useRef({ canEdit, busy, onSave })
  latest.current = { canEdit, busy, onSave }
  const responseDirty = Boolean(saveError) || responseSnapshot(draft) !== acknowledged
  const [metadataDirty, setMetadataDirty] = useState(false)
  const [question, setQuestion] = useState(item.question)
  const [ownerId, setOwnerId] = useState(item.owner_id || '')
  const [dueDate, setDueDate] = useState(item.due_date || '')
  const [detailsSaving, setDetailsSaving] = useState(false)
  const operationPending = useRef(false)
  const serverSnapshot = responseSnapshot(responseDraft(item))
  const hasDrafts = responseDirty || saving || metadataDirty || detailsSaving

  useEffect(() => { onDirtyChange(hasDrafts) }, [hasDrafts, onDirtyChange])
  useEffect(() => {
    active.current = true
    return () => { active.current = false; clearTimeout(timer.current) }
  }, [])
  useEffect(() => {
    if (savingRef.current || failed.current || responseSnapshot(current.current) !== acknowledgedRef.current) return
    current.current = JSON.parse(serverSnapshot) as ResponseDraft
    acknowledgedRef.current = serverSnapshot
    setDraft(current.current)
    setAcknowledged(serverSnapshot)
  }, [serverSnapshot])
  useEffect(() => {
    if (metadataDirty || detailsSaving) return
    setQuestion(item.question)
    setOwnerId(item.owner_id || '')
    setDueDate(item.due_date || '')
  }, [item.question, item.owner_id, item.due_date, metadataDirty, detailsSaving])

  const changeResponse = (patch: Partial<ResponseDraft>) => {
    current.current = { ...current.current, ...patch }
    setDraft(current.current)
  }
  const saveResponse = useCallback(async (retry = false) => {
    clearTimeout(timer.current)
    const context = latest.current
    if (!active.current || !context.canEdit || context.busy || operationPending.current || savingRef.current || (failed.current && !retry)) return
    const captured = responsePayload(current.current)
    const snapshot = responseSnapshot(captured)
    if (!failed.current && snapshot === acknowledgedRef.current) return
    savingRef.current = true
    setSaving(true)
    try {
      const saved = await context.onSave(captured)
      if (!active.current) return
      if (saved) {
        acknowledgedRef.current = snapshot
        setAcknowledged(snapshot)
        failed.current = false
        setSaveError('')
      } else {
        failed.current = true
        setSaveError('Your response draft is still here. Resolve any application error, then retry saving.')
      }
    } catch {
      if (!active.current) return
      failed.current = true
      setSaveError('Your response draft is still here. Retry saving when you are ready.')
    } finally {
      savingRef.current = false
      if (active.current) setSaving(false)
    }
  }, [])
  useEffect(() => {
    if (canEdit && responseDirty && !busy && !saving && !detailsSaving && !saveError)
      timer.current = setTimeout(() => { void saveResponse() }, 800)
    return () => clearTimeout(timer.current)
  }, [canEdit, responseDirty, busy, saving, detailsSaving, saveError, draft, saveResponse])

  const saveDetails = async (status?: 'open' | 'resolved') => {
    if (!canManage || busy || operationPending.current || savingRef.current || responseDirty || (status && metadataDirty)) return
    operationPending.current = true
    setDetailsSaving(true)
    try {
      const saved = await onSave(status ? { status } : { question: question.trim(), owner_id: ownerId || null, due_date: dueDate || null })
      if (saved && active.current && !status) setMetadataDirty(false)
    } finally {
      operationPending.current = false
      if (active.current) setDetailsSaving(false)
    }
  }
  const responseState = saving ? 'saving' : saveError ? 'error' : responseDirty ? 'dirty' : 'saved'
  return <article className="space-y-4 rounded-xl border border-line p-4">
    <div><h4 className="font-semibold whitespace-pre-wrap">{item.question}</h4><p className="mt-1 text-sm text-muted">{item.status === 'resolved' ? 'Resolved' : 'Open'} · {users.find((u) => u.id === item.owner_id)?.full_name || 'Unassigned'} · Due {formatDate(item.due_date)}</p></div>
    {canManage && <details><summary className="cursor-pointer text-sm text-accent">Edit query and assignment</summary><fieldset disabled={busy || saving || detailsSaving} className="mt-3 space-y-3">
      <Field label="Query text"><textarea className={inputClass} value={question} onChange={(e) => { setQuestion(e.target.value); setMetadataDirty(true) }} /></Field>
      <OwnerField users={users} value={ownerId} onChange={(value) => { setOwnerId(value); setMetadataDirty(true) }} />
      <Field label="Query deadline"><input type="date" className={inputClass} value={dueDate} onChange={(e) => { setDueDate(e.target.value); setMetadataDirty(true) }} /></Field>
      <div className="flex flex-wrap items-center gap-2"><Button disabled={!metadataDirty || !question.trim() || responseDirty} onClick={() => void saveDetails()}>Save query details</Button>{metadataDirty && <span className="text-xs text-warning">Unsaved query details</span>}</div>
    </fieldset></details>}
    <div onBlur={() => { void saveResponse() }} className="space-y-3">
      {canEdit ? <><Field label="Response"><textarea rows={3} className={inputClass} value={draft.response} onChange={(e) => changeResponse({ response: e.target.value })} /></Field><p className="text-xs text-muted">Response drafts save automatically. Resolving the query is a separate action.</p></> : <p className="whitespace-pre-wrap text-sm">{item.response || 'No response recorded.'}</p>}
      <EvidenceAttachments ids={canEdit ? draft.evidence_ids : item.evidence_ids} onChange={canEdit ? (evidence_ids) => changeResponse({ evidence_ids }) : undefined} />
    </div>
    {canEdit && <div className="flex flex-wrap items-center gap-2"><DraftSaveStatus state={responseState} message={saveError || undefined} onRetry={!busy ? () => { void saveResponse(true) } : undefined} />{canManage && <Button disabled={busy || hasDrafts || (item.status === 'open' && !draft.response.trim() && draft.evidence_ids.length === 0)} onClick={() => void saveDetails(item.status === 'resolved' ? 'open' : 'resolved')}>{item.status === 'resolved' ? 'Reopen query' : 'Resolve query'}</Button>}</div>}
  </article>
}
