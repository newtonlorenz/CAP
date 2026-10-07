import AccessPanel from '../access/AccessPanel'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useInRouterContext } from 'react-router-dom'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import { useCaseWrites } from '../../hooks/preparation/useCaseWrites'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import type { CertificationProject, UserMention } from '../../types'
import type { PreparationField } from '../../types/preparation'
import Button from '../ui/Button'
import Card from '../ui/Card'
import CaseField from './CaseField'
import EvidenceAttachments from './EvidenceAttachments'
import PackContents from '../applications/PackContents'
import type { LicenceApplication } from '../../types/applications'
import './pilot.css'
import ReviewerAssignment from './ReviewerAssignment'
import PilotIcon from './PilotIcon'
import { visibilityLabels } from '../../types/access'
import type { PilotPreparationCase } from '../../types/pilotReview'

export default function CaseDetail({
  item,
  canEdit: roleEdit,
  canManage: roleManage,
  users,
  projects,
  jurisdictionName,
  onBack,
  backLabel = 'All forms',
  initialFieldKey,
  headingLevel = 2,
  pack,
  onOpenCase,
  onPackSection,
}: {
  item: PilotPreparationCase
  canEdit: boolean
  canManage: boolean
  users: UserMention[]
  projects: CertificationProject[]
  jurisdictionName: (id: string) => string
  onBack: () => void
  backLabel?: string
  initialFieldKey?: string
  headingLevel?: 1 | 2
  pack?: LicenceApplication
  onOpenCase?: (id: string) => void
  onPackSection?: (tab: string) => void
}) {
  const inRouter = useInRouterContext()
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  const canEdit = item.access ? roleEdit && item.access.permissions.includes('edit') : roleEdit
  const canManage = item.access ? roleManage && item.access.permissions.includes('edit') : roleManage
  const [name, setName] = useState(item.name)
  const [ownerId, setOwnerId] = useState(item.owner_id || '')
  const [dueDate, setDueDate] = useState(item.due_date || '')
  const [projectId, setProjectId] = useState(item.project_id || '')
  const [metadataDirty, setMetadataDirty] = useState(false)
  const focusedTarget = useRef('')
  const [question, setQuestion] = useState(() => { if (initialFieldKey) return initialFieldKey; try { const saved = sessionStorage.getItem(`cap-question:${item.id}`); if (saved && item.fields.some(field => field.key === saved)) return saved } catch { /* Optional position restoration. */ } return item.fields[0]?.key || '' })
  const [allQuestions, setAllQuestions] = useState(false)
  const questionIndex = Math.max(0, item.fields.findIndex(field => field.key === question))
  const answered = item.fields.filter(field => item.responses.some(response => response.field_key === field.key && (response.value !== null || response.not_applicable_reason || response.evidence_ids.length))).length
  const accepted = item.responses.filter(response => response.accepted_at).length
  const chooseQuestion = (key: string) => { try { sessionStorage.setItem(`cap-question:${item.id}`, key) } catch { /* Keep position in memory. */ } setQuestion(key); setAllQuestions(false); window.setTimeout(() => document.getElementById(`preparation-field-${key}`)?.focus(), 0) }
  useEffect(() => { if (initialFieldKey) setQuestion(initialFieldKey) }, [initialFieldKey])
  const writes = useCaseWrites(item.id, item.revision, metadataDirty)
  const dirtyFields = useRef(new Set<string>())
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const navigationGuarded = useDraftNavigationGuard(metadataDirty || writes.hasPendingDrafts || writes.isWriting)
  const archived = item.status === 'archived'
  const project = projects.find((candidate) => candidate.id === item.project_id)
  const ownerName =
    users.find((candidate) => candidate.id === item.owner_id)?.full_name ||
    (item.owner_id ? 'Assigned owner' : 'Unassigned')
  const caseProjects = projects.filter(
    (candidate) => candidate.jurisdiction_id === item.jurisdiction_id,
  )
  const sections = (item.fields || []).reduce<{ name: string; fields: PreparationField[] }[]>((groups, field) => {
    const name = field.section || 'General'
    const previous = groups[groups.length - 1]
    if (previous?.name === name) previous.fields.push(field)
    else groups.push({ name, fields: [field] })
    return groups
  }, [])
  useEffect(() => {
    if (metadataDirty) return
    setName(item.name)
    setOwnerId(item.owner_id || '')
    setDueDate(item.due_date || '')
    setProjectId(item.project_id || '')
  }, [item.name, item.owner_id, item.due_date, item.project_id, metadataDirty])
  useEffect(() => {
    if (!initialFieldKey || focusedTarget.current === `${item.id}:${initialFieldKey}` || !item.fields.some(field => field.key === initialFieldKey)) return
    const target = document.getElementById(`preparation-field-${initialFieldKey}`)
    // Select the question for keyboard users without scrolling its pack context away.
    target?.focus({ preventScroll: true })
    if (target) focusedTarget.current = `${item.id}:${initialFieldKey}`
  }, [item.id, initialFieldKey, item.fields])
  const saveMetadata = async (event: FormEvent) => {
    event.preventDefault()
    const ok = await writes.updateCase({
      name: name.trim(),
      owner_id: ownerId || null,
      due_date: dueDate || null,
      project_id: projectId || null,
    })
    if (ok) setMetadataDirty(false)
  }
  const canLeave = () =>
    navigationGuarded || !(metadataDirty || dirtyFields.current.size > 0 || writes.isWriting || writes.hasPendingDrafts) ||
    window.confirm('Some changes are still waiting to save. Leave this form? Unsaved edits will be lost; a save already in progress may still complete.')
  const backWithDraftGuard = () => {
    if (canLeave()) onBack()
  }
  useEffect(() => {
    if (navigationGuarded) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!metadataDirty && dirtyFields.current.size === 0 && !writes.isWriting && !writes.hasPendingDrafts) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [metadataDirty, writes.isWriting, writes.hasPendingDrafts, navigationGuarded])
  const exportZip = async () => {
    setDownloadBusy(true)
    setDownloadError('')
    try {
      await preparationApi.download(
        `cases/${item.id}/export`,
        `${item.name.replace(/[^a-z0-9_-]+/gi, '_')}-form.zip`,
      )
    } catch (caught) {
      setDownloadError(
        getApiErrorMessage(caught, 'ZIP export failed. Try again.'),
      )
    } finally {
      setDownloadBusy(false)
    }
  }
  if (item.summary_only || (item.access && !item.access.permissions.includes('view'))) return <Card className="space-y-4 p-5"><Button onClick={onBack}>{backLabel}</Button><Heading>{item.name}</Heading><p>You have summary access. Form details are restricted.</p></Card>
  return (
    <div className="pilot-case space-y-4">
      {pack && <header className="pilot-dossier-heading"><button type="button" onClick={backWithDraftGuard}>Licence Applications / {pack.name}</button><div className="flex flex-wrap items-center justify-between gap-3"><h1><span className="pilot-desktop-pack-name">{pack.name}</span><span className="pilot-mobile-form-name">{item.name}</span></h1>{pack.access && <span className="flex items-center gap-2 text-sm text-accent"><PilotIcon name="lock" size={19} />{visibilityLabels[pack.access.visibility]}</span>}</div><p>{pack.status === 'draft' ? 'Working draft' : 'Pack version'} v{pack.snapshots.length ? Math.max(...pack.snapshots.map(snapshot => snapshot.version)) + (pack.status === 'draft' ? 1 : 0) : 1} · {pack.status === 'draft' ? 'Preparing revision' : pack.status.replace(/_/g, ' ')}{pack.snapshots.length > 0 && <> · <button type="button" onClick={() => { if (canLeave()) onPackSection?.('history') }}>View approved v{Math.max(...pack.snapshots.map(snapshot => snapshot.version))}</button></>}</p><nav aria-label="Licence pack sections">{[['forms', 'Contents'], ['approval', 'Internal approval and submission'], ['history', 'History']].map(([key, label]) => <button key={key} type="button" aria-current={key === 'forms' ? 'page' : undefined} onClick={() => { if (canLeave()) onPackSection?.(key) }}>{label}</button>)}</nav></header>}
      <div className={pack ? "pilot-dossier" : ""}>
      {pack && <PackContents pack={pack} currentCaseId={item.id} onOpenCase={id => { if (canLeave()) onOpenCase?.(id) }} onOpenContents={() => { if (canLeave()) onPackSection?.('forms') }} />}
      <div className="pilot-case-body space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button variant="ghost" size="sm" onClick={backWithDraftGuard}>
            ← {backLabel}
          </Button>
          <Heading className="mt-1 text-xl font-semibold">{item.name}</Heading><p className="text-sm text-muted">Document owner: {ownerName}</p>
          <p className="mt-1 text-sm text-muted">
            {jurisdictionName(item.jurisdiction_id)} · {item.template_id ? `${item.template_name} v${item.template_revision}` : 'Questions saved with this form'} · {archived ? 'Archived' : 'Active'}
          </p>
        </div>
        <Button disabled={Boolean(item.access && !item.access.permissions.includes('export'))} onClick={() => void exportZip()} loading={downloadBusy}>
          Export form and evidence
        </Button>
      </div>
      {downloadError && (
        <p
          role="alert"
          className="rounded-lg bg-danger-soft p-3 text-sm text-danger"
        >
          {downloadError}
        </p>
      )}
      {pack?.components.some(component => component.case_id === item.id && !component.included) && <p role="status" className="rounded-md bg-info-soft p-3 text-sm text-info">This form is excluded from the current pack. Work saved here does not count towards this pack’s readiness.</p>}
      {archived && (
        <p
          role="status"
          className="rounded-lg bg-info-soft p-4 text-sm text-info"
        >
          This form is archived and read-only. Its answers and evidence remain
          available for review and export.
        </p>
      )}
      {writes.error && (
        <div role="alert" className="rounded-lg bg-danger-soft p-3 text-sm text-danger">
          <p>{writes.error}</p>
          {writes.conflicted ? (
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <p className="max-w-prose">Compare each unsaved draft with the latest saved answer below. Review and combine changes before saving, or explicitly discard your draft.</p>
              {writes.conflictReady ? (
                <div><span className="text-sm">Latest form loaded. Resolve each draft below.</span>{writes.hasPendingUploads && !writes.hasPendingAnswerDrafts && <><p className="mt-2 text-sm">Review the latest answer and evidence before retrying the uploaded attachment.</p><Button className="mt-2" size="sm" disabled={writes.isWriting} onClick={writes.resumeWrites}>Use latest form for attachment retry</Button></>}</div>
              ) : (
                <Button size="sm" disabled={writes.isWriting} onClick={() => void writes.refreshConflict()}>Reload latest form</Button>
              )}
            </div>
          ) : (
            <Button className="mt-2" size="sm" disabled={writes.isWriting} onClick={writes.resumeWrites}>{writes.hasPendingDrafts ? 'Retry saving' : 'Resume editing'}</Button>
          )}
        </div>
      )}
      {(writes.hasPendingDrafts || writes.isWriting) && (
        <p role="status" className="text-xs text-muted">Unsaved changes remain. Keep this form open until every draft is saved.</p>
      )}
      <div className="pilot-form-readiness border-y border-line py-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <h3 className="font-semibold">Form completion and acceptance</h3>
          <span className="text-muted">{item.readiness.answered_count} of {item.readiness.required_count} required answers · {item.readiness.accepted_count} accepted</span>
          <span className={item.readiness.ready ? 'font-semibold text-success' : 'font-semibold text-warning'}>
            {item.readiness.ready ? 'Required answers accepted' : 'Not ready'}
          </span>
          <span className="text-muted">Pack approval and authority decisions are separate.</span>
        </div>
        {item.readiness.blockers.length > 0 && (
          <details className="mt-1">
            <summary className="w-fit text-xs font-medium text-warning">Review {item.readiness.blockers.length} readiness {item.readiness.blockers.length === 1 ? 'issue' : 'issues'}</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-warning">
              {item.readiness.blockers.map((blocker, index) => (
                <li key={`${blocker.field_key}-${blocker.code}-${index}`}>
                  {item.fields.find((field) => field.key === blocker.field_key)
                    ?.label || blocker.field_key}
                  : {blocker.message}{blocker.field_key && <button type="button" className="ml-2 font-medium text-accent underline" onClick={() => { chooseQuestion(blocker.field_key); const target = document.getElementById(`preparation-field-${blocker.field_key}`); target?.scrollIntoView?.({ block: 'center' }); target?.focus() }}>Review field</button>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
      {!!item.original_evidence_ids?.length && <details className="border-y border-line py-3">
        <summary className="cursor-pointer text-sm font-semibold">Original form documents ({item.original_evidence_ids.length})</summary>
        <div className="mt-3"><EvidenceAttachments ids={item.original_evidence_ids} /></div>
        <p className="mt-2 text-xs text-muted">Retained for reference. Review imported questions against these documents; this form export does not reproduce the authority’s original layout.</p>
      </details>}
      <section className="pilot-question-workspace" aria-label="Answers">
        <div className="pilot-question-navigation">
          <Button size="sm" disabled={questionIndex === 0} onClick={() => chooseQuestion(item.fields[questionIndex - 1].key)}>Previous question</Button>
          <select aria-label="Current question" value={question} onChange={event => chooseQuestion(event.target.value)}>{item.fields.map((field, index) => <option key={field.key} value={field.key}>{index + 1} · {field.label}</option>)}</select>
          <Button size="sm" disabled={questionIndex >= item.fields.length - 1} onClick={() => chooseQuestion(item.fields[questionIndex + 1].key)}>Next question</Button>
          <span className="pilot-question-count">{answered} answered · {accepted} accepted</span>
          <button type="button" className="text-sm text-accent underline" onClick={() => { const next = [...item.fields.slice(questionIndex + 1), ...item.fields.slice(0, questionIndex + 1)].find(field => !item.responses.find(response => response.field_key === field.key)?.accepted_at); if (next) chooseQuestion(next.key) }} disabled={accepted >= item.fields.length}>Next needing attention</button>
        </div>
        <div className="flex flex-wrap justify-between gap-3 text-sm text-muted"><p>{allQuestions ? 'All questions' : `Question ${questionIndex + 1} of ${item.fields.length}`} · Answers save automatically</p><button type="button" className="text-accent underline" disabled={writes.hasPendingUploads} onClick={() => setAllQuestions(!allQuestions)}>{allQuestions ? 'Focus current question' : 'View all questions'}</button></div>
        {sections.map((section, index) => <section key={index} id={`preparation-section-${index}`} hidden={!allQuestions && !section.fields.some(field => field.key === question)}>
          {allQuestions && <h3 className="mt-5 font-semibold">{section.name}</h3>}
          {section.fields.map(field => <CaseField key={field.key} caseId={item.id} field={field} response={item.responses.find(response => response.field_key === field.key)} blockers={item.readiness.blockers.filter(blocker => blocker.field_key === field.key)} archived={archived} canEdit={canEdit} canAccept={item.access ? roleManage && item.access.permissions.includes('approve') : canManage} writes={writes} jurisdictionName={jurisdictionName} onSourceNavigate={canLeave} focused={!allQuestions} hidden={!allQuestions && field.key !== question} reviewerName={item.reviewer_name} onDirtyChange={(key, dirty) => { if (dirty) dirtyFields.current.add(key); else dirtyFields.current.delete(key) }} />)}
        </section>)}
        <div className="pilot-contributor-footer"><Button size="sm" disabled={questionIndex >= item.fields.length - 1} onClick={() => chooseQuestion(item.fields[questionIndex + 1].key)}>Next question</Button>{inRouter ? <Link className="pilot-primary-link" to="/" onClick={event => { if (!canLeave()) event.preventDefault() }}>Back to my work</Link> : <a className="pilot-primary-link" href={import.meta.env.BASE_URL} onClick={event => { if (!canLeave()) event.preventDefault() }}>Back to my work</a>}</div>
      </section>
      <Card className="p-4 sm:p-5">
        {pack && <Button className="pilot-mobile-export" disabled={Boolean(item.access && !item.access.permissions.includes('export'))} onClick={() => void exportZip()} loading={downloadBusy}>Export form and evidence</Button>}
        {canManage && !archived && <ReviewerAssignment item={item} writes={writes} />}
        {canManage && !archived ? (
          <details>
            <summary className="cursor-pointer marker:text-accent">
              <span className="text-sm font-semibold">Form details</span>
              <span className="mt-1 block text-sm text-muted">
                Owner: {ownerName} · Deadline: {item.due_date || 'None'}
              </span>
              {metadataDirty && (
                <span className="mt-1 block text-xs font-semibold text-warning">
                  Unsaved form details
                </span>
              )}
            </summary>
            <form className="mt-3" onSubmit={saveMetadata}>
              <fieldset
                disabled={writes.isWriting}
                className="space-y-4"
                aria-label="Form details editor"
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="text-sm font-medium">
                    Form name
                    <input
                      required
                      maxLength={255}
                      className="mt-1 w-full px-3 py-2"
                      value={name}
                      onChange={(event) => {
                        setName(event.target.value)
                        setMetadataDirty(true)
                      }}
                    />
                  </label>
                  <label className="text-sm font-medium">
                    Owner
                    <select
                      className="mt-1 w-full px-3 py-2"
                      value={ownerId}
                      onChange={(event) => {
                        setOwnerId(event.target.value)
                        setMetadataDirty(true)
                      }}
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
                    Deadline
                    <input
                      type="date"
                      className="mt-1 w-full px-3 py-2"
                      value={dueDate}
                      onChange={(event) => {
                        setDueDate(event.target.value)
                        setMetadataDirty(true)
                      }}
                    />
                  </label>
                  <label className="text-sm font-medium">
                    Certification project (optional)
                    <select
                      className="mt-1 w-full px-3 py-2"
                      value={projectId}
                      onChange={(event) => {
                        setProjectId(event.target.value)
                        setMetadataDirty(true)
                      }}
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
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={!metadataDirty || writes.isWriting || writes.hasPendingDrafts || Boolean(writes.pauseReason)}
                  >
                    Save form details
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={writes.isWriting || writes.hasPendingDrafts || Boolean(writes.pauseReason)}
                    onClick={() => {
                      if (
                        window.confirm(
                          metadataDirty
                            ? 'Archive this form and discard unsaved edits? Responses will become read-only.'
                            : 'Archive this form? Responses will become read-only.',
                        )
                      )
                        void writes.updateCase({ status: 'archived' }).then((saved) => { if (saved) setMetadataDirty(false) })
                    }}
                  >
                    Archive form
                  </Button>
                </div>
              </fieldset>
            </form>
          </details>
        ) : (
          <>
            <h3 className="text-sm font-semibold">Form details</h3>
            <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">Owner</dt>
                <dd>{ownerName}</dd>
              </div>
              <div>
                <dt className="text-muted">Deadline</dt>
                <dd>{item.due_date || 'None'}</dd>
              </div>
            </dl>
          </>
        )}
        {canManage && archived && (
          <Button
            className="mt-4"
            size="sm"
            disabled={writes.isWriting}
            onClick={() => void writes.updateCase({ status: 'active' })}
          >
            Restore form to active
          </Button>
        )}
        {project && (
          <p className="mt-4 text-sm">
            Linked project:{' '}
            <Link
              to={`/certification-projects?project=${project.id}`}
              className="font-semibold text-accent underline"
              onClick={(event) => {
                if (!canLeave()) event.preventDefault()
              }}
            >
              {project.name}
            </Link>
          </p>
        )}
      </Card>
      {item.access?.permissions.includes('manage_access') && (
        <details className="rounded-xl border border-line bg-surface p-4">
          <summary className="font-semibold">Sharing and access</summary>
          <div className="mt-4"><AccessPanel type="preparation_case" id={item.id} /></div>
        </details>
      )}
      </div></div>
    </div>
  )
}
