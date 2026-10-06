import { useState, type FormEvent } from 'react'
import type { CertificationProject } from '../../types'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import Button from '../ui/Button'

export type EngagementUpdate = Partial<Pick<CertificationProject,
  'assurance_type' | 'provider_name' | 'engagement_reference' | 'assurance_scope' |
  'system_version' | 'scheduled_test_date' | 'actual_test_date' | 'report_reference' |
  'report_outcome' | 'report_issued_at' | 'report_link'>>

type EngagementMode = 'testing' | 'report'

type EngagementDraft = Record<keyof EngagementUpdate, string>
const dateValue = (value: string | null | undefined) => value ? value.slice(0, 10) : ''
const initialDraft = (project: CertificationProject): EngagementDraft => ({
  assurance_type: project.assurance_type || '',
  provider_name: project.provider_name || '',
  engagement_reference: project.engagement_reference || '',
  assurance_scope: project.assurance_scope || '',
  system_version: project.system_version || '',
  scheduled_test_date: dateValue(project.scheduled_test_date),
  actual_test_date: dateValue(project.actual_test_date),
  report_reference: project.report_reference || '',
  report_outcome: project.report_outcome || '',
  report_issued_at: dateValue(project.report_issued_at),
  report_link: project.report_link || '',
})
const nullableText = (value: string) => value.trim() || null
const nullableDate = (value: string) => value ? new Date(`${value}T00:00:00Z`).toISOString() : null
const payload = (draft: EngagementDraft, mode: EngagementMode): EngagementUpdate => mode === 'testing' ? {
  assurance_type: nullableText(draft.assurance_type) as EngagementUpdate['assurance_type'],
  provider_name: nullableText(draft.provider_name),
  engagement_reference: nullableText(draft.engagement_reference),
  assurance_scope: nullableText(draft.assurance_scope),
  system_version: nullableText(draft.system_version),
  scheduled_test_date: nullableDate(draft.scheduled_test_date),
  actual_test_date: nullableDate(draft.actual_test_date),
} : {
  report_reference: nullableText(draft.report_reference),
  report_outcome: nullableText(draft.report_outcome) as EngagementUpdate['report_outcome'],
  report_issued_at: nullableDate(draft.report_issued_at),
  report_link: nullableText(draft.report_link),
}

export default function CertificationEngagement({ project, mode, canManage, saving, onSave }: {
  project: CertificationProject
  mode: EngagementMode
  canManage: boolean
  saving: boolean
  onSave: (update: EngagementUpdate) => Promise<unknown>
}) {
  const [baseline, setBaseline] = useState<EngagementDraft>(() => initialDraft(project))
  const [draft, setDraft] = useState<EngagementDraft>(() => initialDraft(project))
  const [saveFailed, setSaveFailed] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)
  useDraftNavigationGuard(dirty || saving)
  const change = (name: keyof EngagementDraft, value: string) => {
    setDraft((current) => ({ ...current, [name]: value }))
    setSaveFailed(false)
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!dirty || saving) return
    try {
      await onSave(payload(draft, mode))
      setBaseline(draft)
      setSaveFailed(false)
    } catch {
      setSaveFailed(true)
    }
  }
  const field = (name: keyof EngagementDraft, label: string, type = 'text') => (
    <label className="text-sm text-muted">{label}
      <input name={name} type={type} value={draft[name]} onChange={(event) => change(name, event.target.value)}
        className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink" />
    </label>
  )
  return <form onSubmit={submit} className="space-y-4 rounded-lg border border-line p-4">
    <div><h2 className="font-semibold text-ink">{mode === 'testing' ? 'Testing engagement' : 'Recorded test report'}</h2><p className="text-sm text-muted">{mode === 'testing' ? 'Record the provider, scope and testing dates.' : 'Record the provider’s report. A recorded result does not represent an authority decision.'}</p></div>
    <fieldset disabled={!canManage || saving} className="grid gap-3 sm:grid-cols-2">
      {mode === 'testing' ? <>
      <label className="text-sm text-muted">Assurance type<select name="assurance_type" value={draft.assurance_type} onChange={(event) => change('assurance_type', event.target.value)} className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink"><option value="">Not specified</option><option value="test">Test</option><option value="audit">Audit</option><option value="certification">Certification</option></select></label>
      {field('provider_name', 'Test lab or assurance provider')}
      {field('engagement_reference', 'Engagement reference')}
      {field('system_version', 'System version')}
      <label className="text-sm text-muted sm:col-span-2">Assurance scope<textarea name="assurance_scope" value={draft.assurance_scope} onChange={(event) => change('assurance_scope', event.target.value)} rows={3} className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink" /></label>
      {field('scheduled_test_date', 'Scheduled test date', 'date')}
      {field('actual_test_date', 'Actual test date', 'date')}
      </> : <>
      {field('report_reference', 'Report reference')}
      {field('report_issued_at', 'Report issued date', 'date')}
      <label className="text-sm text-muted">Recorded report outcome<select name="report_outcome" value={draft.report_outcome} onChange={(event) => change('report_outcome', event.target.value)} className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink"><option value="">Not recorded</option><option value="passed">Passed</option><option value="passed_with_findings">Passed with findings</option><option value="failed">Failed</option></select></label>
      {field('report_link', 'Report link (HTTP or HTTPS)', 'url')}
      </>}
    </fieldset>
    {mode === 'report' && project.report_link && <a className="text-sm text-accent underline" href={project.report_link} target="_blank" rel="noopener noreferrer">Open recorded report</a>}
    {dirty && <p className="text-xs text-warning">Unsaved {mode === 'testing' ? 'engagement' : 'report'} changes</p>}
    {saveFailed && <p role="alert" className="text-xs text-danger">Could not save the {mode === 'testing' ? 'engagement' : 'report'}. Your changes are still here; try again.</p>}
    {canManage && <div><Button type="submit" loading={saving} disabled={!dirty}>Save {mode === 'testing' ? 'engagement' : 'report'}</Button></div>}
  </form>
}
