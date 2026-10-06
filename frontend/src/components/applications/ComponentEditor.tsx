import { useEffect, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { preparationApi } from '../../api/preparation'
import type { UserMention } from '../../types'
import type { ApplicationComponent, ComponentInput } from '../../types/applications'
import Button from '../ui/Button'
import EvidenceAttachments from '../preparation/EvidenceAttachments'
import NewPackFormEditor from './NewPackFormEditor'
import PrivateSourceUpload from './PrivateSourceUpload'
import { Field, OwnerField, inputClass } from './Fields'

export default function ComponentEditor({ initial, jurisdictionId, users, busy, onSave, onLibrary, onDirtyChange }: {
  initial?: ApplicationComponent; jurisdictionId: string; users: UserMention[]; busy: boolean
  onSave: (body: ComponentInput) => Promise<boolean>; onLibrary: (tab: 'templates' | 'evidence') => void; onDirtyChange?: (dirty: boolean) => void
}) {
  const [dirty, setDirty] = useState(false)
  const [name, setName] = useState(initial?.name || '')
  const [kind, setKind] = useState<ComponentInput['kind']>(initial?.kind || 'annex')
  const [source, setSource] = useState(initial?.case_id ? 'existing' : 'blank')
  const [formSetup, setFormSetup] = useState<{ template_id?: string; form_fields?: ComponentInput['form_fields']; original_evidence_ids: string[] }>({ original_evidence_ids: [] })
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  const [caseId, setCaseId] = useState(initial?.case_id || '')
  const [evidenceIds, setEvidenceIds] = useState(initial?.evidence_id ? [initial.evidence_id] : [])
  const [ownerId, setOwnerId] = useState(initial?.owner_id || '')
  const [dueDate, setDueDate] = useState(initial?.due_date || '')
  const [required, setRequired] = useState(initial?.required ?? true)
  const [included, setIncluded] = useState(initial?.included ?? true)
  const [search, setSearch] = useState('')
  const cases = useQuery({ queryKey: ['preparation', 'cases', 'application-picker', jurisdictionId, search], queryFn: () => preparationApi.cases(new URLSearchParams({ jurisdiction_id: jurisdictionId, status: 'active', limit: '100', q: search })), enabled: source === 'existing' && kind !== 'document' })
  const save = async (event: FormEvent) => {
    event.preventDefault()
    const ok = await onSave({ name: name.trim(), kind, required, included, owner_id: ownerId || null, due_date: dueDate || null, case_id: kind !== 'document' && source === 'existing' ? caseId || null : null, evidence_id: kind === 'document' ? evidenceIds[0] || null : null, ...(kind !== 'document' && source === 'blank' ? { form_fields: formSetup.form_fields, original_evidence_ids: formSetup.original_evidence_ids, ...(formSetup.template_id ? { template_id: formSetup.template_id } : {}) } : {}) })
    if (ok) setDirty(false)
    if (ok && !initial) { setName(''); setCaseId(''); setEvidenceIds([]) }
  }
  return <div className="space-y-5"><form onSubmit={save} onChange={() => setDirty(true)}><fieldset disabled={busy} className="space-y-4">
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label="Form or document name"><input className={inputClass} required maxLength={200} placeholder="Annex A, application form, ownership chart…" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Item type"><select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value as ComponentInput['kind'])}><option value="annex">Annex / supplementary form</option><option value="form">Application form</option><option value="document">Supporting document / information</option></select></Field>
    </div>
    {kind === 'document' ? <><PrivateSourceUpload disabled={busy} onUploaded={(id) => { setEvidenceIds([id]); setDirty(true) }} /><EvidenceAttachments ids={evidenceIds} disabled={busy} onChange={(ids) => { setDirty(true); setEvidenceIds(ids.length > evidenceIds.length ? ids.slice(-1) : ids) }} /><p className="text-xs text-muted">Attach one file, link or note per document. Add a separate item for each additional document.</p><Button size="sm" onClick={() => onLibrary('evidence')}>Open evidence library</Button></> : <>
      <Field label="Form source"><select className={inputClass} value={source} onChange={(e) => setSource(e.target.value)}><option value="blank">Set up a form in this pack</option><option value="placeholder">Keep checklist item for later</option><option value="existing">Link existing form</option></select></Field>
      {initial?.case_id && source === 'blank' && <p className="rounded-lg bg-info-soft p-3 text-sm text-info">This creates a separate form. Answers in the currently linked form are not copied.</p>}
      {source === 'existing' && <>
        <Field label="Search existing forms"><input type="search" className={inputClass} value={search} onChange={(e) => setSearch(e.target.value)} /></Field>
        <Field label="Existing preparation form"><select required className={inputClass} value={caseId} onChange={(e) => setCaseId(e.target.value)}><option value="">Select form in this jurisdiction</option>{caseId && !cases.data?.items.some((c) => c.id === caseId) && <option value={caseId}>{initial?.case_name || 'Currently linked form'}</option>}{cases.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        {cases.isLoading && <p role="status">Loading forms…</p>}{cases.isError && <p role="alert">Forms could not be loaded. <button type="button" className="underline" onClick={() => void cases.refetch()}>Retry</button></p>}
        {(cases.data?.total || 0) > 100 && <p className="text-xs text-muted">Showing the first 100 matches. Narrow the search to find another form.</p>}
      </>}
    </>}
    {kind !== 'document' && source === 'blank' && <NewPackFormEditor jurisdictionId={jurisdictionId} disabled={busy} onDirtyChange={(value) => { if (value) setDirty(true) }} onChange={(value) => { setFormSetup(value); setDirty(true) }} />}
    <details className="border-t border-line pt-4" open={Boolean(initial && (initial.owner_id || initial.due_date || !initial.required || !initial.included)) || undefined}>
      <summary className="cursor-pointer text-sm font-semibold">Owner, deadline and pack options</summary>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <OwnerField users={users} value={ownerId} onChange={setOwnerId} />
        <Field label="Due date"><input type="date" className={inputClass} value={dueDate} onChange={(e) => setDueDate(e.target.value)} /></Field>
      </div>
      <div className="mt-3 flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />Required for this application</label><label className="flex items-center gap-2"><input type="checkbox" checked={included} onChange={(e) => setIncluded(e.target.checked)} />Include in submission pack</label></div>
    </details>
    <Button type="submit" variant="primary" disabled={!name.trim() || (kind !== 'document' && source === 'blank' && Boolean(formSetup.form_fields?.some((field) => !field.label.trim())))}>{initial ? 'Save form or document' : 'Add form or document'}</Button>
  </fieldset></form>
  </div>
}
