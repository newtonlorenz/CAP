import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { workflowsApi } from '../../api/workflows'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { getApiErrorMessage } from '../../api/errors'
import { formatDate } from '../../utils/dateFormat'
import type { ReviewCycle } from '../../types'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function ProjectMaintenance({ projectId, jurisdictionId, canManage, assessments }: { projectId: string; jurisdictionId: string; canManage: boolean; assessments: ReviewCycle[] }) {
  const client = useQueryClient()
  const [name, setName] = useState('')
  const [cadence, setCadence] = useState('365')
  const [firstRun, setFirstRun] = useState('')
  const [summary, setSummary] = useState('')
  const plans = useQuery({ queryKey: ['maintenance-plans', 'project', projectId], queryFn: () => workflowsApi.maintenancePlans(projectId) })
  const refresh = () => { void client.invalidateQueries({ queryKey: ['maintenance-plans'] }); void client.invalidateQueries({ queryKey: ['review-cycles'] }); void client.invalidateQueries({ queryKey: ['program-workspace-summary'] }) }
  const create = useMutation({ mutationFn: () => workflowsApi.createMaintenancePlan({ name: name.trim(), jurisdiction_id: jurisdictionId, certification_project_id: projectId, cadence_days: Number(cadence), next_run_at: new Date(`${firstRun}T09:00:00`).toISOString(), reminder_days: 7, escalation_days: 3 }), onSuccess: () => { refresh(); setName(''); setFirstRun('') } })
  const update = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => workflowsApi.updateMaintenancePlan(id, { status }), onSuccess: refresh })
  const run = useMutation({ mutationFn: () => workflowsApi.runDue(projectId), onSuccess: result => { refresh(); setSummary(`${result.generated_cycles} maintenance assessments created for due plans in this project.`) } })
  useDraftNavigationGuard(Boolean(name || firstRun || create.isPending || update.isPending || run.isPending))
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">Maintenance</h2><p className="mt-1 max-w-prose text-sm text-muted">Set a recurring assessment schedule for this project's approved requirements. Run due plans when you are ready to create the next assessments.</p></div>{canManage && <Button onClick={() => run.mutate()} loading={run.isPending} disabled={plans.isError || plans.isLoading}>Run due plans</Button>}</div>
    {summary && <p role="status" className="text-sm text-success">{summary}</p>}
    {run.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(run.error, 'Due assessments could not be created. Try again.')}</p>}
    {plans.isError ? <LoadError subject="Maintenance plans" onRetry={() => plans.refetch()} /> : plans.isLoading ? <p role="status">Loading maintenance plans…</p> : plans.data?.items.length ? <ul className="divide-y divide-line">{plans.data.items.map(plan => <li key={plan.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="font-semibold">{plan.name}</p><p className="mt-1 text-sm text-muted">Every {plan.cadence_days} days · {plan.status} · Next run {plan.next_run_at ? formatDate(plan.next_run_at) : 'not scheduled'}</p></div>{canManage && plan.status !== 'archived' && <Button size="sm" disabled={update.isPending} onClick={() => update.mutate({ id: plan.id, status: plan.status === 'active' ? 'paused' : 'active' })}>{plan.status === 'active' ? 'Pause plan' : 'Resume plan'}</Button>}</li>)}</ul> : <p className="text-sm text-muted">No maintenance plans are linked to this project.</p>}
    {update.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(update.error, 'The plan could not be updated. Try again.')}</p>}
    {canManage && <details className="border-t border-line pt-4"><summary className="cursor-pointer font-semibold">Add maintenance plan</summary><form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); create.mutate() }}><label className="text-sm">Plan name<input required maxLength={255} className="mt-1 block px-3 py-2" value={name} onChange={event => setName(event.target.value)} /></label><label className="text-sm">Cadence in days<input type="number" required min={1} max={3650} className="mt-1 block w-32 px-3 py-2" value={cadence} onChange={event => setCadence(event.target.value)} /></label><label className="text-sm">First due date<input type="date" required className="mt-1 block px-3 py-2" value={firstRun} onChange={event => setFirstRun(event.target.value)} /></label><Button type="submit" loading={create.isPending} disabled={!name.trim() || !firstRun || !cadence}>Add plan</Button></form>{create.isError && <p role="alert" className="mt-2 text-sm text-danger">{getApiErrorMessage(create.error, 'The plan could not be saved. Your entries are preserved.')}</p>}</details>}
    <section className="border-t border-line pt-4"><h3 className="font-semibold">Assessment history</h3>{assessments.filter(item => item.cycle_type === 'maintenance').length ? <ul className="mt-2 divide-y divide-line">{assessments.filter(item => item.cycle_type === 'maintenance').map(item => <li className="flex flex-wrap justify-between gap-2 py-3" key={item.id}><Link className="text-accent underline" to={`/review-cycles/${item.id}`}>{item.name}</Link><span className="text-sm text-muted">{item.status} · {item.closed_at ? `Closed ${formatDate(item.closed_at)}` : item.deadline ? `Due ${formatDate(item.deadline)}` : 'No deadline'}</span></li>)}</ul> : <p className="mt-2 text-sm text-muted">No maintenance assessments have been created.</p>}</section>
  </div>
}
