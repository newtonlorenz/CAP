import { useEffect, useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { preparationApi } from '../../api/preparation'
import type { CaseWrites } from '../../hooks/preparation/useCaseWrites'
import { useResponseDraft } from '../../hooks/preparation/useResponseDraft'
import {
  fieldValueToString,
  type PreparationBlocker,
  type PreparationField,
  type PreparationResponse,
} from '../../types/preparation'
import Button from '../ui/Button'
import CopyButton from '../ui/CopyButton'
import DraftSaveStatus from '../ui/DraftSaveStatus'
import EvidenceAttachments from './EvidenceAttachments'
import ContextualEvidenceUpload from './ContextualEvidenceUpload'
import AnswerHistory from './AnswerHistory'
import type { PilotPreparationCase } from '../../types/pilotReview'

const EMPTY_RESPONSE: PreparationResponse = {
  field_key: '',
  value: null,
  not_applicable_reason: null,
  evidence_ids: [],
  accepted_at: null,
  accepted_by: null,
  reused_from_case_id: null,
  reused_from_field_key: null,
}

export default function CaseField({
  caseId,
  field,
  response: incoming,
  blockers,
  archived,
  canEdit,
  canAccept,
  writes,
  jurisdictionName,
  onDirtyChange,
  onSourceNavigate,
  focused = false,
  hidden = false,
  reviewerName,
}: {
  caseId: string
  field: PreparationField
  response?: PilotPreparationCase['responses'][number]
  blockers: PreparationBlocker[]
  archived: boolean
  canEdit: boolean
  canAccept: boolean
  writes: CaseWrites
  jurisdictionName: (id: string) => string
  onDirtyChange: (fieldKey: string, dirty: boolean) => void
  onSourceNavigate?: () => boolean
  focused?: boolean
  hidden?: boolean
  reviewerName?: string | null
}) {
  const response = incoming || EMPTY_RESPONSE
  const inputId = useId()
  const questionId = `${inputId}-question`
  const helpId = field.help_text ? `${inputId}-help` : undefined
  const [uploadPending, setUploadPending] = useState(false)
  const { setFieldDirty } = writes
  useEffect(() => { setFieldDirty(`upload:${field.key}`, uploadPending); return () => setFieldDirty(`upload:${field.key}`, false) }, [field.key, setFieldDirty, uploadPending])
  const [showReuse, setShowReuse] = useState(false)
  const [suggestionError, setSuggestionError] = useState('')
  const readOnly = !canEdit || archived
  const draft = useResponseDraft(field, response, !readOnly, writes, onDirtyChange)
  const { value, reason, evidenceIds, dirty } = draft
  const [supportOpen, setSupportOpen] = useState(Boolean(
    response.not_applicable_reason || (!focused && (response.evidence_ids.length || field.type === 'evidence')),
  ))
  const copyValue = readOnly ? fieldValueToString(response.value) : value
  const copyReason = readOnly ? response.not_applicable_reason || '' : reason
  const answerText = field.type === 'yes_no'
    ? copyValue === 'true' ? 'Yes' : copyValue === 'false' ? 'No' : ''
    : copyValue
  const copyText = copyReason.trim() ? `Not applicable: ${copyReason.trim()}` : answerText
  const suggestions = useQuery({
    queryKey: ['preparation', 'reuse', caseId, field.key],
    queryFn: () => preparationApi.reuseSuggestions(caseId, field.key),
    enabled: showReuse && canEdit && !archived,
  })
  return (
    <article
      id={`preparation-field-${field.key}`}
      tabIndex={-1}
      hidden={hidden}
      className={`${focused ? 'pilot-focused-question' : ''} min-w-0 scroll-mt-24 border-b border-line py-3 ${field.type === 'multiline' || field.type === 'evidence' ? 'lg:col-span-2' : ''}`}
      aria-label={field.label}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <div className="min-w-[10rem] flex-1">
          <h5 className="break-words text-sm font-semibold leading-relaxed text-ink">
            <span id={questionId} className="whitespace-pre-wrap break-words">{field.label}</span>
            {field.required && (
              <span className="ml-1 text-danger" aria-label="required">
                *
              </span>
            )}
          </h5>
          {field.help_text && (
            <p id={helpId} className="mt-1 max-w-prose text-sm text-muted">
              {field.help_text}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!readOnly && <DraftSaveStatus state={draft.state} message={draft.localError || undefined} onRetry={draft.state === 'error' && !draft.localError ? draft.retry : undefined} />}
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${dirty || incoming?.review_status === 'changes_requested' ? 'bg-warning-soft text-warning' : response.accepted_at ? 'bg-success-soft text-success' : 'bg-subtle text-muted'}`}
          >
            {dirty || draft.saving
              ? 'Draft'
              : response.accepted_at
                ? 'Accepted'
                : incoming?.review_status === 'changes_requested'
                  ? 'Changes requested'
                : response.value !== null ||
                    response.not_applicable_reason ||
                    response.evidence_ids.length
                  ? 'Pending acceptance'
                  : 'Unanswered'}
          </span>
          {field.type !== 'evidence' && (
            <CopyButton
              value={copyText}
              className="min-h-11 min-w-11 px-2"
              title={dirty && !readOnly ? 'Copy draft answer' : 'Copy answer'}
              aria-label={`Copy answer for ${field.label}`}
              successMessage={dirty && !readOnly ? 'Draft answer copied.' : 'Answer copied.'}
            />
          )}
        </div>
      </div>
      {blockers.filter((blocker) => blocker.code !== 'pending_acceptance' && blocker.code !== 'missing').map((blocker, index) => (
        <p
          key={`${blocker.code}-${index}`}
          className="mt-2 text-sm text-warning"
        >
          {blocker.message}
        </p>
      ))}
      {response.reused_from_case_id && (
        <p className="mt-2 text-xs text-muted">
          Reused from{' '}
          <Link
            className="font-semibold text-accent underline"
            to={`/preparation?case=${encodeURIComponent(response.reused_from_case_id)}`}
            onClick={(event) => {
              if (onSourceNavigate && !onSourceNavigate())
                event.preventDefault()
            }}
          >
            source case
          </Link>
          {response.reused_from_field_key
            ? ` (${response.reused_from_field_key})`
            : ''}
          .{' '}
          {response.accepted_at
            ? 'Accepted for this case.'
            : 'Pending review for this case.'}
        </p>
      )}
      {readOnly ? (
        <div className="mt-4 space-y-2 text-sm">
          <p className="whitespace-pre-wrap break-words">
            {response.not_applicable_reason
              ? `Not applicable: ${response.not_applicable_reason}`
              : response.value === null
                ? field.type === 'evidence'
                  ? 'Evidence field'
                  : 'No answer'
                : field.type === 'yes_no' ? response.value ? 'Yes' : 'No' : fieldValueToString(response.value)}
          </p>
          {(response.evidence_ids.length > 0 || field.type === 'evidence') && <EvidenceAttachments ids={response.evidence_ids} />}
        </div>
      ) : (
        <form className="mt-2" onSubmit={(event) => { event.preventDefault(); void draft.saveNow() }} onBlur={() => void draft.saveNow()}>
          <fieldset
            className="space-y-3"
            aria-label={`Response editor for ${field.label}`}
          >
            {field.type === 'multiline' ? (
              <label className="block text-sm font-medium">
                <span className="sr-only">{field.label}</span>
                <textarea
                  aria-labelledby={questionId}
                  aria-describedby={helpId}
                  aria-required={field.required}
                  rows={3}
                  className="mt-1 w-full px-3 py-2"
                  value={value}
                  disabled={Boolean(reason)}
                  onChange={(event) =>
                    draft.change({ value: event.target.value })
                  }
                />
              </label>
            ) : field.type === 'yes_no' ? (
              <fieldset aria-labelledby={questionId} aria-describedby={helpId} disabled={Boolean(reason)}>
                <div className="flex flex-wrap items-center gap-2">
                  {[['true', 'Yes'], ['false', 'No']].map(([option, label]) => (
                    <label key={option} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-4 py-2 text-sm ${value === option ? 'border-accent bg-brand-soft' : 'border-line-strong'}`}>
                      <input
                        type="radio"
                        name={inputId}
                        value={option}
                        checked={value === option}
                        onChange={() => draft.change({ value: option })}
                      />
                      {label}
                    </label>
                  ))}
                  {value !== '' && (
                    <Button size="sm" variant="ghost" onClick={() => draft.change({ value: '' })}>Clear answer</Button>
                  )}
                </div>
              </fieldset>
            ) : field.type === 'choice' ? (
              <label className="block text-sm font-medium">
                <span className="sr-only">{field.label}</span>
                <select
                  aria-labelledby={questionId}
                  aria-describedby={helpId}
                  aria-required={field.required}
                  className="mt-1 w-full px-3 py-2"
                  value={value}
                  disabled={Boolean(reason)}
                  onChange={(event) =>
                    draft.change({ value: event.target.value })
                  }
                >
                  <option value="">Choose an answer</option>
                  {field.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            ) : field.type === 'evidence' ? (
              <p className="text-sm text-muted">
                Attach evidence from the shared library below.
              </p>
            ) : (
              <label className="block text-sm font-medium">
                <span className="sr-only">{field.label}</span>
                <input
                  aria-labelledby={questionId}
                  aria-describedby={helpId}
                  aria-required={field.required}
                  type={
                    field.type === 'date'
                      ? 'date'
                      : field.type === 'number'
                        ? 'number'
                        : 'text'
                  }
                  step={field.type === 'number' ? 'any' : undefined}
                  className="mt-1 w-full px-3 py-2"
                  value={value}
                  disabled={Boolean(reason)}
                  onChange={(event) =>
                    draft.change({ value: event.target.value })
                  }
                />
              </label>
            )}
              {canAccept &&
                !dirty &&
                (response.value !== null ||
                  response.not_applicable_reason ||
                  response.evidence_ids.length > 0) &&
                !response.accepted_at && (
                  <Button
                    size="sm"
                    disabled={writes.isWriting || writes.hasPendingDrafts || Boolean(writes.pauseReason) || dirty || draft.saving}
                    onClick={() => void writes.acceptField(field.key)}
                  >
                    Accept response
                  </Button>
                )}
            {(writes.conflicted || draft.needsReview) && dirty && (
              <div className="pilot-conflict" role="alert">
                <h3>This form changed while you were editing.</h3>
                <p>Your draft has not been saved. Keep this form open until it is saved.</p>
                {writes.conflictReady ? <>
                  <details open><summary>Latest saved answer</summary><p className="whitespace-pre-wrap break-words">{response.not_applicable_reason ? `Not applicable: ${response.not_applicable_reason}` : response.value === null ? 'No answer' : field.type === 'yes_no' ? response.value ? 'Yes' : 'No' : fieldValueToString(response.value)}</p><EvidenceAttachments ids={response.evidence_ids} /></details>
                  <details open><summary>Your unsaved draft</summary><p className="whitespace-pre-wrap break-words">{reason ? `Not applicable: ${reason}` : value || 'No answer'}</p><EvidenceAttachments ids={evidenceIds} /></details>
                  {draft.comparing ? <><p>Combine your changes in the answer editor above, then save when you are ready.</p><Button variant="primary" disabled={draft.saving} onClick={draft.saveCombined}>Save combined answer</Button></> : <Button variant="primary" disabled={draft.saving} onClick={draft.reviewChanges}>Review and combine changes</Button>}
                  <Button variant="ghost" disabled={draft.saving} onClick={draft.useLatest}>Discard my draft and use latest</Button>
                </> : <><p>The latest saved form has not loaded. Your local draft is retained; comparison is unavailable.</p><Button onClick={() => void writes.refreshConflict()}>Retry loading latest form</Button></>}
              </div>
            )}
            {focused && <section className="pilot-answer-evidence"><h3>Evidence for this answer</h3><EvidenceAttachments ids={evidenceIds} disabled={draft.saving || uploadPending} onChange={(next) => draft.change({ evidenceIds: next })} /><ContextualEvidenceUpload caseId={caseId} onBusyChange={setUploadPending} ids={evidenceIds} disabled={draft.saving || Boolean(writes.pauseReason) || draft.needsReview} attach={draft.attachEvidence} /><p className="text-xs text-muted">Earlier attachment references remain in answer history.</p></section>}
            <details open={supportOpen || Boolean(reason) || (!focused && (evidenceIds.length > 0 || field.type === 'evidence'))} onToggle={(event) => setSupportOpen(event.currentTarget.open)} className="max-w-2xl text-sm">
              <summary className="w-fit py-1 text-muted hover:text-ink">Supporting details<span className="ml-2 text-xs">Evidence, not applicable{field.reuse_key ? ', reuse' : ''}</span></summary>
              <div className="mt-3 space-y-4">
                <label className="block max-w-2xl text-sm font-medium">
                  Not applicable reason (optional)
                  <textarea
                    rows={2}
                    className="mt-1 w-full px-3 py-2"
                    value={reason}
                    onChange={(event) =>
                      draft.change({ reason: event.target.value })
                    }
                  />
                  <span className="mt-1 block text-xs font-normal text-muted">
                    A manager must accept a not applicable response before this
                    field is ready.
                  </span>
                </label>
                {!focused && <EvidenceAttachments ids={evidenceIds} onChange={(next) => draft.change({ evidenceIds: next })} />}
                {field.reuse_key && (
                  <Button
                    size="sm"
                    onClick={() => setShowReuse(!showReuse)}
                    aria-expanded={showReuse}
                  >
                    Find reusable answers
                  </Button>
                )}
              </div>
            </details>
          </fieldset>
        </form>
      )}
      {focused && <AnswerHistory caseId={caseId} fieldKey={field.key} revision={writes.revision} />}
      {incoming?.feedback?.filter(feedback => !feedback.resolved_at).map(feedback => <div className="pilot-feedback" key={feedback.id}><strong>Changes requested · {feedback.created_by_name || 'Reviewer'}</strong><p>{feedback.comment}</p><small>Your next saved revision returns this answer for review. This feedback stays open until the reviewer resolves it.</small></div>)}
      {focused && !dirty && !uploadPending && !draft.saving && (response.value !== null || response.evidence_ids.length > 0 || response.not_applicable_reason) && <p className="pilot-next-action" role="status">{response.accepted_at ? 'This answer and its attached evidence are accepted.' : incoming?.review_status === 'changes_requested' ? 'Changes requested · Next action: update this answer using the feedback above.' : reviewerName ? `Saved · Next action: ${reviewerName} to review this answer.` : 'Saved · Review owner unassigned.'}</p>}
      {showReuse && canEdit && !archived && (
        <div className="mt-4 max-w-2xl rounded-xl bg-subtle p-4">
          <h5 className="font-semibold">Possible answers to review</h5>
          <p className="mt-1 text-xs text-muted">
            Matching a reuse key does not establish legal equivalence. Reused
            answers remain pending acceptance.
          </p>
          {dirty && (
            <p className="mt-2 text-sm text-warning">
              Your draft must finish saving before you can reuse another answer.
            </p>
          )}
          {suggestions.isLoading ? (
            <p role="status" className="mt-3 text-sm text-muted">
              Finding answers…
            </p>
          ) : suggestions.isError ? (
            <p role="alert" className="mt-3 text-sm text-danger">
              Suggestions could not be loaded.{' '}
              <button
                type="button"
                className="underline"
                onClick={() => void suggestions.refetch()}
              >
                Retry
              </button>
            </p>
          ) : !suggestions.data?.items.length ? (
            <p className="mt-3 text-sm text-muted">
              No matching answers were found.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {suggestions.data.items.map((item) => (
                <li
                  key={`${item.source_case_id}-${item.source_field_key}`}
                  className="flex flex-wrap items-start justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium">
                      {item.source_case_name} ·{' '}
                      {jurisdictionName(item.source_jurisdiction_id)}
                    </p>
                    <p className="text-sm text-muted">
                      {fieldValueToString(item.value)}
                      {item.accepted_at
                        ? ` · Accepted ${item.accepted_at.slice(0, 10)}`
                        : ' · Pending review'}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    disabled={writes.isWriting || writes.hasPendingDrafts || Boolean(writes.pauseReason) || dirty || draft.saving}
                    onClick={async () => {
                      setSuggestionError('')
                      const ok = await writes.reuseField(
                        field.key,
                        item.source_case_id,
                        item.source_field_key,
                      )
                      if (ok) {
                        setShowReuse(false)
                      } else
                        setSuggestionError(
                          'Reuse failed. Review the case error and try again.',
                        )
                    }}
                  >
                    Reuse answer
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {suggestionError && (
            <p role="alert" className="mt-2 text-sm text-danger">
              {suggestionError}
            </p>
          )}
        </div>
      )}
    </article>
  )
}
