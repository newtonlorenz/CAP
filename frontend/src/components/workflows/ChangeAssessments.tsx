import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import { workflowsApi } from '../../api/workflows'
import { preparationApi } from '../../api/preparation'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { getApiErrorMessage } from '../../api/errors'
import type { CertificationProject, PaginatedResponse, Requirement, RequirementSetSummary } from '../../types'
import type { ChangeImpact, ChangeImpactInput } from '../../types/workflows'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function ChangeAssessments({ changeId, jurisdictionId, canEdit, canManage, changeName, blockingAssessmentIds = [] }: { blockingAssessmentIds?: string[]; changeId: string; jurisdictionId: string; canEdit: boolean; canManage: boolean; changeName: string }) {
  const client = useQueryClient()
  const [draft, setDraft] = useState<ChangeImpact[]>([])
  const [dirty, setDirty] = useState(false)
  const [setId, setSetId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [requirementId, setRequirementId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [reusedScope, setReusedScope] = useState({ setId: '', versionId: '', projectId: '' })
  const [autoSelectVersion, setAutoSelectVersion] = useState(false)
  const [duplicateAttempt, setDuplicateAttempt] = useState(false)
  const [rationale, setRationale] = useState('')
  const [name, setName] = useState('')
  const [deadline, setDeadline] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const impacts = useQuery({ queryKey: ['change-impacts', changeId], queryFn: () => workflowsApi.impacts(changeId) })
  const assessments = useQuery({ queryKey: ['change-assessments', changeId], queryFn: () => workflowsApi.changeAssessments(changeId) })
  const sets = useQuery({ queryKey: ['requirements-sets', 'change-scope', jurisdictionId], queryFn: async () => (await api.get<PaginatedResponse<RequirementSetSummary>>('/requirements/sets', { params: { jurisdiction_id: jurisdictionId, limit: 1000, include_empty_sets: true } })).data, enabled: canEdit })
  const versions = useQuery({ queryKey: ['requirement-versions', setId], queryFn: () => preparationApi.requirementVersions(setId), enabled: Boolean(setId) })
  const requirements = useQuery({ queryKey: ['impact-requirements', versionId], queryFn: async () => (await api.get<PaginatedResponse<Requirement>>('/requirements', { params: { requirement_set_version_id: versionId, limit: 1000 } })).data, enabled: Boolean(versionId) })
  const projects = useQuery({ queryKey: ['certification-projects', 'change-scope', jurisdictionId], queryFn: async () => (await api.get<PaginatedResponse<CertificationProject>>('/certification-projects', { params: { jurisdiction_id: jurisdictionId, limit: 1000 } })).data, enabled: canEdit })
  useEffect(() => { if (impacts.data && !dirty) setDraft(impacts.data.items) }, [impacts.data, dirty])
  useEffect(() => {
    if (!autoSelectVersion || !setId || !versions.isSuccess || versions.isFetching || versions.isPaused) return
    const approved = versions.data.items.filter(item => item.status === 'approved')
    if (!versionId && approved.length === 1) setVersionId(approved[0].id)
    setAutoSelectVersion(false)
  }, [autoSelectVersion, setId, versionId, versions.data, versions.isSuccess, versions.isFetching, versions.isPaused])
  const save = useMutation({ mutationFn: () => workflowsApi.saveImpacts(changeId, draft.map(({ requirement_set_version_id, requirement_id, certification_project_id, rationale }): ChangeImpactInput => ({ requirement_set_version_id, requirement_id, certification_project_id, rationale }))), onSuccess: data => { client.setQueryData(['change-impacts', changeId], data); setDraft(data.items); setSelected([]); setDirty(false); void client.invalidateQueries({ queryKey: ['change-impacts', changeId] }) } })
  const create = useMutation({ mutationFn: () => workflowsApi.createChangeAssessments(changeId, { impact_ids: selected, name: (name.trim() || `Change assessment: ${changeName}`).slice(0, 255), ...(deadline ? { deadline: new Date(`${deadline}T23:59:59`).toISOString() } : {}) }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['change-assessments', changeId] }); void client.invalidateQueries({ queryKey: ['review-cycles'] }); setSelected([]); setName(''); setDeadline('') } })
  const updateBlocking = useMutation({mutationFn: (ids: string[]) => api.patch(`/change-management/changes/${changeId}`, {blocking_assessment_ids:ids}),onSuccess: () => {void client.invalidateQueries({queryKey:['change-management']})}})
  const pendingScope = setId !== reusedScope.setId || versionId !== reusedScope.versionId || projectId !== reusedScope.projectId
  useDraftNavigationGuard(Boolean(dirty || pendingScope || requirementId || rationale || name || deadline || selected.length || save.isPending || create.isPending || updateBlocking.isPending))
  const approvedVersion = versions.data?.items.find(item => item.id === versionId && item.status === 'approved')
  const selectedSet = sets.data?.items.find(item => item.document_id === setId)
  const selectedRequirement = requirements.data?.items.find(item => item.id === requirementId)
  const selectedProject = projects.data?.items.find(item => item.id === projectId)
  const duplicateImpact = draft.some(item => item.requirement_set_version_id === versionId
    && item.requirement_id === (requirementId || null) && item.certification_project_id === (projectId || null))
  const canAdd = Boolean(approvedVersion && selectedSet && !versions.isFetching && !versions.isPaused && !versions.isError && !save.isPending
    && !sets.isError && !projects.isError && draft.length < 200
    && (!requirementId || (selectedRequirement && !requirements.isFetching && !requirements.isError))
    && (!projectId || (selectedProject && !projects.isFetching)))
  const add = () => {
    if (!canAdd || !approvedVersion || !selectedSet) return
    if (duplicateImpact) { setDuplicateAttempt(true); return }
    setDraft(current => [...current, { id: `draft-${crypto.randomUUID()}`, requirement_set_version_id: versionId, requirement_id: requirementId || null, certification_project_id: projectId || null, rationale: rationale.trim(), set_name: selectedSet.name || selectedSet.filename || 'Requirement set', version_number: approvedVersion.version_number, project_name: selectedProject?.name || null, requirement_reference_id: selectedRequirement?.reference_id || null, requirement_title: selectedRequirement?.title || null }])
    setDirty(true)
    setReusedScope({ setId, versionId, projectId })
    setRationale('')
    setRequirementId('')
    setDuplicateAttempt(false)
  }
  return <section className="change-assessments space-y-4 border-y border-line py-4">
    <div><h4 className="font-semibold">Requirement impact and assessments</h4><p className="mt-1 max-w-prose text-sm text-muted">Identify affected approved requirements, record the impact, then create an assessment when needed. Assessment decisions are separate from change approval.</p></div>
    {impacts.isError ? <LoadError subject="Requirement impacts" onRetry={() => impacts.refetch()} /> : impacts.isLoading ? <p role="status">Loading impacts…</p> : <>
      {draft.length ? <ul className="divide-y divide-line">{draft.map(item => <li key={item.id} className="flex items-start gap-3 py-3">{canManage && !dirty && <input type="checkbox" aria-label={`Assess ${item.set_name} v${item.version_number}${item.requirement_id ? ` ${item.requirement_reference_id || 'selected requirement'}` : ''}`} checked={selected.includes(item.id)} onChange={event => setSelected(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} />}<div className="min-w-0 flex-1"><p className="font-medium">{item.set_name} v{item.version_number}{item.requirement_id ? ` · ${item.requirement_reference_id || 'Selected requirement'}${item.requirement_title ? ` ${item.requirement_title}` : ''}` : ' · Entire version'}{item.project_name && item.certification_project_id ? <> · <Link className="text-accent underline" to={`/certification-projects?project=${item.certification_project_id}`}>{item.project_name}</Link></> : null}</p>{canEdit ? <label className="mt-2 block text-sm">Impact rationale<textarea className="mt-1 block w-full px-3 py-2" maxLength={4000} value={item.rationale} disabled={save.isPending} onChange={event => { setDraft(current => current.map(row => row.id === item.id ? { ...row, rationale: event.target.value } : row)); setDirty(true) }} /></label> : <p className="mt-1 text-sm text-muted">{item.rationale || 'No rationale recorded.'}</p>}</div>{canEdit && <Button size="sm" disabled={save.isPending} onClick={() => { setDraft(current => current.filter(row => row.id !== item.id)); setDirty(true) }}>Remove impact</Button>}</li>)}</ul> : <p className="text-sm text-muted">No structured requirement impacts have been recorded.</p>}
      {canEdit && <details>
        <summary className="cursor-pointer text-sm font-semibold">Add requirement impact</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <p className="text-xs text-muted sm:col-span-2">The set, version, and project stay selected so you can add several requirements.</p>
          <label className="text-sm">Requirement set
            <select className="mt-1 block w-full px-3 py-2" value={setId} onChange={event => {
              setSetId(event.target.value)
              setVersionId('')
              setRequirementId('')
              setAutoSelectVersion(Boolean(event.target.value))
              setDuplicateAttempt(false)
            }}>
              <option value="">Select a set</option>
              {sets.data?.items.map(item => <option key={item.document_id} value={item.document_id}>{item.name || item.filename}</option>)}
            </select>
          </label>
          <label className="text-sm">Approved version
            <select className="mt-1 block w-full px-3 py-2" value={versionId}
              disabled={!setId || versions.isFetching || versions.isPaused || versions.isError}
              onChange={event => {
                setVersionId(event.target.value)
                setRequirementId('')
                setAutoSelectVersion(false)
                setDuplicateAttempt(false)
              }}>
              <option value="">Select an approved version</option>
              {versions.data?.items.filter(item => item.status === 'approved').map(item => <option key={item.id} value={item.id}>Version {item.version_number}</option>)}
            </select>
          </label>
          <label className="text-sm">Affected requirement
            <select className="mt-1 block w-full px-3 py-2" value={requirementId}
              disabled={!approvedVersion || requirements.isError || requirements.isFetching}
              onChange={event => { setRequirementId(event.target.value); setDuplicateAttempt(false) }}>
              <option value="">Entire version</option>
              {requirements.data?.items.map(item => <option key={item.id} value={item.id}>{item.reference_id} {item.title || ''}</option>)}
            </select>
          </label>
          <label className="text-sm">Certification project (optional)
            <select className="mt-1 block w-full px-3 py-2" value={projectId}
              onChange={event => { setProjectId(event.target.value); setDuplicateAttempt(false) }}>
              <option value="">No project context</option>
              {projects.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">Impact rationale
            <textarea className="mt-1 block w-full px-3 py-2" maxLength={4000} value={rationale} onChange={event => setRationale(event.target.value)} />
          </label>
          {duplicateAttempt && duplicateImpact && <p role="alert" className="text-sm text-danger sm:col-span-2">
            This impact is already listed for the selected version and project. Edit its rationale above or choose another requirement.
          </p>}
          <div><Button onClick={add} disabled={!canAdd}>Add impact to draft</Button></div>
        </div>
        {(sets.isError || versions.isError || projects.isError || requirements.isError) && <p role="alert" className="mt-2 text-sm text-danger">
          Scope options could not be loaded. Try again before adding an impact. <button type="button" className="underline" onClick={() => { if (sets.isError) void sets.refetch(); if (versions.isError) void versions.refetch(); if (projects.isError) void projects.refetch(); if (requirements.isError) void requirements.refetch() }}>Try again</button>
        </p>}
      </details>}
      {canEdit && dirty && <div className="flex gap-2"><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save impacts</Button><Button disabled={save.isPending} onClick={() => { setDirty(false); setDraft(impacts.data?.items || []) }}>Discard impact changes</Button></div>}
      {save.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(save.error, 'Impacts could not be saved. Your draft is preserved.')}</p>}
      {canManage && !dirty && draft.length > 0 && <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); create.mutate() }}><label className="text-sm">Assessment name<input className="mt-1 block px-3 py-2" maxLength={255} placeholder={`Change assessment: ${changeName}`} value={name} onChange={event => setName(event.target.value)} /></label><label className="text-sm">Deadline (optional)<input type="date" className="mt-1 block px-3 py-2" value={deadline} onChange={event => setDeadline(event.target.value)} /></label><Button type="submit" loading={create.isPending} disabled={selected.length === 0}>Create assessment for selected impacts</Button></form>}
      {create.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(create.error, 'The assessment could not be created. Your selection is preserved.')}</p>}
    </>}
    {updateBlocking.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(updateBlocking.error, 'Assessment requirement could not be updated.')}</p>}
    <div className="assessment-groups">
      {assessments.isError ? <LoadError subject="Change assessments" onRetry={() => assessments.refetch()} /> : assessments.isLoading ? <p role="status">Loading assessments…</p> : (['required', 'advisory'] as const).map(group => {
        const items = (assessments.data?.items || []).filter(item => blockingAssessmentIds.includes(item.id) === (group === 'required'))
        return <section className="assessment-group" key={group} aria-label={`${group === 'required' ? 'Required' : 'Advisory'} assessments`}>
          <header><h5>{group === 'required' ? 'Required assessments' : 'Advisory assessments'}</h5><span>{items.length}</span></header>
          <p className="assessment-group-description">{group === 'required' ? 'These assessments gate change completion. Their outcomes and evidence must satisfy the current readiness checks.' : 'These assessments inform the change and do not block completion under the required-assessment rule.'}</p>
          {items.length ? <ul>{items.map(item => <li key={item.id}><div className="min-w-0"><Link className="text-accent underline" to={`/review-cycles/${item.id}`}>{item.name}</Link><p className="mt-1 text-sm text-muted">{item.status.replace(/_/g, ' ')}{item.deadline ? ` · Due ${new Date(item.deadline).toLocaleDateString('en-GB')}` : ''}</p></div>{canEdit && <label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={updateBlocking.isPending} checked={blockingAssessmentIds.includes(item.id)} onChange={event => updateBlocking.mutate(event.target.checked ? [...blockingAssessmentIds,item.id] : blockingAssessmentIds.filter(id => id !== item.id))} />Required before change completion</label>}<Link className="text-sm font-medium text-accent underline" to={`/review-cycles/${item.id}`}>Open assessment</Link></li>)}</ul> : <p className="assessment-group-empty">No {group} assessments linked.</p>}
        </section>
      })}
    </div>
  </section>
}
