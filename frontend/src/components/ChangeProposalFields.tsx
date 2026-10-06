import type { ChangeEvent, Dispatch, FormEvent, SetStateAction } from 'react'
import type { ManagedComponent } from '../types'
import type { ChangeCompliance } from '../types/changeManagement'
import ChangeComplianceFields from './workflows/ChangeComplianceFields'
type ChangeType = 'standard' | 'normal' | 'emergency'
type TestingCycle = 'immediate' | 'quarterly' | 'annual'

export type ChangeDraft = {
  title: string
  description: string
  category: string
  change_type: ChangeType
  complexity_classification: string
  resource_assessment: string
  scheduling_assessment: string
  affected_components_summary: string
  affected_docs_summary: string
  planned_start_at: string
  planned_end_at: string
  justification: string
  affected_documentation: string
  evaluation_effect: string
  evaluation_risk: string
  evaluation_regulatory_impact: string
  evaluation_ciaa_impact: string
  testing_org_required: boolean
  testing_org_status: string
  testing_org_cycle: TestingCycle
  testing_org_next_due_at: string
  testing_org_approved_at: string
  integration_related: boolean
  component_ids: string[]
  planned_versions: Record<string, string>
  planned_checksum_hashes: Record<string, string>
  baseline_scope_assessments: Record<string, string>
  compliance: ChangeCompliance
}

type DraftTextField = 'title' | 'description' | 'category' | 'complexity_classification'
  | 'resource_assessment' | 'scheduling_assessment' | 'justification'
  | 'evaluation_effect' | 'evaluation_risk' | 'evaluation_regulatory_impact' | 'evaluation_ciaa_impact'
  | 'affected_components_summary' | 'affected_docs_summary' | 'affected_documentation'

const labelClass = 'flex min-w-0 flex-col gap-1 text-xs font-medium text-muted'
const inputClass = 'w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm'
const detailsClass = 'min-w-0 border-t border-line pt-3 md:col-span-2'
const summaryClass = 'cursor-pointer text-sm font-semibold text-ink'

function revealInvalidField(event: FormEvent<HTMLElement>) {
  if (event.target instanceof HTMLElement) event.target.closest('details')?.setAttribute('open', '')
}

function TextField({ label, field, draft, setDraft, multiline = false, required = false, autoFocus = false, maxLength }: {
  label: string
  field: DraftTextField
  draft: ChangeDraft
  setDraft: Dispatch<SetStateAction<ChangeDraft>>
  multiline?: boolean
  required?: boolean
  autoFocus?: boolean
  maxLength?: number
}) {
  const props = {
    'aria-label': label,
    value: draft[field],
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft(previous => ({ ...previous, [field]: event.target.value })),
    placeholder: label,
    className: inputClass,
    required,
    autoFocus,
    'data-autofocus': autoFocus || undefined,
    maxLength,
  }
  return <label className={`${labelClass}${multiline ? ' md:col-span-2' : ''}`}>
    <span>{label}{required ? ' *' : ''}</span>
    {multiline ? <textarea {...props} rows={3} /> : <input {...props} />}
  </label>
}

