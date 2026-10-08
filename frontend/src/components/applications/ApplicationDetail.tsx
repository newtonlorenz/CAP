import AccessPanel from '../access/AccessPanel'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { applicationsApi } from '../../api/applications'
import { getApiErrorMessage } from '../../api/errors'
import type { Jurisdiction, UserMention } from '../../types'
import { scopeLabels, statusLabels, type LicenceApplication } from '../../types/applications'
import { formatDate, formatDateTime } from '../../utils/dateFormat'
import Button from '../ui/Button'
import Card from '../ui/Card'
import EvidenceAttachments from '../preparation/EvidenceAttachments'
import ApplicationMetadataForm from './ApplicationMetadataForm'
import ComponentEditor from './ComponentEditor'
import LifecycleActions from './LifecycleActions'
import ReadinessIssues from './ReadinessIssues'
import { Followup, NewFollowup } from './Followups'

export default function ApplicationDetail({ item: incoming, users, jurisdictions, canManage: roleManage, canEdit: roleEdit, canApprove: roleApprove, onBack, onOpenCase, onSection, onLibrary, onReload, onSectionChange, navigation, initialAccessOpen = false, activeTab = 'applications' }: {
  item: LicenceApplication; users: UserMention[]; jurisdictions: Jurisdiction[]; canManage: boolean; canEdit: boolean; canApprove: boolean
  onBack: () => void; onOpenCase: (id: string, fieldKey?: string) => void; onSection?: (tab: 'forms' | 'approval', target?: string) => void; onLibrary: (tab: 'templates' | 'evidence') => void; onReload: () => void; onSectionChange?: (tab: string) => void; navigation?: ReactNode; initialAccessOpen?: boolean; activeTab?: string
}) {
  const canManage = incoming.access ? roleManage && incoming.access.permissions.includes('edit') : roleManage
  const canEdit = incoming.access ? roleEdit && incoming.access.permissions.includes('edit') : roleEdit
  const canApprove = incoming.access ? roleApprove && incoming.access.permissions.includes('approve') : roleApprove
  const canExport = !incoming.access || incoming.access.permissions.includes('export')
  const client = useQueryClient()
  const [item, setItem] = useState(incoming)
  const revision = useRef(item.revision)
  const writing = useRef(false)
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [dirtyEditors, setDirtyEditors] = useState<Record<string, boolean>>({})
  const dirty = Object.values(dirtyEditors).some(Boolean)
  const navigationGuarded = useDraftNavigationGuard(dirty || (busy && writing.current))
  const markDirty = useCallback((key: string, value: boolean) => setDirtyEditors((old) => old[key] === value ? old : ({ ...old, [key]: value })), [])
  const draft = item.status === 'draft'
  const canFollowup = item.status === 'follow_up' || draft
  const changedRemotely = revision.current !== incoming.revision
  useEffect(() => { if (incoming.revision === revision.current) setItem(incoming) }, [incoming])
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  const leave = (next: () => void, routeChange = true) => { if ((routeChange && navigationGuarded) || !dirty || window.confirm('Discard unsaved application edits and reload?')) next() }
  const write = async (operation: (expected: number) => Promise<LicenceApplication>): Promise<boolean> => {
    if (writing.current || conflict) return false
    writing.current = true
    setBusy(true); setError(''); setNotice('')
    try {
      const saved = await operation(revision.current)
      if (!active.current) return false
      await client.cancelQueries({ queryKey: ['applications', 'item', item.id], exact: true })
      if (!active.current) return false
      revision.current = saved.revision
      setItem(saved)
      client.setQueryData(['applications', 'item', item.id], saved)
      void client.invalidateQueries({ queryKey: ['applications', 'list'] })
      void client.invalidateQueries({ queryKey: ['preparation', 'cases'] })
      setNotice('Changes saved.')
      return true
    } catch (caught) {
      const collided = axios.isAxiosError(caught) && caught.response?.status === 409
      setConflict(collided)
      setError(getApiErrorMessage(caught, 'The application could not be updated. Your edits are still here.'))
      return false
    } finally { writing.current = false; setBusy(false) }
  }
  const removePlaceholder = async (componentId: string) => {
    const component = item.components.find(entry => entry.id === componentId)
    if (!component || dirty || busy || conflict) return
    if (!window.confirm(`Remove "${component.name}" from this draft pack? This changes the pack contents and readiness checks.`)) return
    const ok = await write(expected => applicationsApi.removeComponent(item.id, componentId, expected))
    if (ok && editing === componentId) {
      markDirty(`component-${componentId}`, false)
      setEditing(null)
    }
  }
  const download = async (snapshotId: string, version: number) => {
    setError(''); setBusy(true)
    try { await applicationsApi.download(item.id, snapshotId, `${item.name.replace(/[^a-z0-9_-]+/gi, '_')}-v${version}.zip`) }
    catch (caught) { setError(getApiErrorMessage(caught, 'Pack download failed. Try again.')) }
    finally { setBusy(false) }
  }
  if (incoming.summary_only || (incoming.access && !incoming.access.permissions.includes('view'))) return <Card className="space-y-4 p-5"><Button onClick={onBack}>All applications</Button><h1 className="text-2xl font-semibold">{incoming.name}</h1><p>{statusLabels[incoming.status]} · Due {formatDate(incoming.due_date)}</p><p className="text-muted">You have summary access. Application details, documents and exports are restricted.</p></Card>
  const unconfigured = item.components.filter(component => component.included && component.kind !== 'document' && !component.case_id).length
  const openQueries = item.followups.filter(query => query.status === 'open').length
  const setupNeeded = item.components.length === 0 || unconfigured > 0
  const continueTab = item.status === 'completed' ? 'history' : draft && (setupNeeded || !item.readiness.ready) ? 'forms' : 'approval'
  const continueLabel = continueTab === 'history' ? 'View application history' : continueTab === 'forms' ? 'Continue to forms and documents' : 'Continue to approval and submission'
  const stage = item.status === 'draft' ? setupNeeded ? 'Set up the pack' : 'Complete forms and documents'
    : item.status === 'in_review' ? 'Internal approval'
    : item.status === 'approved' ? 'Record authority submission'
    : item.status === 'submitted' || item.status === 'follow_up' ? 'Authority follow-up' : 'Outcome recorded'
  const nextStep = item.status === 'draft' ? setupNeeded ? 'Add the required forms and documents, then set up each form’s questions. You can start without an approved requirement set.'
    : item.readiness.ready ? 'The required forms and documents are ready. Send the pack for internal review using the controls below.'
    : `Complete and review the outstanding forms and documents. ${item.readiness.ready_count} of ${item.readiness.required_count} required forms and documents are ready.`
    : item.status === 'in_review' ? item.readiness.ready ? 'An approver checks the pack and freezes an approved version. This is internal approval.' : 'Resolve the readiness issues before approving this pack.'
    : item.status === 'approved' ? item.readiness.ready ? 'Download the approved version, submit it through the authority’s own channel, then record the actual submission date and reference.' : 'Refresh readiness and resolve the issues before recording submission.'
    : item.status === 'submitted' ? 'Start follow-up to record authority questions and responses, or record the actual outcome when no queries remain.'
    : item.status === 'follow_up' ? openQueries ? `Answer and resolve ${openQueries} open authority ${openQueries === 1 ? 'query' : 'queries'} before recording the final outcome.` : 'Record the authority’s actual decision, reference and any conditions.'
    : 'The application record is complete. The recorded outcome below states the authority’s decision; completion alone does not mean a licence was issued.'
  const openSection = (tab: 'forms' | 'approval', target?: string) => {
    if (onSection) onSection(tab, target)
    else onSectionChange?.(tab)
  }
  const openComponent = (componentId: string) => {
    const component = item.components.find(entry => entry.id === componentId)
    if (component?.case_id && component.included) leave(() => onOpenCase(component.case_id!))
    else openSection('forms', `application-component-${componentId}`)
  }
  const nextComponent = item.components.find(component => component.included && !component.ready)
  const continueWork = () => {
    if (continueTab === 'history' && onSectionChange) {
      onSectionChange('history')
    } else if (item.status === 'draft' && !item.readiness.ready) {
      if (nextComponent) openComponent(nextComponent.id)
      else openSection('forms', 'application-components')
    } else openSection('approval', 'pack-readiness')
  }
  const readinessIssues = (blockers: typeof item.readiness.blockers) => <ReadinessIssues blockers={blockers} components={item.components} users={users}
    onOpenCase={(caseId, fieldKey) => leave(() => onOpenCase(caseId, fieldKey))}
    onOpenComponent={openComponent}
    onReviewPack={(code) => code === 'invalid_evidence' ? leave(() => onLibrary('evidence')) : openSection(code === 'empty_pack' ? 'forms' : 'approval', code === 'open_followup' ? 'authority-queries' : code === 'empty_pack' ? 'application-components' : 'pack-readiness')} />
  return <div className="space-y-6">
    <div data-tour="licence-heading" className="flex flex-wrap items-start justify-between gap-4"><div className="min-w-0"><Button variant="ghost" size="sm" onClick={() => leave(onBack)}>← All applications</Button><h1 className="mt-2 break-words text-2xl font-semibold">{item.name}</h1><p className="mt-2 text-sm text-muted">{jurisdictions.find((j) => j.id === item.jurisdiction_id)?.name || 'Jurisdiction unavailable'} · {scopeLabels[item.scope]}</p></div><div className="flex flex-wrap items-center gap-3"><span className="rounded-full bg-info-soft px-3 py-1 text-sm text-info">{statusLabels[item.status]}</span><Button size="sm" disabled={busy} onClick={() => leave(onReload, false)}>Refresh readiness</Button></div></div>
    {navigation}
    <section hidden={activeTab !== 'applications'} aria-labelledby="application-next-step" className="space-y-2 border-y border-line py-4">
      <h3 id="application-next-step" className="text-lg font-semibold">{stage}</h3>
      <p className="max-w-prose text-sm text-muted">{nextStep}</p>
      <Button variant="primary" size="sm" onClick={continueWork}>{item.status === 'draft' && !item.readiness.ready && nextComponent?.case_id ? `Continue ${nextComponent.name}` : continueLabel}</Button>
      {item.snapshots.length > 0 && <p className="text-xs text-muted">To amend the pack, return it to draft and obtain a new internal approval. Earlier pack versions and submission records remain in history.</p>}
    </section>
    {error && <p role="alert" className="rounded-lg bg-danger-soft p-4 text-danger">{error}</p>}
    {(conflict || changedRemotely) && <div role="alert" className="rounded-lg bg-warning-soft p-4 text-warning">This application has changed or needs a fresh readiness check. Your edits have been retained. <Button size="sm" onClick={() => leave(onReload, false)}>Reload latest application</Button></div>}
    {busy && <p role="status" className="text-sm text-muted">Saving…</p>}
    {notice && !error && <p role="status" className="text-sm text-success">{notice}</p>}
    {activeTab === 'applications' && item.access?.permissions.includes('manage_access') && <AccessPanel type="application" id={item.id} initialOpen={initialAccessOpen} />}
    <section data-tour="licence-components" hidden={activeTab !== 'forms'} id="application-components" tabIndex={-1}><Card className="space-y-5 p-5 sm:p-7"><div><h3 className="text-lg font-semibold">Forms and documents</h3><p className="mt-1 text-sm text-muted">Set up each form’s questions and attach its original source. Complete answers in the form workspace.</p></div>
      {!draft && <p className="rounded-lg bg-info-soft p-3 text-sm text-info">Return the application to draft to change its composition. Approved snapshots retain the exact earlier content.</p>}
      {item.components.length === 0 && <p className="text-sm text-muted">No forms or documents yet. Add an annex, application form or supporting document below.</p>}
      <div className="space-y-4">{item.components.map((component) => <article key={component.id} id={`application-component-${component.id}`} tabIndex={-1} className="space-y-3 border-b border-line py-4 last:border-0">
        <div className="flex flex-wrap justify-between gap-3"><div><h4 className="font-semibold">{component.name}</h4><p className="mt-1 text-xs text-muted">{component.kind === 'annex' ? 'Supplementary form' : component.kind === 'form' ? 'Application form' : 'Supporting document'} · {component.required ? 'Required' : 'Optional'} · {component.included ? 'Included in pack' : 'Excluded from pack'} · {component.ready ? 'Ready' : 'Incomplete'}</p><p className="mt-1 text-xs text-muted">{users.find((u) => u.id === component.owner_id)?.full_name || 'Unassigned'} · Due {formatDate(component.due_date)}</p></div><div className="flex flex-wrap items-start gap-2">{component.case_id && <Button variant="primary" size="sm" onClick={() => leave(() => onOpenCase(component.case_id!))}>Open {component.name}</Button>}{canManage && draft && component.kind === 'annex' && component.case_id && <Button size="sm" disabled={busy || conflict} onClick={() => { const name = window.prompt('Name for the next blank annex', component.name); if (name?.trim()) void write((expected_revision) => applicationsApi.duplicateComponent(item.id, component.id, { expected_revision, name: name.trim() })) }}>Add another blank</Button>}{canManage && draft && <Button size="sm" disabled={busy || conflict} onClick={() => { if (!editing || !dirtyEditors[`component-${editing}`] || window.confirm('Discard unsaved form or document edits?')) { if (editing) markDirty(`component-${editing}`, false); setEditing(editing === component.id ? null : component.id) } }}>{editing === component.id ? 'Close editor' : (!component.case_id && component.kind !== 'document' ? `Set up ${component.name}` : `Edit ${component.name}`)}</Button>}{canManage && draft && !component.case_id && !component.evidence_id && <Button size="sm" aria-label={`Remove ${component.name}`} title={dirty ? 'Save or discard unsaved edits before removing an item.' : undefined} disabled={busy || conflict || dirty} onClick={() => void removePlaceholder(component.id)}>Remove</Button>}</div></div>
        {!component.case_id && component.kind !== 'document' && <p className="text-sm text-muted">{component.form_field_count ? `${component.form_field_count} setup questions` : 'Checklist item only — set up its questions or keep it for later.'}</p>}
        {component.blockers.length > 0 && <details><summary className="cursor-pointer text-xs font-medium text-warning">{component.blockers.length} readiness {component.blockers.length === 1 ? 'issue' : 'issues'}</summary>{readinessIssues(component.blockers)}</details>}
        {component.evidence_id && <EvidenceAttachments ids={[component.evidence_id]} />}
        {editing === component.id && canManage && draft && <ComponentEditor initial={component} onDirtyChange={(value) => markDirty(`component-${component.id}`, value)} jurisdictionId={item.jurisdiction_id} users={users} busy={busy || conflict} onLibrary={onLibrary} onSave={async (body) => { const ok = await write((expected_revision) => applicationsApi.updateComponent(item.id, component.id, { ...body, expected_revision })); if (ok) { markDirty(`component-${component.id}`, false); setEditing(null) }; return ok }} />}
      </article>)}</div>
      {canManage && draft && <details open={item.components.length === 0 ? true : undefined}><summary className="cursor-pointer font-semibold text-accent">Add form or document</summary><div className="mt-4"><ComponentEditor onDirtyChange={(value) => markDirty('new-component', value)} jurisdictionId={item.jurisdiction_id} users={users} busy={busy || conflict} onLibrary={onLibrary} onSave={(body) => write((expected_revision) => applicationsApi.addComponent(item.id, { ...body, expected_revision }))} /></div></details>}
    </Card></section>
    <section data-tour="licence-readiness" hidden={activeTab !== 'approval'} id="pack-readiness" tabIndex={-1}><Card className="space-y-4 p-5 sm:p-7">
      <div className="flex flex-wrap justify-between gap-3"><div><h3 className="text-lg font-semibold">Pack readiness</h3><p className="mt-1 text-sm text-muted">{item.readiness.ready_count} of {item.readiness.required_count} required items ready</p></div><span className={`self-start rounded-full px-3 py-1 text-sm ${item.readiness.ready ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'}`}>{item.readiness.ready ? 'Ready for internal approval' : 'Preparation incomplete'}</span></div>
      {item.readiness.blockers.length > 0 && <div><p className="text-sm font-medium">{item.readiness.blockers.length} readiness issues</p>{readinessIssues(item.readiness.blockers)}</div>}
      <p className="text-xs text-muted">Readiness covers the selected forms and documents. Authority submission and approval are recorded separately.</p>
      {(canManage || canApprove) && <LifecycleActions status={item.status} ready={item.readiness.ready} busy={busy || conflict} canManage={canManage} canApprove={canApprove} hasOpenQueries={item.followups.some((f) => f.status === 'open')} onAction={(action, body) => { if (dirty) { setError('Save or discard your unsaved pack, form and query edits before changing stage.'); return Promise.resolve(false) } return write((expected_revision) => applicationsApi.action(item.id, action, { ...body, expected_revision })) }} />}
      {item.status === 'in_review' && canManage && !canApprove && <p className="text-sm text-muted">Someone with approval access must approve this pack.</p>}
      {item.outcome && <div className="rounded-lg bg-subtle p-4"><h4 className="font-semibold">Recorded outcome</h4><p className="mt-2 whitespace-pre-wrap text-sm">{item.outcome}</p></div>}
    </Card></section>
    <div data-tour="licence-metadata" hidden={activeTab !== 'applications'}><Card className="p-5 sm:p-7"><details><summary className="cursor-pointer font-semibold">Application details <span className="font-normal text-sm text-muted">· {item.applicant || 'Applicant not set'} · Due {formatDate(item.due_date)}</span></summary><div className="mt-5">{canManage && draft ? <ApplicationMetadataForm initial={item} onDirtyChange={(value) => markDirty('metadata', value)} jurisdictions={jurisdictions} users={users} busy={busy || conflict} onSave={({ jurisdiction_id: _jurisdiction, ...body }) => write((expected_revision) => applicationsApi.update(item.id, { ...body, expected_revision }))} /> : <dl className="grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-muted">Applicant</dt><dd>{item.applicant || 'Not set'}</dd></div><div><dt className="text-muted">Authority</dt><dd>{item.authority || 'Not set'}</dd></div><div><dt className="text-muted">Owner</dt><dd>{users.find((u) => u.id === item.owner_id)?.full_name || 'Unassigned'}</dd></div><div><dt className="text-muted">Scope and accompanying information</dt><dd className="whitespace-pre-wrap">{item.description || 'None'}</dd></div></dl>}</div></details></Card></div>
    <section data-tour="licence-queries" hidden={activeTab !== 'approval'} id="authority-queries" tabIndex={-1}><Card className="space-y-5 p-5 sm:p-7"><h3 className="text-lg font-semibold">Authority queries and responses</h3>{item.followups.length === 0 && <p className="text-sm text-muted">No authority queries recorded.</p>}{item.followups.map((followup) => <Followup key={followup.id} onDirtyChange={(value) => markDirty(`followup-${followup.id}`, value)} item={followup} users={users} canEdit={canEdit && canFollowup} canManage={canManage && canFollowup} busy={busy || conflict} onSave={(body) => write((expected_revision) => applicationsApi.updateFollowup(item.id, followup.id, { ...body, expected_revision }))} />)}{canManage && canFollowup && <details><summary className="cursor-pointer font-semibold text-accent">Add authority query</summary><div className="mt-4"><NewFollowup onDirtyChange={(value) => markDirty('new-query', value)} users={users} busy={busy || conflict} onSave={(body) => write((expected_revision) => applicationsApi.addFollowup(item.id, { ...body, expected_revision }))} /></div></details>}</Card></section>
    {activeTab === 'approval' && <Card data-tour="licence-snapshots" className="space-y-4 p-5 sm:p-7"><h3 className="text-lg font-semibold">Approved packs and submissions</h3><p className="text-sm text-muted">Each approval preserves a separate version of the forms and evidence. Downloads contain that approved version.</p>{item.snapshots.length === 0 && <p className="text-sm text-muted">No approved packs yet.</p>}{item.snapshots.map((snapshot) => <article key={snapshot.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-line p-4"><div><h4 className="font-semibold">Pack version {snapshot.version}</h4><p className="mt-1 text-sm text-muted">Approved {formatDateTime(snapshot.approved_at)}</p><p className="mt-1 text-sm">{snapshot.submitted_at ? `Submitted ${formatDateTime(snapshot.submitted_at)} · ${snapshot.reference}` : 'Submission not recorded'}</p>{snapshot.notes && <p className="mt-2 whitespace-pre-wrap text-sm text-muted">{snapshot.notes}</p>}</div><Button disabled={busy || !canExport} onClick={() => void download(snapshot.id, snapshot.version)}>Download version {snapshot.version}</Button></article>)}</Card>}
    {activeTab === 'history' && <Card data-tour="licence-history" className="p-5 sm:p-7"><h3 className="text-lg font-semibold">Activity history</h3><ol className="mt-4 divide-y divide-line">{item.history.map((event) => <li key={event.id} className="py-3 text-sm"><p className="font-medium">{event.action.replace(/_/g, ' ')} · {event.user_name || 'User'}</p><p className="mt-1 text-xs text-muted">{formatDateTime(event.timestamp)}</p>{Object.entries(event.details || {}).filter(([, value]) => typeof value === 'string' && Boolean(value)).map(([key, value]) => <p key={key} className="mt-1 whitespace-pre-wrap text-xs text-muted">{key.replace(/_/g, ' ')}: {String(value)}</p>)}</li>)}</ol></Card>}
  </div>
}
