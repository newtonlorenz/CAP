import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { preparationApi } from '../../api/preparation'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { getApiErrorMessage } from '../../api/errors'
import { formatDate } from '../../utils/dateFormat'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'
import LoadError from '../ui/LoadError'
import NewPackFormEditor from '../applications/NewPackFormEditor'
import type { PreparationField } from '../../types/preparation'

export default function ProjectForms({ projectId, jurisdictionId, canManage }: { projectId: string; jurisdictionId: string; canManage: boolean }) {
  const client = useQueryClient()
  const [page, setPage] = useState(0)
  const pageSize = 100
  const [name, setName] = useState('')
  const [setup, setSetup] = useState<{ template_id?: string; form_fields?: PreparationField[]; original_evidence_ids: string[] }>({ form_fields: [], original_evidence_ids: [] })
  const [formDirty, setFormDirty] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const [showCreate, setShowCreate] = useState(false)
  const [showDiscard, setShowDiscard] = useState(false)
  const hasDraft = Boolean(formDirty || name || setup.template_id || setup.form_fields?.length || setup.original_evidence_ids.length)
  const cases = useQuery({ queryKey: ['preparation', 'project-cases', projectId, jurisdictionId, page], queryFn: () => preparationApi.cases(new URLSearchParams({ project_id: projectId, jurisdiction_id: jurisdictionId, limit: String(pageSize), skip: String(page * pageSize) })) })
  const create = useMutation({ mutationFn: () => preparationApi.createCase({ name: name.trim(), ...(setup.template_id ? { template_id: setup.template_id } : { fields: setup.form_fields || [] }), original_evidence_ids: setup.original_evidence_ids, jurisdiction_id: jurisdictionId, project_id: projectId }), onSuccess: () => { void client.invalidateQueries({ queryKey: ['preparation'] }); setName(''); setFormDirty(false); setSetup({ form_fields: [], original_evidence_ids: [] }); setEditorKey(key => key + 1); setShowCreate(false); setShowDiscard(false) } })
  useDraftNavigationGuard(hasDraft || create.isPending)
  const closeCreate = () => { if (create.isPending) return; if (hasDraft) setShowDiscard(true); else { setShowCreate(false); create.reset() } }
  const discard = () => { setName(''); setFormDirty(false); setSetup({ form_fields: [], original_evidence_ids: [] }); setEditorKey(key => key + 1); setShowCreate(false); setShowDiscard(false); create.reset() }
  const rows = (cases.data?.items || []).filter(item => item.project_id === projectId)
  return <div className="space-y-5">
    <div><h2 className="text-lg font-semibold">Forms and evidence</h2><p className="mt-1 max-w-prose text-sm text-muted">Prepare project forms and attach supporting evidence to their answers. Form readiness and requirement assessment decisions remain separate.</p></div>
    {cases.isError ? <LoadError subject="Project forms" onRetry={() => cases.refetch()} /> : cases.isLoading ? <p role="status" className="text-sm text-muted">Loading project forms…</p> : rows.length ? <ul className="divide-y divide-line">{rows.map(item => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><Link className="font-semibold text-accent underline" to={`/preparation?case=${item.id}&return_project=${projectId}`}>{item.name}</Link><p className="mt-1 text-sm text-muted">{item.template_name} · {item.status} · {item.readiness.ready ? 'Required answers ready' : `${item.readiness.answered_count} of ${item.readiness.required_count} required answers`} {item.due_date ? `· Due ${formatDate(item.due_date)}` : ''}</p></div><Link className="text-sm text-accent underline" to={`/preparation?case=${item.id}&return_project=${projectId}`}>Open form and evidence</Link></li>)}</ul> : <p className="text-sm text-muted">No forms are linked to this project. Add a form, import reviewed questions or use a saved blank form.</p>}
    {(cases.data?.total || 0) > pageSize && <nav aria-label="Project forms pages" className="flex items-center gap-3 text-sm"><Button size="sm" disabled={page === 0 || cases.isFetching} onClick={() => setPage(current => current - 1)}>Previous forms</Button><span>Page {page + 1} of {Math.ceil((cases.data?.total || 0) / pageSize)}</span><Button size="sm" disabled={(page + 1) * pageSize >= (cases.data?.total || 0) || cases.isFetching} onClick={() => setPage(current => current + 1)}>Next forms</Button></nav>}
    {canManage && <>
      <Button onClick={() => setShowCreate(true)}>Add form</Button>
      <Modal open={showCreate} title="Add project form" description="Create a form for this project using questions, a reviewed import or a saved blank form." size="lg" onClose={closeCreate}>
      <div className="space-y-4">
        <label className="block text-sm">Form name<input className="mt-1 block w-full px-3 py-2" required maxLength={255} value={name} onChange={event => setName(event.target.value)} /></label>
        <NewPackFormEditor key={editorKey} jurisdictionId={jurisdictionId} disabled={create.isPending} kindScope="certification" onDirtyChange={dirty => { if (dirty) setFormDirty(true) }} onChange={setSetup} />
        <Button disabled={!name.trim() || Boolean(setup.form_fields?.some(field => !field.label.trim())) || create.isPending} loading={create.isPending} onClick={() => create.mutate()}>Create form</Button>
        {create.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(create.error, 'The form could not be created. Your entries are preserved.')}</p>}
        <Button disabled={create.isPending} onClick={closeCreate}>Cancel</Button>
      </div></Modal>
      <ConfirmDialog open={showDiscard} title="Discard this form draft?" description="The form has not been created. Discarding removes the questions and details entered here." confirmLabel="Discard draft" onConfirm={discard} onClose={() => setShowDiscard(false)} />
    </>}
  </div>
}
