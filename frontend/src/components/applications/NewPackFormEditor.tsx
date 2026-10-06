import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { preparationApi } from '../../api/preparation'
import type { PreparationField, PreparationKind } from '../../types/preparation'
import { nextPreparationFieldKey, PREPARATION_FIELD_TYPES } from '../../types/preparation'
import Button from '../ui/Button'
import EvidenceAttachments from '../preparation/EvidenceAttachments'
import QuestionImport from '../preparation/QuestionImport'
import RequirementsImport from '../preparation/RequirementsImport'
import { Field, inputClass } from './Fields'
import PrivateSourceUpload from './PrivateSourceUpload'

export default function NewPackFormEditor({ jurisdictionId, disabled, onChange, onDirtyChange, kindScope = 'licence_application' }: {
  jurisdictionId: string; disabled: boolean; kindScope?: PreparationKind
  onDirtyChange?: (dirty: boolean) => void
  onChange: (value: { template_id?: string; form_fields?: PreparationField[]; original_evidence_ids: string[] }) => void
}) {
  const [source, setSource] = useState<'blank' | 'template'>('blank')
  const [fields, setFields] = useState<PreparationField[]>([])
  const [templateId, setTemplateId] = useState('')
  const [originals, setOriginals] = useState<string[]>([])
  const [pending, setPending] = useState<PreparationField[]>([])
  const templates = useQuery({ queryKey: ['preparation', 'templates'], queryFn: preparationApi.templates, enabled: source === 'template' })
  const notify = (nextFields: PreparationField[], nextOriginals = originals, nextTemplate = templateId, nextSource = source) => onChange({ ...(nextSource === 'template' ? { template_id: nextTemplate || undefined } : { form_fields: nextFields }), original_evidence_ids: nextOriginals })
  const updateFields = (next: PreparationField[]) => { setFields(next); notify(next) }
  const append = () => { const next = [...fields, { key: nextPreparationFieldKey(fields), section: 'General', label: '', type: 'text' as const, required: true, options: [], help_text: null, reuse_key: null }]; updateFields(next) }
  const reviewImport = (incoming: PreparationField[]) => { setPending(incoming); onDirtyChange?.(true) }
  const changeSource = (next: 'blank' | 'template') => { setSource(next); notify(fields, originals, templateId, next) }
  return <fieldset disabled={disabled} className="min-w-0 space-y-4 border-t border-line pt-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold">Questions</h4><Button size="sm" variant="ghost" onClick={() => changeSource(source === 'blank' ? 'template' : 'blank')}>{source === 'blank' ? 'Use a saved blank form' : 'Write or import questions instead'}</Button></div>
    {source === 'template' ? <><Field label="Saved blank form"><select className={inputClass} value={templateId} onChange={(event) => { setTemplateId(event.target.value); notify(fields, originals, event.target.value, 'template') }}><option value="">Select a saved blank form</option>{templates.data?.items.filter((item) => item.active && item.kind === kindScope).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>{templates.isError && <p role="alert">Saved blank forms could not be loaded. <button type="button" onClick={() => void templates.refetch()} className="underline">Retry</button></p>}</> : <>
      <p className="text-sm text-muted">Enter questions in source order, or import a reviewed list.</p>
      {fields.map((field, index) => <div key={field.key} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2"><Field label={`Question ${index + 1}`}><input className={inputClass} value={field.label} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, label: event.target.value } : current))} /></Field><Field label="Answer type"><select className={inputClass} value={field.type} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, type: event.target.value as PreparationField['type'], options: [] } : current))}>{PREPARATION_FIELD_TYPES.map((type) => <option key={type} value={type}>{type.replace('_', ' ')}</option>)}</select></Field><Field label="Section"><input className={inputClass} value={field.section} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, section: event.target.value } : current))} /></Field><Field label="Help text"><input className={inputClass} value={field.help_text || ''} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, help_text: event.target.value || null } : current))} /></Field>{field.type === 'choice' && <Field label="Choices, one per line"><textarea className={inputClass} value={field.options.join('\n')} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, options: event.target.value.split('\n').map((part) => part.trim()).filter(Boolean) } : current))} /></Field>}<label className="text-sm"><input type="checkbox" checked={field.required} onChange={(event) => updateFields(fields.map((current, i) => i === index ? { ...current, required: event.target.checked } : current))} /> Required</label><Button size="sm" onClick={() => updateFields(fields.filter((_, i) => i !== index))}>Remove question</Button></div>)}
      <Button size="sm" onClick={append}>Add question</Button>
      <QuestionImport existing={fields} disabled={disabled} onDirtyChange={onDirtyChange} onImport={reviewImport} />
      <RequirementsImport existing={fields} jurisdictionId={jurisdictionId} disabled={disabled} onDirtyChange={onDirtyChange} onImport={reviewImport} />
      {pending.length > 0 && <div className="rounded-lg border border-warning p-4"><p className="font-semibold">Review {pending.length} imported questions</p><ol className="mt-2 list-decimal pl-5 text-sm">{pending.map((field) => <li key={field.key}>{field.label} · {field.type}</li>)}</ol><div className="mt-3 flex gap-2"><Button size="sm" onClick={() => { updateFields([...fields, ...pending]); setPending([]) }}>Confirm and add questions</Button><Button size="sm" onClick={() => setPending([])}>Discard import</Button></div></div>}
    </>}
    <details open={originals.length > 0 || undefined} className="border-t border-line pt-4"><summary className="cursor-pointer text-sm font-semibold">Original form or source files <span className="text-xs font-normal text-muted">{originals.length ? `(${originals.length} attached)` : '(optional)'}</span></summary><div className="mt-3"><p className="mb-2 text-xs text-muted">Attach the original files used to set up this form.</p><PrivateSourceUpload disabled={disabled} onUploaded={(id) => { const next = [...originals, id]; setOriginals(next); notify(fields, next) }} /><EvidenceAttachments ids={originals} onChange={(ids) => { setOriginals(ids); notify(fields, ids) }} disabled={disabled} /></div></details>
  </fieldset>
}
