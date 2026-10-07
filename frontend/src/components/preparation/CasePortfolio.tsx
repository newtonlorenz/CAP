import { visibilityLabels, visibilityDescriptions, type Visibility } from '../../types/access'
import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import type {
  CertificationProject,
  Jurisdiction,
  UserMention,
} from '../../types'
import {
  PREPARATION_KINDS,
  preparationLabel,
  type PreparationCase,
  type PreparationKind,
  type PreparationTemplate,
} from '../../types/preparation'
import Button from '../ui/Button'
import Card from '../ui/Card'

export default function CasePortfolio({
  jurisdictions,
  users,
  projects,
  canManage,
  onOpen,
  kindScope,
  onTemplates,
  spaceJurisdictionId,
}: {
  jurisdictions: Jurisdiction[]
  users: UserMention[]
  projects: CertificationProject[]
  canManage: boolean
  onOpen: (id: string, kind?: PreparationKind) => void
  kindScope?: PreparationKind
  onTemplates?: () => void
  spaceJurisdictionId?: string | null
}) {
  const applications = kindScope === 'licence_application'
  const client = useQueryClient()
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [jurisdictionId, setJurisdictionId] = useState('')
  const [page, setPage] = useState(0)
  const [templateId, setTemplateId] = useState('')
  const [name, setName] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('secret')
  const [newJurisdictionId, setNewJurisdictionId] = useState('')
  const [ownerId, setOwnerId] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [projectId, setProjectId] = useState('')
  const fixedJurisdiction = spaceJurisdictionId !== undefined
  const effectiveJurisdictionId = fixedJurisdiction ? spaceJurisdictionId || '' : jurisdictionId
  const effectiveNewJurisdictionId = fixedJurisdiction ? spaceJurisdictionId || '' : newJurisdictionId
  useEffect(() => { setPage(0); setProjectId('') }, [spaceJurisdictionId])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const params = new URLSearchParams({
    skip: String(page * 100),
    limit: '100',
  })
  if (q.trim()) params.set('q', q.trim())
  const effectiveKind = kindScope || kind
  if (effectiveKind) params.set('kind', effectiveKind)
  if (status) params.set('status', status)
  if (effectiveJurisdictionId) params.set('jurisdiction_id', effectiveJurisdictionId)
  const cases = useQuery({
    queryKey: ['preparation', 'forms', q, effectiveKind, status, effectiveJurisdictionId, page],
    queryFn: () => preparationApi.cases(params),
    enabled: !fixedJurisdiction || Boolean(effectiveJurisdictionId),
  })
  const templates = useQuery({
    queryKey: ['preparation', 'templates'],
    queryFn: preparationApi.templates,
    enabled: canManage,
  })
  const availableTemplates = templates.data?.items.filter(
    (template) => template.active && (!kindScope || template.kind === kindScope),
  ) || []
  const caseProjects = projects.filter(
    (project) => project.jurisdiction_id === effectiveNewJurisdictionId,
  )
  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (
      busy ||
      !availableTemplates.some((template) => template.id === templateId) ||
      !effectiveNewJurisdictionId
    ) return
    setBusy(true)
    setError('')
    try {
      const created = await preparationApi.createCase({
        visibility,
        template_id: templateId,
        jurisdiction_id: effectiveNewJurisdictionId,
        name: name.trim(),
        ...(ownerId ? { owner_id: ownerId } : {}),
        ...(dueDate ? { due_date: dueDate } : {}),
        ...(projectId ? { project_id: projectId } : {}),
      })
      void client.invalidateQueries({ queryKey: ['preparation', 'forms'] })
      onOpen(created.id, created.kind)
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          'Case could not be created. Check the details and try again.',
        ),
      )
    } finally {
      setBusy(false)
    }
  }
  const lookupJurisdiction = (id: string) =>
    jurisdictions.find((item) => item.id === id)?.name ||
    'Jurisdiction unavailable'
  const lookupOwner = (id: string | null) =>
    users.find((item) => item.id === id)?.full_name ||
    (id ? 'Assigned owner' : 'Unassigned')
  return (
    <div data-tour="forms-list" className="space-y-6">
      <Card className="p-5 sm:p-7">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">{applications ? 'Applications' : 'Existing forms'}</h2>
            <p className="mt-1 max-w-prose text-sm text-muted">
              {applications
                ? 'Track application preparation and supporting evidence. Readiness does not mean submitted or approved.'
                : 'Work across jurisdictions before a requirements baseline exists. Readiness is internal preparation status.'}
            </p>
          </div>
          <span className="text-sm text-muted">
            {cases.data?.total ?? '—'} {applications ? 'applications' : 'forms'}
          </span>
        </div>
        <div className={`mt-6 grid gap-3 sm:grid-cols-2 ${kindScope ? 'xl:grid-cols-3' : 'xl:grid-cols-4'}`}>
          <label className="text-sm font-medium">
            Search name
            <input
              type="search"
              className="mt-1 w-full px-3 py-2"
              value={q}
              onChange={(event) => {
                setQ(event.target.value)
                setPage(0)
              }}
            />
          </label>
          {!kindScope && <label className="text-sm font-medium">
            Kind
            <select
              className="mt-1 w-full px-3 py-2"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value)
                setPage(0)
              }}
            >
              <option value="">All kinds</option>
              {PREPARATION_KINDS.map((value) => (
                <option key={value} value={value}>
                  {preparationLabel(value)}
                </option>
              ))}
            </select>
          </label>}
          <label className="text-sm font-medium">
            Status
            <select
              className="mt-1 w-full px-3 py-2"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value)
                setPage(0)
              }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
            </select>
          </label>
          {!fixedJurisdiction && <label className="text-sm font-medium">
            Jurisdiction
            <select
              className="mt-1 w-full px-3 py-2"
              value={jurisdictionId}
              onChange={(event) => {
                setJurisdictionId(event.target.value)
                setPage(0)
              }}
            >
              <option value="">All jurisdictions</option>
              {jurisdictions.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>}
        </div>
        {cases.isLoading ? (
          <p role="status" className="mt-6 text-muted">
            Loading {applications ? 'applications' : 'forms'}…
          </p>
        ) : cases.isError ? (
          <p role="alert" className="mt-6 text-danger">
            {applications ? 'Applications' : 'Cases'} could not be loaded.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => void cases.refetch()}
            >
              Retry
            </button>
          </p>
        ) : !cases.data?.items.length ? (
          <p className="mt-6 text-muted">
            No {applications ? 'applications' : 'forms'} match these filters.
            {canManage && ' Create one from an saved blank form when you are ready.'}
          </p>
        ) : (
          <ul className="mt-6 divide-y divide-line">
            {cases.data.items.map((item) => (
              <CaseRow
                key={item.id}
                item={item}
                jurisdiction={lookupJurisdiction(item.jurisdiction_id)}
                owner={lookupOwner(item.owner_id)}
                project={
                  projects.find((project) => project.id === item.project_id)
                    ?.name
                }
                onOpen={() => onOpen(item.id, item.kind)}
              />
            ))}
          </ul>
        )}
        {cases.data && cases.data.total > 100 && (
          <div className="mt-5 flex items-center gap-3">
            <Button
              size="sm"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-muted">
              Page {page + 1} of {Math.ceil(cases.data.total / 100)}
            </span>
            <Button
              size="sm"
              disabled={(page + 1) * 100 >= cases.data.total}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </Card>
      {canManage && (
        <Card className="p-5 sm:p-7">
          <h2 className="text-lg font-semibold">{applications ? 'Create an application' : 'Create a form'}</h2>
          <p className="mt-1 text-sm text-muted">
            {fixedJurisdiction ? 'Choose a saved blank form for the current space. You can link a certification project if one exists.' : 'Choose an saved blank form and one active jurisdiction. You can link a certification project if one exists.'}
          </p>
          {!templates.isLoading && !templates.isError && !availableTemplates.length && (
            <p className="mt-4 text-sm text-muted">
              {applications ? 'Create an active licence application template to get started.' : 'Create an saved blank form to get started.'}{' '}
              {onTemplates && <button type="button" className="underline" onClick={onTemplates}>Open saved blank forms</button>}
            </p>
          )}
          <form className="mt-5 space-y-4" onSubmit={create}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium">Visibility<select className="mt-1 block w-full rounded-lg border border-line bg-surface p-2" value={visibility} onChange={(e) => setVisibility(e.target.value as Visibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className="text-xs text-muted">{visibilityDescriptions[visibility]} After creation, use “Who can access this?” to choose recipients.</span></label>
              <label className="text-sm font-medium">
                Saved blank form
                <select
                  required
                  className="mt-1 w-full px-3 py-2"
                  value={templateId}
                  onChange={(event) => {
                    const next = event.target.value
                    setTemplateId(next)
                    const template = templates.data?.items.find(
                      (item) => item.id === next,
                    )
                    if (template && !name) setName(template.name)
                  }}
                >
                  <option value="">Select an saved blank form</option>
                  {availableTemplates.map((template: PreparationTemplate) => (
                    <option key={template.id} value={template.id}>
                      {template.name} · {preparationLabel(template.kind)}
                    </option>
                  ))}
                </select>
              </label>
              {fixedJurisdiction ? <div><p className="text-sm font-medium">Jurisdiction</p><p className="mt-1 text-sm">{effectiveNewJurisdictionId ? lookupJurisdiction(effectiveNewJurisdictionId) : 'Select a space to continue'}</p><p className="mt-1 text-xs text-muted">Defined by your current space.</p></div> : (<label className="text-sm font-medium">
                Jurisdiction
                <select
                  required
                  className="mt-1 w-full px-3 py-2"
                  value={newJurisdictionId}
                  onChange={(event) => {
                    setNewJurisdictionId(event.target.value)
                    setProjectId('')
                  }}
                >
                  <option value="">Select a jurisdiction</option>
                  {jurisdictions
                    .filter((item) => item.active)
                    .map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </label>)}
              <label className="text-sm font-medium">
                {applications ? 'Application name' : 'Form name'}
                <input
                  required
                  maxLength={255}
                  className="mt-1 w-full px-3 py-2"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="text-sm font-medium">
                Owner (optional)
                <select
                  className="mt-1 w-full px-3 py-2"
                  value={ownerId}
                  onChange={(event) => setOwnerId(event.target.value)}
                >
                  <option value="">Unassigned</option>
                  {users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name || user.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium">
                Deadline (optional)
                <input
                  type="date"
                  className="mt-1 w-full px-3 py-2"
                  value={dueDate}
                  onChange={(event) => setDueDate(event.target.value)}
                />
              </label>
              <label className="text-sm font-medium">
                Certification project (optional)
                <select
                  className="mt-1 w-full px-3 py-2"
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  <option value="">No linked project</option>
                  {caseProjects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {templates.isError && (
              <p role="alert" className="text-sm text-danger">
                Templates could not be loaded.{' '}
                <button
                  type="button"
                  className="underline"
                  onClick={() => void templates.refetch()}
                >
                  Retry
                </button>
              </p>
            )}
            {error && (
              <p
                role="alert"
                className="rounded-lg bg-danger-soft p-3 text-sm text-danger"
              >
                {error}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              loading={busy}
              disabled={
                !availableTemplates.length ||
                !jurisdictions.some((item) => item.active) || (fixedJurisdiction && !effectiveNewJurisdictionId)
              }
            >
              {applications ? 'Create application' : 'Create form'}
            </Button>
          </form>
        </Card>
      )}
    </div>
  )
}

function CaseRow({
  item,
  jurisdiction,
  owner,
  project,
  onOpen,
}: {
  item: PreparationCase
  jurisdiction: string
  owner: string
  project?: string
  onOpen: () => void
}) {
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onOpen}
            className="text-left text-base font-semibold text-accent hover:underline"
          >
            {item.name}
          </button>
          <p className="mt-1 text-sm text-muted">
            {jurisdiction} · {preparationLabel(item.kind)} ·{' '}
            {item.status === 'archived' ? 'Archived' : 'Active'}
          </p>
          <p className="mt-1 text-sm text-muted">
            Owner: {owner} · Deadline: {item.due_date || 'None'}
            {project ? ` · Project: ${project}` : ''}
          </p>
        </div>
        <div className="text-right text-sm">
          <span
            className={
              item.readiness.ready
                ? 'font-semibold text-success'
                : 'font-semibold text-warning'
            }
          >
            {item.readiness.ready
              ? 'Ready'
              : `${item.readiness.blockers.length} blockers`}
          </span>
          <p className="mt-1 text-muted">
            {item.readiness.accepted_count}/{item.readiness.required_count}{' '}
            required accepted
          </p>
        </div>
      </div>
    </li>
  )
}
