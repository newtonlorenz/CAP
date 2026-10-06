import { visibilityLabels, visibilityDescriptions, type Visibility } from '../../types/access'
import { useEffect, useState, type FormEvent } from 'react'
import type { Jurisdiction, UserMention } from '../../types'
import { scopeLabels, type ApplicationMetadata } from '../../types/applications'
import Button from '../ui/Button'
import { Field, OwnerField, inputClass } from './Fields'

export default function ApplicationMetadataForm({ initial, jurisdictions, users, busy, onSave, onDirtyChange, creating = false, jurisdictionId }: {
  initial?: ApplicationMetadata; jurisdictions: Jurisdiction[]; users: UserMention[]; busy: boolean
  onSave: (body: ApplicationMetadata) => Promise<boolean>; creating?: boolean; jurisdictionId?: string | null; onDirtyChange?: (dirty: boolean) => void
}) {
  const [draft, setDraft] = useState<ApplicationMetadata>(initial ? { name: initial.name, scope: initial.scope, jurisdiction_id: initial.jurisdiction_id, applicant: initial.applicant, authority: initial.authority, description: initial.description, owner_id: initial.owner_id, due_date: initial.due_date } : { visibility: 'secret', name: '', scope: 'annex_only', jurisdiction_id: jurisdictionId || '', applicant: '', authority: '', description: '', owner_id: null, due_date: null })
  const [dirty, setDirty] = useState(false)
  useEffect(() => { onDirtyChange?.(dirty) }, [dirty, onDirtyChange])
  const set = <K extends keyof ApplicationMetadata>(key: K, value: ApplicationMetadata[K]) => { setDirty(true); setDraft((old) => ({ ...old, [key]: value })) }
  const effectiveJurisdictionId = creating ? jurisdictionId || '' : draft.jurisdiction_id
  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (await onSave({ ...draft, jurisdiction_id: effectiveJurisdictionId, name: draft.name.trim(), applicant: draft.applicant?.trim() || null, authority: draft.authority?.trim() || null, description: draft.description?.trim() || null })) setDirty(false)
  }
  return <form onSubmit={save}><fieldset disabled={busy} className="space-y-4">
    <div className="grid gap-4 sm:grid-cols-2">
      {creating && <Field label="Visibility"><select aria-label="Visibility" aria-describedby="application-visibility-help" className={inputClass} value={draft.visibility} onChange={(e) => set('visibility', e.target.value as Visibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><p id="application-visibility-help" className="mt-1 text-xs text-muted">{visibilityDescriptions[draft.visibility || 'secret']} {draft.visibility !== 'organisation' && 'Choose recipients in “Who can access this?” after creating the application.'}</p></Field>}
      <Field label="Application name"><input required maxLength={200} className={inputClass} value={draft.name} onChange={(e) => set('name', e.target.value)} placeholder="For example, Denmark Annex A and B" /></Field>
      <Field label="Application scope"><select className={inputClass} value={draft.scope} onChange={(e) => set('scope', e.target.value as ApplicationMetadata['scope'])}>{Object.entries(scopeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <div><p className="text-sm font-medium">Jurisdiction</p><p className="mt-1 text-sm">{jurisdictions.find((j) => j.id === effectiveJurisdictionId)?.name || 'Select a space to continue'}</p>{creating && <p className="mt-1 text-xs text-muted">Defined by your current space.</p>}</div>
      <Field label="Applicant"><input className={inputClass} maxLength={255} value={draft.applicant || ''} onChange={(e) => set('applicant', e.target.value)} /></Field>
      <Field label="Authority"><input className={inputClass} maxLength={255} value={draft.authority || ''} onChange={(e) => set('authority', e.target.value)} /></Field>
      <OwnerField users={users} value={draft.owner_id || ''} onChange={(id) => set('owner_id', id || null)} />
      <Field label="Deadline"><input type="date" className={inputClass} value={draft.due_date || ''} onChange={(e) => set('due_date', e.target.value || null)} /></Field>
    </div>
    <Field label="Scope and accompanying information"><textarea className={inputClass} rows={3} value={draft.description || ''} onChange={(e) => set('description', e.target.value)} /></Field>
    <p className="text-sm text-muted">Choose the forms and documents you need. Any scope can contain standalone annexes, a licence form, supporting information, or a combination.</p>
    <Button type="submit" variant="primary" disabled={!draft.name.trim() || !effectiveJurisdictionId || (!creating && !dirty)} >{creating ? draft.visibility === 'organisation' ? 'Create application' : 'Create application and choose access' : 'Save application details'}</Button>
    {dirty && <span className="ml-3 text-xs text-warning">Unsaved details</span>}
  </fieldset></form>
}
