import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import { applicationsApi } from '../api/applications'
import { preparationApi } from '../api/preparation'
import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import type { CertificationProject, PaginatedResponse, UserMention } from '../types'
import { scopeLabels, statusLabels, type GuidedApplicationInput } from '../types/applications'
import { formatDate } from '../utils/dateFormat'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import SectionNav from '../components/ui/SectionNav'
import CaseDetail from '../components/preparation/CaseDetail'
import CasePortfolio from '../components/preparation/CasePortfolio'
import TemplateBuilder from '../components/preparation/TemplateBuilder'
import { EvidenceLibrary } from '../components/preparation/EvidenceLibrary'
import ApplicationDetail from '../components/applications/ApplicationDetail'
import NewPackWizard from '../components/applications/NewPackWizard'
import { Field, inputClass } from '../components/applications/Fields'

const tabs = [{ id: 'applications', label: 'Applications' }, { id: 'forms', label: 'Existing forms' }, { id: 'templates', label: 'Templates' }, { id: 'evidence', label: 'Evidence library' }, { id: 'teams', label: 'Access teams' }]
const workspaceTabs = [{ id: 'applications', label: 'Overview' }, { id: 'forms', label: 'Forms and documents' }, { id: 'approval', label: 'Approval and submission' }, { id: 'history', label: 'History' }]
export default function Applications() {
  const { user } = useAuth()
  const { jurisdictionId, setJurisdictionId, jurisdictions, jurisdictionById, error: jurisdictionError, retry } = useJurisdiction()
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const goTo = useNavigate()
  const client = useQueryClient()
  const id = params.get('application')
  const caseId = params.get('case')
  const fieldKey = params.get('field')
  const returnTab = params.get('returnTab') === 'approval' ? 'approval' : params.get('returnTab') === 'applications' ? 'applications' : 'forms'
  const tab = [...tabs, ...workspaceTabs].some((t) => t.id === params.get('tab')) ? params.get('tab')! : 'applications'
  const detailTab = !params.has('tab') && ['#authority-queries', '#pack-readiness'].includes(location.hash) ? 'approval' : !params.has('tab') && location.hash === '#application-components' ? 'forms' : tab
  const q = params.get('q') || ''
  const status = params.get('status') || ''
  const scope = params.get('scope') || ''
  const isCreating = params.get('create') === '1' && !id && !caseId && tab === 'applications'
  const previousJurisdiction = useRef(jurisdictionId)
  const page = previousJurisdiction.current !== jurisdictionId ? 0 : Math.max(0, Number(params.get('page')) || 0)
  useEffect(() => {
    if (previousJurisdiction.current === jurisdictionId) return
    previousJurisdiction.current = jurisdictionId
    setParams((current) => { const next = new URLSearchParams(current); next.delete('page'); return next }, { replace: true })
  }, [jurisdictionId, setParams])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const canManage = user?.role === 'admin' || user?.role === 'manager'
  const canApprove = user?.role === 'admin' || user?.role === 'approver'
  const canEdit = canManage || user?.role === 'contributor'
  const listParams = new URLSearchParams({ skip: String(page * 50), limit: '50' })
  if (q) listParams.set('q', q)
  if (status) listParams.set('status', status)
  if (scope) listParams.set('scope', scope)
  if (jurisdictionId) listParams.set('jurisdiction_id', jurisdictionId)
  const list = useQuery({ queryKey: ['applications', 'list', listParams.toString()], queryFn: () => applicationsApi.list(listParams), enabled: Boolean(jurisdictionId) && !id && !caseId && tab === 'applications' && !isCreating })
  const application = useQuery({ queryKey: ['applications', 'item', id], queryFn: () => applicationsApi.get(id!), enabled: Boolean(id) })
  const caseQuery = useQuery({ queryKey: ['preparation', 'case', caseId], queryFn: () => preparationApi.getCase(caseId!), enabled: Boolean(caseId) })
  const resourceJurisdiction = caseId ? caseQuery.data?.jurisdiction_id : application.data?.jurisdiction_id
  useEffect(() => {
    if (resourceJurisdiction && resourceJurisdiction !== jurisdictionId) setJurisdictionId(resourceJurisdiction)
  }, [resourceJurisdiction, jurisdictionId, setJurisdictionId])
  const users = useQuery({ queryKey: ['preparation', 'users'], queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data, staleTime: 300000 })
  const projects = useQuery({ queryKey: ['preparation', 'projects'], queryFn: async () => (await api.get<PaginatedResponse<CertificationProject>>('/certification-projects?limit=1000')).data, enabled: Boolean(caseId) || tab === 'forms', staleTime: 300000 })
  const navigate = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) }
    if ('tab' in changes && location.hash) goTo({ pathname: location.pathname, search: `?${next.toString()}`, hash: '' })
    else setParams(next)
    if (id && changes.tab === null) void application.refetch()
  }
  const open = (applicationId: string, chooseAccess = false) => navigate({ application: applicationId, case: null, tab: null, create: null, access: chooseAccess ? applicationId : null })
  const create = async (body: GuidedApplicationInput) => {
    setBusy(true); setError('')
    try { const created = await applicationsApi.guidedCreate(body); client.setQueryData(['applications', 'item', created.id], created); void client.invalidateQueries({ queryKey: ['applications', 'list'] }); open(created.id, body.visibility !== 'organisation'); return true }
    catch (caught) { setError(getApiErrorMessage(caught, 'The application could not be created. Check the details and try again.')); return false }
    finally { setBusy(false) }
  }
  const previousCase = useRef(caseId)
  const { refetch: refreshApplication } = application
  useEffect(() => {
    if (previousCase.current && !caseId && id) void refreshApplication()
    previousCase.current = caseId
  }, [caseId, id, refreshApplication])
  const backFromCase = () => navigate({ case: null, field: null, returnTab: null, tab: id ? returnTab : 'forms' })
  const libraryHref = (section: 'templates' | 'evidence') => {
    const query = new URLSearchParams({ section, returnTo: id ? `/licence-applications?application=${encodeURIComponent(id)}` : '/licence-applications' })
    if (section === 'templates') query.set('kind', 'licence_application')
    return `/library?${query}`
  }
  useEffect(() => {
    if (caseId || !application.data || !location.hash) return
    const target = document.getElementById(location.hash.slice(1))
    if (target && !target.closest('[hidden]')) { target.scrollIntoView?.({ block: 'start' }); target.focus() }
  }, [caseId, application.data, detailTab, location.hash])
  // Keep bookmarked application-library URLs working while giving shared materials one home.
  if (!caseId && (tab === 'teams' || (!id && (tab === 'templates' || tab === 'evidence')))) return <Navigate replace to={tab === 'teams' ? '/access-teams' : libraryHref(tab as 'templates' | 'evidence')} />
  if (isCreating) return <div data-tour="licence-create" className="application-workspace space-y-6 pb-10">
    <header><h1 className="text-3xl font-semibold">New licence pack</h1><p className="mt-2 max-w-prose text-sm text-muted">Review the market checklist, then choose the contents, owners and access for this application.</p></header>
    <Button disabled={busy} onClick={() => { setError(''); navigate({ create: null }) }}>Cancel and return to applications</Button>
    {!canManage ? <p role="alert">Only managers and administrators can create licence packs.</p> : !jurisdictionId ? <p role="alert">Select a jurisdiction before starting a licence pack.</p> : <>
      {jurisdictionError && <p role="alert" className="text-warning">{jurisdictionError} <button type="button" className="underline" onClick={retry}>Retry</button></p>}
      {users.isError && <p role="alert" className="text-warning">Owner names could not be loaded. <Button onClick={() => void users.refetch()}>Retry</Button></p>}
      {error && <p role="alert" className="text-danger">{error}</p>}
      <Card className="p-5 sm:p-7"><NewPackWizard key={`${user?.id}-${jurisdictionId}`} jurisdictionId={jurisdictionId} jurisdiction={jurisdictions.find((entry) => entry.id === jurisdictionId)} userId={user?.id || ''} users={users.data?.items || []} busy={busy} onCreate={create} /></Card>
    </>}
  </div>
  return <div className="application-workspace space-y-6 pb-10">
    {!id && !caseId && <header><h1 className="text-3xl font-semibold">Licence packs</h1><p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">Prepare the forms and documents, approve the pack and record its submission.</p></header>}
    {jurisdictionError && <p role="alert" className="text-warning">{jurisdictionError} <button type="button" className="underline" onClick={retry}>Retry</button></p>}
    {!caseId && !id && canManage && <div className="flex flex-wrap items-center gap-4"><Button variant="primary" disabled={!jurisdictionId} onClick={() => navigate({ create: '1', tab: null })}>New licence pack</Button><Link to="/market-setup" className="text-sm font-semibold text-accent underline">Market setup</Link></div>}
    {id && !caseId && (tab === 'templates' || tab === 'evidence') && <Button onClick={() => navigate({ tab: null })}>← Return to pack</Button>}
    {(users.isError || projects.isError) && <p role="alert" className="text-sm text-warning">Some owner or project names could not be loaded. <button type="button" className="underline" onClick={() => { if (users.isError) void users.refetch(); if (projects.isError) void projects.refetch() }}>Retry</button></p>}
    {caseId ? (id && application.isLoading) || caseQuery.isLoading ? <p role="status">Loading form…</p> : caseQuery.isError || (id && application.isError) ? <p role="alert">Form could not be loaded. <Button onClick={() => { void caseQuery.refetch(); if (id) void application.refetch() }}>Retry</Button><Button onClick={backFromCase}>Return</Button></p> : caseQuery.data ? id && !application.data?.components?.some(component => component.case_id === caseId) ? <p role="alert">This form is not available in this pack. <Button onClick={backFromCase}>Return to pack</Button></p> : (!id && caseQuery.data.kind !== 'licence_application') ? <p role="alert">This form is available in Existing forms. <Link className="underline" to={`/preparation?case=${encodeURIComponent(caseId)}`}>Open form</Link></p> : <CaseDetail key={caseId} pack={application.data} onOpenCase={(formId) => navigate({ case: formId, field: null })} onPackSection={(section) => navigate({ case: null, field: null, tab: section })} headingLevel={id ? 2 : 1} item={caseQuery.data} canEdit={canEdit && (!id || application.data?.status === 'draft')} canManage={canManage && (!id || application.data?.status === 'draft')} users={users.data?.items || []} projects={projects.data?.items || []} jurisdictionName={(key) => jurisdictionById[key]?.name || 'Jurisdiction unavailable'} initialFieldKey={fieldKey || undefined} backLabel={id ? `Return to pack${application.data?.name ? ` · ${application.data.name}` : ''}` : 'Existing forms'} onBack={backFromCase} /> : null : <>
      {id && <div hidden={tab === 'templates' || tab === 'evidence'}>{application.isLoading ? <p role="status">Loading application…</p> : application.isError ? <p role="alert">Application could not be loaded. <Button onClick={() => void application.refetch()}>Retry</Button><Button onClick={() => navigate({ application: null })}>All applications</Button></p> : application.data && <ApplicationDetail key={`${id}-${reloadKey}`} item={application.data} users={users.data?.items || []} jurisdictions={jurisdictions} canManage={canManage} canEdit={canEdit} canApprove={canApprove} activeTab={detailTab} onSectionChange={(value) => navigate({ tab: value })} navigation={<SectionNav label="Licence pack sections" items={workspaceTabs} value={detailTab} onChange={(value) => navigate({ tab: value === 'applications' ? null : value })} />} initialAccessOpen={params.get('access') === id} onBack={() => navigate({ application: null, access: null, tab: null })} onOpenCase={(formId, field) => navigate({ case: formId, field: field || null, returnTab: detailTab, tab: null })} onSection={(section, target) => { const next = new URLSearchParams(params); next.set('tab', section); goTo({ pathname: location.pathname, search: `?${next}`, hash: target ? `#${target}` : '' }) }} onLibrary={(section) => navigate({ tab: section })} onReload={() => { void application.refetch().then((result) => { if (result.isSuccess) setReloadKey((key) => key + 1) }) }} />}</div>}
      {id && (tab === 'templates' || tab === 'evidence') && <section className="space-y-4" aria-label="Reusable forms and evidence"><h2 className="text-xl font-semibold">{tab === 'templates' ? 'Reusable blank forms' : 'Reusable evidence'}</h2><p className="max-w-prose text-sm text-muted">These shared materials are available across your workspace. Your licence pack draft is kept while you work here.</p>{tab === 'templates' ? <TemplateBuilder jurisdictionId={resourceJurisdiction || jurisdictionId || undefined} canManage={canManage} kindScope="licence_application" /> : <EvidenceLibrary canEdit={canEdit} />}</section>}
      {!id && tab === 'applications' && <>
        <Card data-tour="licence-list" className="space-y-5 p-5 sm:p-7"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Applications</h2><span className="text-sm text-muted">{list.data?.total ?? '—'} total</span></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Search applications"><input type="search" className={inputClass} value={q} onChange={(e) => navigate({ q: e.target.value, page: null })} /></Field>
          <Field label="Stage"><select className={inputClass} value={status} onChange={(e) => navigate({ status: e.target.value, page: null })}><option value="">All stages</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="Scope"><select className={inputClass} value={scope} onChange={(e) => navigate({ scope: e.target.value, page: null })}><option value="">All scopes</option>{Object.entries(scopeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>

        </div>
        {list.isLoading ? <p role="status">Loading applications…</p> : list.isError ? <p role="alert">Applications could not be loaded. <Button onClick={() => void list.refetch()}>Retry</Button></p> : list.data?.items.length ? <ul className="divide-y divide-line">{list.data.items.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div><button type="button" className="text-left font-semibold text-accent underline" onClick={() => open(item.id)}>{item.name}</button><p className="mt-1 text-sm text-muted">{!item.summary_only && <>{scopeLabels[item.scope]} · {jurisdictionById[item.jurisdiction_id]?.name || 'Jurisdiction unavailable'} · </>}{statusLabels[item.status]} · Due {formatDate(item.due_date)}</p>{!item.summary_only && <p className="mt-1 text-xs text-muted">{item.readiness?.ready_count}/{item.readiness?.required_count} required items ready</p>}</div><Button size="sm" onClick={() => open(item.id)}>Open pack</Button></li>)}</ul> : <p className="text-sm text-muted">No licence packs match. Start a new licence pack, or open existing forms.</p>}
        {list.data && list.data.total > 50 && <div className="flex items-center gap-3"><Button disabled={page === 0} onClick={() => navigate({ page: page > 1 ? String(page - 1) : null })}>Previous</Button><span className="text-sm">Page {page + 1}</span><Button disabled={(page + 1) * 50 >= list.data.total} onClick={() => navigate({ page: String(page + 1) })}>Next</Button></div>}
        </Card>

      </>}
      {!id && <details open={tab === 'forms'} onToggle={(event) => { if (event.currentTarget.open !== (tab === 'forms')) navigate({ tab: event.currentTarget.open ? 'forms' : null }) }} className="rounded-xl border border-line p-5"><summary className="cursor-pointer font-semibold text-accent">Existing forms</summary>{tab === 'forms' && <div className="mt-5"><CasePortfolio kindScope="licence_application" spaceJurisdictionId={jurisdictionId} jurisdictions={jurisdictions} users={users.data?.items || []} projects={projects.data?.items || []} canManage={canManage} onOpen={(formId) => navigate({ case: formId, application: null })} onTemplates={() => goTo(libraryHref('templates'))} /></div>}</details>}
    </>}
  </div>
}
