import { useState } from 'react'
import type { SubmissionChecklist } from '../types'
import Button from './ui/Button'

export default function SubmissionChecklistEditor({ checklist, readOnly, saving, onSave }: {
  checklist: SubmissionChecklist
  readOnly: boolean
  saving: boolean
  onSave: (checklist: SubmissionChecklist) => Promise<unknown>
}) {
  const [draft, setDraft] = useState(checklist)
  const [dirty, setDirty] = useState(false)
  return <div className="space-y-3 rounded-lg border border-line p-4">
    <h3 className="font-semibold">Package checklist</h3>
    <p className="text-sm text-muted">Confirm each item after checking the supporting work. The server also checks the linked review, snapshot and required artifacts.</p>
    {draft.sections.map((section, sectionIndex) => <fieldset key={section.id} disabled={readOnly || saving} className="space-y-2">
      <legend className="mb-2 text-sm font-medium text-muted">{section.title}</legend>
      {section.items.map((item, itemIndex) => <label key={item.id} className="flex min-h-10 items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1" checked={item.completed} onChange={(event) => {
          setDraft((current) => ({ ...current, sections: current.sections.map((entry, i) => i !== sectionIndex ? entry : { ...entry, items: entry.items.map((row, j) => j !== itemIndex ? row : { ...row, completed: event.target.checked }) }) }))
          setDirty(true)
        }} />
        <span>{item.label}{!item.required && <span className="text-muted"> (optional)</span>}{item.guidance && <span className="mt-1 block text-xs text-muted">{item.guidance}</span>}</span>
      </label>)}
    </fieldset>)}
    {readOnly ? <p className="text-xs text-muted">This checklist is read-only. Changes must be made in a draft package.</p> : <Button loading={saving} disabled={!dirty} onClick={async () => { try { await onSave(draft); setDirty(false) } catch { /* The mutation displays an error and retains this draft. */ } }}>Save checklist</Button>}
  </div>
}
