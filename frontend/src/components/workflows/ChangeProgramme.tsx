import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type { ComponentRegister } from '../../types'
import type { ProgrammeAssurance, ResponsibilityRole } from '../../types/changeManagement'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { getApiErrorMessage } from '../../api/errors'
import Button from '../ui/Button'
import ConfirmDialog from '../ui/ConfirmDialog'

const fields: Array<{ key: keyof ProgrammeAssurance; label: string; date?: boolean; group: string }> = [
  { key: 'change_plan_reference', label: 'Approved change-management plan reference', group: 'Governance' },
  { key: 'change_plan_approved_by', label: 'Senior manager who approved the plan', group: 'Governance' },
  { key: 'change_plan_approved_at', label: 'Senior-management approval date', date: true, group: 'Governance' },
  { key: 'change_plan_approval_evidence', label: 'Plan approval evidence reference', group: 'Governance' },
  { key: 'responsible_owner', label: 'Responsible change-management personnel', group: 'Governance' },
  { key: 'integration_procedure_reference', label: 'Integration-check procedure reference', group: 'Governance' },
  { key: 'integration_procedure_approved_at', label: 'ATO approval of integration procedure', date: true, group: 'Governance' },
  { key: 'integration_procedure_ato', label: 'ATO approving the integration procedure', group: 'Governance' },
  { key: 'latest_certification_at', label: 'Latest SCP.06 certification completed', date: true, group: 'Annual certification' },
  { key: 'certification_ato', label: 'Accredited certification body', group: 'Annual certification' },
  { key: 'ato_accreditation_reference', label: 'Certification-body accreditation reference', group: 'Annual certification' },
  { key: 'ato_accreditation_evidence', label: 'Accreditation evidence reference', group: 'Annual certification' },
  { key: 'certification_reference', label: 'SCP.06 standard-report reference', group: 'Annual certification' },
  { key: 'certification_evidence', label: 'Signed standard-report evidence reference', group: 'Annual certification' },
  { key: 'report_submitted_at', label: 'Standard report submitted to DGA', date: true, group: 'Annual certification' },
  { key: 'cadence_anchor_at', label: 'Original certification cadence anchor', date: true, group: 'Annual certification' },
  { key: 'renewal_due_at', label: 'Next renewal due under that cadence', date: true, group: 'Annual certification' },
  { key: 'postponement_notified_at', label: 'DGA notified before postponing renewal', date: true, group: 'Renewal postponement' },
  { key: 'postponement_reference', label: 'DGA notification receipt reference', group: 'Renewal postponement' },
  { key: 'postponed_until', label: 'Postponed renewal and report deadline', date: true, group: 'Renewal postponement' },
]
function displayDate(value?: string | null) { return value ? new Date(value).toLocaleDateString('en-GB') : 'Not recorded' }
function inputDate(value?: string | null) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
export default function ChangeProgramme({ register, canEdit, onDraftState }: { register: ComponentRegister; canEdit: boolean; onDraftState?: (dirty: boolean, saving: boolean) => void }) {
  const client = useQueryClient()
  const [value, setValue] = useState<ProgrammeAssurance>(register.programme_assurance || {})
  const [role, setRole] = useState<ResponsibilityRole>(register.responsibility_role || 'unknown')
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [dirty, setDirty] = useState(false)
  useEffect(() => { if (!dirty) { setValue(register.programme_assurance || {}); setRole(register.responsibility_role || 'unknown') } }, [register, dirty])
  const save = useMutation({ mutationFn: async () => (await api.patch<ComponentRegister>(`/change-management/registers/${register.id}`, { responsibility_role: role, programme_assurance: value })).data, onSuccess: () => { setDirty(false); void client.invalidateQueries({ queryKey: ['change-management', 'registers'] }); void client.invalidateQueries({ queryKey: ['change-management', 'changes'] }); void client.invalidateQueries({ queryKey: ['change-management', 'linked-change'] }) } })
  useEffect(() => { onDraftState?.(dirty, save.isPending); return () => onDraftState?.(false, false) }, [dirty, save.isPending, onDraftState])
  useDraftNavigationGuard(dirty || save.isPending)
  const ready = register.programme_readiness
  return <section className="space-y-5 rounded-xl border border-line bg-surface p-4 sm:p-6" aria-label="Danish change-management programme">
    <div><h2 className="text-xl font-semibold">Programme assurance</h2><p className="mt-2 max-w-prose text-sm text-muted">Keep the approved change plan, responsible personnel, annual SCP.06 certification and regulator submission together. These records support your change workflow; CAP does not issue certification or submit reports to the authority.</p></div>
    {ready && <div role="status" className="space-y-2 border-y border-line py-3"><p className="font-medium">{ready.ready ? 'Programme evidence recorded' : 'Programme evidence needs attention'}</p><p className="text-sm">Certification due: {displayDate(ready.certification_due_at)} · DGA report due: {displayDate(ready.report_due_at)}</p>{ready.reasons.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm">{ready.reasons.map(item => <li key={item.code}>{item.message}</li>)}</ul>}</div>}
    <form className="space-y-5" onSubmit={event => { event.preventDefault(); save.mutate() }}>
      <fieldset disabled={!canEdit || save.isPending} className="space-y-5">
        <label className="block text-sm">Organisation's responsibility<select className="mt-1 block w-full rounded-lg border border-line-strong bg-surface px-3 py-2" value={role} onChange={event => { setRole(event.target.value as ResponsibilityRole); setDirty(true) }}><option value="unknown">Not assessed</option><option value="licensed_operator">Danish licensed operator</option><option value="licensed_game_supplier">Danish licensed game supplier</option><option value="unlicensed_subcontractor">Base-platform subcontractor without its own Danish licence</option></select></label>
        {['Governance', 'Annual certification', 'Renewal postponement'].map(group => <details key={group} open={group === 'Governance'} className="space-y-3 border-b border-line pb-4"><summary className="cursor-pointer font-semibold">{group}</summary>{group === 'Renewal postponement' && <p className="text-sm text-muted">Renewal can be postponed by at most two months with prior DGA notification. Certification and report share the extended deadline. The following renewal retains the original cadence.</p>}<div className="grid gap-3 sm:grid-cols-2">{fields.filter(field => field.group === group).map(field => <label key={field.key} className="text-sm">{field.label}<input type={field.date ? 'datetime-local' : 'text'} className="mt-1 block w-full rounded-lg border border-line-strong bg-surface px-3 py-2" value={field.date ? inputDate(value[field.key]) : value[field.key] || ''} onChange={event => { setValue(current => ({ ...current, [field.key]: field.date ? (event.target.value ? new Date(event.target.value).toISOString() : null) : event.target.value })); setDirty(true) }} /></label>)}</div></details>)}
      </fieldset>
      {canEdit && <div className="flex flex-wrap items-center gap-3"><Button variant="primary" type="submit" disabled={!dirty} loading={save.isPending}>Save programme evidence</Button><Button disabled={!dirty || save.isPending} onClick={() => setConfirmDiscard(true)}>Discard changes</Button>{save.isSuccess && !dirty && <span role="status" className="text-sm">Programme evidence saved.</span>}</div>}
      {save.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(save.error, 'Programme evidence could not be saved. Your draft is preserved.')}</p>}
    </form>
    <ConfirmDialog open={confirmDiscard} title="Discard programme changes?" description="Your saved programme evidence remains unchanged." confirmLabel="Discard changes" onClose={() => setConfirmDiscard(false)} onConfirm={() => {setDirty(false);setValue(register.programme_assurance || {});setRole(register.responsibility_role || 'unknown');setConfirmDiscard(false)}} />
    <a className="text-sm text-accent underline" href="https://spillemyndigheden.dk/media/xjoatyja/scp0600en31-change-management-programme.pdf" target="_blank" rel="noreferrer">Current SCP.06 programme · version 3.1, March 2026</a>
  </section>
}
