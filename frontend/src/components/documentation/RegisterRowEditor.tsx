import { useState } from 'react'
import axios from 'axios'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, DocumentationSection } from '../../types/documentation'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { Field, inputClass } from '../applications/Fields'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'
import DraftSaveStatus, { type DraftSaveState } from '../ui/DraftSaveStatus'
import { emptyExpectation } from './model'

const fields = ['required_documentation', 'source_reference', 'description', 'document_name'] as const
const labels = { required_documentation: 'Document / record required', source_reference: 'SCP reference', description: 'Comment/explanation', document_name: 'Document', section_id: 'Section' }
const rowValues = (row?: DocumentationExpectation, sectionId?: string) => ({ required_documentation: row?.required_documentation ?? row?.title ?? '', source_reference: row?.source_reference || '', description: row?.description || '', document_name: row?.document_name || '', section_id: row?.section_id || sectionId || '' })

export default function RegisterRowEditor({ row, registerId, projectId, sectionId, sections, onClose, onSaved }: { row?: DocumentationExpectation; registerId: string; projectId?: string; sectionId?: string; sections: DocumentationSection[]; onClose: () => void; onSaved: (row: DocumentationExpectation) => void }) {
  const [draft, setDraft] = useState(rowValues(row, sectionId))
  const [baseline, setBaseline] = useState(draft)
  const [revision, setRevision] = useState(row?.revision || 1)
  const [latest, setLatest] = useState<ReturnType<typeof rowValues> | null>(null)
  const [state, setState] = useState<DraftSaveState>('saved')
  const [error, setError] = useState('')
  const [discard, setDiscard] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)
  useDraftNavigationGuard(dirty || state === 'saving')
  const close = () => { if (state === 'saving') return; if (dirty) setDiscard(true); else onClose() }
  const save = async () => {
    if (state === 'saving' || state === 'conflict') return
    setState('saving'); setError('')
    const body = { ...draft, section_id: draft.section_id || null, title: draft.required_documentation.slice(0, 500) }
    try {
      const saved = row ? await documentationApi.updateExpectation(row.id, revision, body) : await documentationApi.createExpectation(registerId, { ...emptyExpectation(projectId), ...body })
      setBaseline(rowValues(saved)); setDraft(rowValues(saved)); setState('saved'); onSaved(saved)
    } catch (caught) { setState(axios.isAxiosError(caught) && caught.response?.status === 409 ? 'conflict' : 'error'); setError(getApiErrorMessage(caught, 'The row could not be saved. Your changes are preserved.')) }
  }
  return <><Modal open title={row ? 'Edit row' : 'Add row'} size="lg" onClose={close} footer={<><DraftSaveStatus state={dirty && state === 'saved' ? 'dirty' : state} /><Button disabled={state === 'saving'} onClick={close}>Cancel</Button><Button variant="primary" loading={state === 'saving'} disabled={!dirty || !draft.required_documentation.trim() || state === 'conflict'} onClick={() => void save()}>Save row</Button></>}>
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); void save() }}><fieldset disabled={state === 'saving'} className="space-y-4">
      {sections.length > 0 && <Field label="Section"><select className={inputClass} value={draft.section_id} onChange={event => { setDraft(current => ({ ...current, section_id: event.target.value })); if (state !== 'conflict') setState('dirty') }}><option value="">Unsectioned</option>{sections.map(section => <option key={section.id} value={section.id}>{section.name}</option>)}</select></Field>}
      {fields.map(field => <Field key={field} label={labels[field]}><textarea required={field === 'required_documentation'} rows={field === 'required_documentation' ? 5 : field === 'description' ? 3 : 2} className={inputClass} value={draft[field]} onChange={event => { setDraft(current => ({ ...current, [field]: event.target.value })); if (state !== 'conflict') setState('dirty') }} /></Field>)}
    </fieldset></form>
    {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    {state === 'conflict' && row && <div className="mt-4 space-y-3"><Button onClick={async () => { try { const current = (await api.get<DocumentationExpectation>(`/documentation/expectations/${row.id}`)).data; setLatest(rowValues(current)); setRevision(current.revision) } catch (caught) { setError(getApiErrorMessage(caught, 'The current row could not be loaded.')) } }}>Load current row</Button>{latest && <><h3 className="font-semibold">Review concurrent changes</h3>{([...fields, 'section_id'] as const).filter(field => draft[field] !== latest[field]).map(field => <div key={field} className="mt-3 space-y-1 border-t border-line pt-2 text-sm"><strong>{labels[field]}</strong><p className="whitespace-pre-wrap break-words">Current: {field === 'section_id' ? sections.find(section => section.id === latest[field])?.name || 'Unsectioned' : latest[field] || 'Empty'}</p><p className="whitespace-pre-wrap break-words">Your draft: {field === 'section_id' ? sections.find(section => section.id === draft[field])?.name || 'Unsectioned' : draft[field] || 'Empty'}</p></div>)}<div className="flex flex-wrap gap-2"><Button onClick={() => { setBaseline(latest); setLatest(null); setState('dirty'); setError('Your reviewed draft is ready to save.') }}>Keep reviewed draft</Button><Button onClick={() => { setBaseline(latest); setDraft(latest); setLatest(null); setState('saved'); setError('') }}>Use current values</Button></div></>}</div>}
  </Modal><ConfirmDialog open={discard} title="Discard row changes?" description="Your changes have not been saved." confirmLabel="Discard changes" onClose={() => setDiscard(false)} onConfirm={onClose} /></>
}