export default function ChangeProposalFields({ draft, setDraft, components, autoFocus = false, proposalReadOnly = false, danish = false }: {
  autoFocus?: boolean
  proposalReadOnly?: boolean
  danish?: boolean
  draft: ChangeDraft
  setDraft: Dispatch<SetStateAction<ChangeDraft>>
  components: ManagedComponent[]
}) {
  const selectedComponents = components.filter(component => draft.component_ids.includes(component.id))
  const planningCount = [draft.complexity_classification, draft.resource_assessment, draft.scheduling_assessment,
    draft.planned_start_at, draft.planned_end_at, draft.justification].filter(value => value.trim()).length
  const evaluationCount = [draft.evaluation_effect, draft.evaluation_risk,
    draft.evaluation_regulatory_impact, draft.evaluation_ciaa_impact].filter(value => value.trim()).length
  const testingStatus = draft.testing_org_status
    ? draft.testing_org_status.replace(/_/g, ' ')
    : 'status not recorded'

  return <>
    <fieldset disabled={proposalReadOnly} onInvalidCapture={revealInvalidField} className="grid min-w-0 grid-cols-1 gap-3 md:col-span-2 md:grid-cols-2">
      <TextField label="Change title" field="title" draft={draft} setDraft={setDraft} required maxLength={255} autoFocus={autoFocus && !proposalReadOnly} />
      <label className={labelClass}>
        <span>Change type</span>
        <select aria-label="Change type" value={draft.change_type}
          onChange={event => setDraft(previous => ({ ...previous, change_type: event.target.value as ChangeType }))}
          className={inputClass}>
          <option value="standard">Standard</option>
          <option value="normal">Normal</option>
          <option value="emergency">Emergency</option>
        </select>
      </label>
      <TextField label="Description" field="description" draft={draft} setDraft={setDraft} multiline />
      <p className="text-xs text-muted md:col-span-2">You can save these details later. Approval uses the recorded scope, impact evaluation, and applicable compliance checks.</p>
      {draft.change_type === 'emergency' && <p className="text-sm text-muted md:col-span-2">Record the incident and urgent decision. Emergency handling still requires the applicable certification and notification checks.</p>}

      <details className={detailsClass}>
        <summary className={summaryClass}>
          Affected components and documentation
          <span className="ml-2 text-xs font-normal text-muted">{draft.component_ids.length} {draft.component_ids.length === 1 ? 'component' : 'components'} linked</span>
        </summary>
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2">
          <TextField label="Category" field="category" draft={draft} setDraft={setDraft} maxLength={100} />
          <TextField label="Affected components summary" field="affected_components_summary" draft={draft} setDraft={setDraft} />
          <TextField label="Affected documents summary" field="affected_docs_summary" draft={draft} setDraft={setDraft} />
          <TextField label="Affected documentation" field="affected_documentation" draft={draft} setDraft={setDraft} multiline />
          <div className="md:col-span-2">
            <p className="text-xs font-semibold text-ink">Linked components (multi-select)</p>
            <p className="mt-1 text-xs text-muted">Link at least one component before approval.</p>
            {components.length ? <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
              {components.map(component => <label key={component.id} className="flex items-center gap-2 text-sm text-ink">
                <input type="checkbox" checked={draft.component_ids.includes(component.id)}
                  onChange={() => setDraft(previous => ({ ...previous, component_ids: previous.component_ids.includes(component.id)
                    ? previous.component_ids.filter(id => id !== component.id) : [...previous.component_ids, component.id] }))} />
                <span><span className="font-medium">{component.component_uid}</span> · {component.definition}
                  <span className="block text-muted">Current {component.version} · relevance {component.classification_code} · {(component.regulatory_scope || 'unknown').replace(/_/g, ' ')}</span>
                </span>
              </label>)}
            </div> : <p className="mt-2 text-sm text-muted">No components in this register. Add a component in the Components tab before approval.</p>}
          </div>
          <p className="text-xs text-muted md:col-span-2">Record the planned component versions. The approved scope preserves these details.</p>
          {selectedComponents.map(component => <div key={component.id} className="grid min-w-0 grid-cols-1 gap-3 md:col-span-2 md:grid-cols-2">
            <label className={labelClass}><span>Planned version for {component.component_uid}</span>
              <input className={inputClass} maxLength={100} value={draft.planned_versions[component.id] || ''}
                onChange={event => setDraft(current => ({ ...current, planned_versions: { ...current.planned_versions, [component.id]: event.target.value } }))} />
            </label>
            <label className={labelClass}><span>Planned hash for {component.component_uid}</span>
              <input className={inputClass} maxLength={255} value={draft.planned_checksum_hashes[component.id] || ''}
                onChange={event => setDraft(current => ({ ...current, planned_checksum_hashes: { ...current.planned_checksum_hashes, [component.id]: event.target.value } }))} />
            </label>
            {danish && <label className={`${labelClass} md:col-span-2`}><span>Baseline scope assessment for {component.component_uid}</span>
              <textarea className={inputClass} value={draft.baseline_scope_assessments[component.id] || ''}
                onChange={event => setDraft(current => ({ ...current, baseline_scope_assessments: { ...current.baseline_scope_assessments, [component.id]: event.target.value } }))} />
              <span className="text-xs text-muted">For a component absent from the certified baseline, explain its scope and relationship to the platform.</span>
            </label>}
          </div>)}
          <label className="flex items-center gap-2 text-sm text-ink md:col-span-2">
            <input type="checkbox" checked={draft.integration_related}
              onChange={event => setDraft(previous => ({ ...previous, integration_related: event.target.checked }))} />
            Includes integration between base and game platforms
          </label>
        </div>
      </details>

      <details className={detailsClass}>
        <summary className={summaryClass}>
          Planning and justification
          <span className="ml-2 text-xs font-normal text-muted">{planningCount} of 6 details recorded</span>
        </summary>
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2">
          <p className="text-xs text-muted md:col-span-2">Complete all six planning details before approval. Leave planned dates blank until the schedule is known.</p>
          <TextField label="Complexity" field="complexity_classification" draft={draft} setDraft={setDraft} maxLength={100} multiline />
          <TextField label="Resource assessment" field="resource_assessment" draft={draft} setDraft={setDraft} multiline />
          <TextField label="Scheduling assessment" field="scheduling_assessment" draft={draft} setDraft={setDraft} multiline />
          <label className={labelClass}>
            <span>Planned Start</span>
            <input type="datetime-local" value={draft.planned_start_at}
              onChange={event => setDraft(previous => ({ ...previous, planned_start_at: event.target.value }))}
              className={inputClass} />
          </label>
          <label className={labelClass}>
            <span>Planned End</span>
            <input type="datetime-local" value={draft.planned_end_at} min={draft.planned_start_at || undefined}
              onChange={event => setDraft(previous => ({ ...previous, planned_end_at: event.target.value }))}
              className={inputClass} />
          </label>
          <TextField label="Justification" field="justification" draft={draft} setDraft={setDraft} multiline />
        </div>
      </details>

      <details className={detailsClass}>
        <summary className={summaryClass}>
          Impact evaluation
          <span className="ml-2 text-xs font-normal text-muted">{evaluationCount} of 4 evaluations recorded</span>
        </summary>
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2">
          <p className="text-xs text-muted md:col-span-2">Record all four impact evaluations before approval. CIAA means confidentiality, integrity, availability, and accountability.</p>
          <TextField label="Evaluation: expected effect" field="evaluation_effect" draft={draft} setDraft={setDraft} multiline />
          <TextField label="Evaluation: risk" field="evaluation_risk" draft={draft} setDraft={setDraft} multiline />
          <TextField label="Evaluation: regulatory impact" field="evaluation_regulatory_impact" draft={draft} setDraft={setDraft} multiline />
          <TextField label="Evaluation: CIAA impact" field="evaluation_ciaa_impact" draft={draft} setDraft={setDraft} multiline />
        </div>
      </details>
    </fieldset>

    {proposalReadOnly && <p className="text-sm text-muted md:col-span-2">The approved proposal is read-only. Record testing results below. Reject an approved change to revise its proposal; after implementation, create a new change.</p>}
    {danish ? <ChangeComplianceFields value={draft.compliance} onChange={compliance => setDraft(current => ({ ...current, compliance }))}
      components={selectedComponents} integrationRelated={draft.integration_related} /> : <details className={detailsClass} open={proposalReadOnly || undefined} onInvalidCapture={revealInvalidField}>
      <summary className={summaryClass}>
        Testing organization
        <span className="ml-2 text-xs font-normal text-muted">{draft.testing_org_required ? 'Required' : 'Not required'} · {testingStatus} · {draft.testing_org_cycle}</span>
      </summary>
      <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex items-center gap-2 text-sm text-ink md:col-span-2">
          <input type="checkbox" disabled={proposalReadOnly} checked={draft.testing_org_required}
            onChange={event => setDraft(previous => ({ ...previous, testing_org_required: event.target.checked }))} />
          Testing organization required
        </label>
        <p className="text-xs text-muted md:col-span-2">Record the testing organization's decision. Leave approval dates blank until you receive approval.</p>
        <label className={labelClass}>
          <span>Testing organization status</span>
          <select autoFocus={autoFocus && proposalReadOnly} aria-label="Testing organization status"
            value={draft.testing_org_status}
            onChange={event => setDraft(previous => ({ ...previous, testing_org_status: event.target.value }))}
            className={inputClass}>
            <option value="">Not recorded</option>
            <option value="pending">Pending</option>
            <option value="in_progress">In progress</option>
            <option value="approved">Approved</option>
            <option value="certified">Certified</option>
            <option value="rejected">Rejected</option>
            <option value="not_required">Not required</option>
            {draft.testing_org_status && !['pending', 'in_progress', 'approved', 'certified', 'rejected', 'not_required'].includes(draft.testing_org_status)
              && <option value={draft.testing_org_status}>{draft.testing_org_status}</option>}
          </select>
        </label>
        <label className={labelClass}>
          <span>Testing cycle</span>
          <select aria-label="Testing cycle" value={draft.testing_org_cycle}
            onChange={event => setDraft(previous => ({ ...previous, testing_org_cycle: event.target.value as TestingCycle }))}
            className={inputClass}>
            <option value="immediate">Immediate</option>
            <option value="quarterly">Quarterly</option>
            <option value="annual">Annual</option>
          </select>
        </label>
        <label className={labelClass}>
          <span>Testing organization approval date</span>
          <input type="datetime-local"
            max={new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)}
            value={draft.testing_org_approved_at}
            onChange={event => setDraft(previous => ({ ...previous, testing_org_approved_at: event.target.value }))}
            className={inputClass} />
        </label>
        <label className={labelClass}>
          <span>Next testing due date</span>
          <input type="datetime-local" value={draft.testing_org_next_due_at}
            onChange={event => setDraft(previous => ({ ...previous, testing_org_next_due_at: event.target.value }))}
            className={inputClass} />
        </label>
      </div>
    </details>}
  </>
}
