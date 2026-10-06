import { useMemo, useState } from 'react'
import type {
  ExtractionFeedbackBatchRequest,
  ExtractionFeedbackBatchResponse,
  ExtractionSectionPrefixOption,
} from '../../types'

type BulkTriagePanelProps = {
  runId: string | null
  disabled: boolean
  requirementTypes: string[]
  sectionOptions: ExtractionSectionPrefixOption[]
  reviewReasons: string[]
  previewResult: ExtractionFeedbackBatchResponse | null
  lastApplyResult: ExtractionFeedbackBatchResponse | null
  isPreviewing: boolean
  isApplying: boolean
  onPreview: (payload: ExtractionFeedbackBatchRequest) => void
  onApply: (payload: ExtractionFeedbackBatchRequest) => void
  canUndo: boolean
  undoDisabled: boolean
  undoUnavailableReason: string | null
  onUndo: () => void
}

function toNumberOrUndefined(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

export default function BulkTriagePanel({
  runId,
  disabled,
  requirementTypes,
  sectionOptions,
  reviewReasons,
  previewResult,
  lastApplyResult,
  isPreviewing,
  isApplying,
  onPreview,
  onApply,
  canUndo,
  undoDisabled,
  undoUnavailableReason,
  onUndo,
}: BulkTriagePanelProps) {
  const [confidenceMin, setConfidenceMin] = useState('')
  const [confidenceMax, setConfidenceMax] = useState('')
  const [requirementType, setRequirementType] = useState('')
  const [sectionPrefix, setSectionPrefix] = useState('')
  const [reviewReason, setReviewReason] = useState('')
  const [actionType, setActionType] = useState<'accept' | 'reject' | 'edit'>('accept')
  const [editRequirementType, setEditRequirementType] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const activeResult = lastApplyResult || previewResult

  const canSendEditAction = useMemo(() => {
    if (actionType !== 'edit') return true
    return !!editRequirementType || !!editStatus
  }, [actionType, editRequirementType, editStatus])

  const buildPayload = (previewOnly: boolean): ExtractionFeedbackBatchRequest | null => {
    const payload: ExtractionFeedbackBatchRequest = {
      run_id: runId || undefined,
      preview_only: previewOnly,
      filter: {
        needs_review_only: true,
      },
      action: {
        type: actionType,
      },
    }

    const min = toNumberOrUndefined(confidenceMin)
    const max = toNumberOrUndefined(confidenceMax)
    if (min !== undefined) payload.filter!.confidence_min = min
    if (max !== undefined) payload.filter!.confidence_max = max
    if (requirementType) payload.filter!.requirement_types = [requirementType]
    if (sectionPrefix) payload.filter!.section_prefixes = [sectionPrefix]
    if (reviewReason) payload.filter!.review_reasons = [reviewReason]

    if (actionType === 'edit') {
      if (!canSendEditAction) {
        setFormError('Select edit fields (requirement type and/or status) for edit action.')
        return null
      }
      payload.action.edit = {}
      if (editRequirementType) payload.action.edit.requirement_type = editRequirementType
      if (editStatus) payload.action.edit.status = editStatus
    }

    setFormError(null)
    return payload
  }

  const handlePreview = () => {
    const payload = buildPayload(true)
    if (!payload) return
    onPreview(payload)
  }

  const handleApply = () => {
    const payload = buildPayload(false)
    if (!payload) return
    onApply(payload)
  }

  return (
    <div className="mb-4 rounded-lg border border-line bg-surface p-4" data-testid="bulk-triage-panel">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold text-ink">Bulk Triage</h3>
        <div className="text-xs text-muted">Run scope: {runId || 'all extracted rows'}</div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <label className="text-xs font-medium text-ink">
          Confidence min
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={confidenceMin}
            onChange={(event) => setConfidenceMin(event.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs font-medium text-ink">
          Confidence max
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={confidenceMax}
            onChange={(event) => setConfidenceMax(event.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs font-medium text-ink">
          Requirement type
          <select
            value={requirementType}
            onChange={(event) => setRequirementType(event.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          >
            <option value="">Any</option>
            {requirementTypes.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-ink">
          Section prefix
          <select
            value={sectionPrefix}
            onChange={(event) => setSectionPrefix(event.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          >
            <option value="">Any</option>
            {sectionOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-ink">
          Review reason
          <select
            value={reviewReason}
            onChange={(event) => setReviewReason(event.target.value)}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          >
            <option value="">Any</option>
            {reviewReasons.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium text-ink">
          Action
          <select
            value={actionType}
            onChange={(event) => setActionType(event.target.value as 'accept' | 'reject' | 'edit')}
            className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
          >
            <option value="accept">Accept</option>
            <option value="reject">Reject</option>
            <option value="edit">Edit + Accept</option>
          </select>
        </label>
      </div>

      {actionType === 'edit' ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="text-xs font-medium text-ink">
            New requirement type
            <select
              value={editRequirementType}
              onChange={(event) => setEditRequirementType(event.target.value)}
              className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
            >
              <option value="">Keep existing</option>
              <option value="mandatory">mandatory</option>
              <option value="recommended">recommended</option>
              <option value="informational">informational</option>
            </select>
          </label>
          <label className="text-xs font-medium text-ink">
            New status
            <select
              value={editStatus}
              onChange={(event) => setEditStatus(event.target.value)}
              className="mt-1 w-full rounded-md border border-line-strong px-2 py-1.5 text-sm"
            >
              <option value="">Keep existing</option>
              <option value="pending">pending</option>
              <option value="accepted">accepted</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
        </div>
      ) : null}

      {formError ? <p className="mt-2 text-xs text-danger">{formError}</p> : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled || isPreviewing || isApplying}
          onClick={handlePreview}
          className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
        >
          {isPreviewing ? 'Previewing...' : 'Preview'}
        </button>
        <button
          type="button"
          disabled={disabled || isApplying || isPreviewing}
          onClick={handleApply}
          className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-hover disabled:opacity-50"
        >
          {isApplying ? 'Applying...' : 'Apply'}
        </button>
        <button
          type="button"
          disabled={!canUndo || undoDisabled}
          onClick={onUndo}
          className="rounded-md border border-warning-line px-3 py-1.5 text-xs font-medium text-warning hover:bg-warning-soft disabled:opacity-50"
        >
          Undo last bulk action
        </button>
      </div>
      {undoUnavailableReason ? <p className="mt-2 text-xs text-warning">{undoUnavailableReason}</p> : null}

      {activeResult ? (
        <div className="mt-3 rounded-md border border-line bg-canvas p-3 text-xs text-ink">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span>Matched: {activeResult.matched_count}</span>
            <span>Affected: {activeResult.affected_count}</span>
            <span>Failures: {activeResult.failures.length}</span>
          </div>
          {activeResult.affected_ids_truncated ? (
            <p className="mt-1 text-warning">
              Result affected IDs exceeded 500. Full undo is not available for this action.
            </p>
          ) : null}
          {activeResult.failures.length ? (
            <ul className="mt-2 space-y-1 text-danger">
              {activeResult.failures.slice(0, 3).map((failure, index) => (
                <li key={`${failure.code}-${index}`}>
                  {failure.code}: {failure.detail}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
