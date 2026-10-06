import AccessPanel from '../access/AccessPanel'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import { useCaseWrites } from '../../hooks/preparation/useCaseWrites'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import type { CertificationProject, UserMention } from '../../types'
import type { PreparationCase, PreparationField } from '../../types/preparation'
import Button from '../ui/Button'
import Card from '../ui/Card'
import CaseField from './CaseField'
import EvidenceAttachments from './EvidenceAttachments'

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
}: {
  item: PreparationCase
  canEdit: boolean
  canManage: boolean
  users: UserMention[]
  projects: CertificationProject[]
  jurisdictionName: (id: string) => string
  onBack: () => void
  backLabel?: string
  initialFieldKey?: string
  headingLevel?: 1 | 2
}) {
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  const canEdit = item.access ? roleEdit && item.access.permissions.includes('edit') : roleEdit
  const canManage = item.access ? roleManage && item.access.permissions.includes('edit') : roleManage
  const [name, setName] = useState(item.name)
  const [ownerId, setOwnerId] = useState(item.owner_id || '')
  const [dueDate, setDueDate] = useState(item.due_date || '')
  const [projectId, setProjectId] = useState(item.project_id || '')
  const [metadataDirty, setMetadataDirty] = useState(false)
  const focusedTarget = useRef('')
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
    target?.scrollIntoView?.({ block: 'center' })
    target?.focus()
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
    navigationGuarded || !(metadataDirty || dirtyFields.current.size > 0 || writes.isWriting) ||
    window.confirm('Some changes are still waiting to save. Leave this form? Unsaved edits will be lost; a save already in progress may still complete.')
  const backWithDraftGuard = () => {
    if (canLeave()) onBack()
  }
  useEffect(() => {
    if (navigationGuarded) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!metadataDirty && dirtyFields.current.size === 0 && !writes.isWriting) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [metadataDirty, writes.isWriting, navigationGuarded])
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button variant="ghost" size="sm" onClick={backWithDraftGuard}>
            ← {backLabel}
          </Button>
          <Heading className="mt-1 text-xl font-semibold">{item.name}</Heading>
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
              <p className="max-w-prose">Your unsaved fields show the latest answer for comparison. Use the latest answer where appropriate, then resume to save the remaining drafts.</p>
              {writes.conflictReady ? (
                <Button size="sm" disabled={writes.isWriting} onClick={writes.resumeWrites}>Keep my drafts and resume autosave</Button>
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
      <div className="border-y border-line py-2">
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
                  : {blocker.message}{blocker.field_key && <button type="button" className="ml-2 font-medium text-accent underline" onClick={() => { const target = document.getElementById(`preparation-field-${blocker.field_key}`); target?.scrollIntoView?.({ block: 'center' }); target?.focus() }}>Review field</button>}
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
      <Card className="overflow-hidden">
        <div className="border-b border-line px-4 py-3 sm:px-5">
          <h3 className="text-base font-semibold">Answers</h3>
          <p className="mt-1 text-sm text-muted">
            {canEdit && !archived
              ? 'Answers save automatically. Acceptance remains a separate review step. Required fields are marked *.'
              : 'Review the saved answers and supporting evidence below.'}
          </p>
          {sections.length > 1 && (
            <nav aria-label="Form sections" className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
              {sections.map((section, index) => (
                <a key={index} href={`#preparation-section-${index}`} className="py-1 text-sm font-medium text-accent underline decoration-transparent hover:decoration-current">{section.name}</a>
              ))}
            </nav>
          )}
        </div>
        <div className="px-4 sm:px-5">
          {sections.map((section, index) => {
            const fields = section.fields
            const answered = fields.filter((field) => item.responses.some((response) =>
              response.field_key === field.key &&
              (response.value !== null || response.not_applicable_reason || response.evidence_ids.length > 0),
            )).length
            return (
              <section
                key={index}
                id={`preparation-section-${index}`}
                aria-labelledby={`preparation-section-heading-${index}`}
                className="scroll-mt-24 pt-4"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-2">
                  <h4 id={`preparation-section-heading-${index}`} className="text-base font-semibold">{section.name}</h4>
                  <span className="text-xs tabular-nums text-muted">{answered} of {fields.length} answered</span>
                </div>
                <div className="grid grid-cols-1 gap-x-6 lg:grid-cols-2">
                {fields.map((field) => (
                  <CaseField
                    key={field.key}
                    caseId={item.id}
                    field={field}
                    response={item.responses.find(
                      (response) => response.field_key === field.key,
                    )}
                    blockers={item.readiness.blockers.filter(
                      (blocker) => blocker.field_key === field.key,
                    )}
                    archived={archived}
                    canEdit={canEdit}
                    canAccept={item.access ? roleManage && item.access.permissions.includes('approve') : canManage}
                    writes={writes}
                    jurisdictionName={jurisdictionName}
                    onSourceNavigate={canLeave}
                    onDirtyChange={(key, dirty) => {
                      if (dirty) dirtyFields.current.add(key)
                      else dirtyFields.current.delete(key)
                    }}
                  />
                ))}
                </div>
              </section>
            )
          })}
        </div>
      </Card>
      <Card className="p-4 sm:p-5">
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
    </div>
  )
}
