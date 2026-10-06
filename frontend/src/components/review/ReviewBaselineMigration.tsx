import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type { ReviewCycleBaselineMigrationExecuteResponse, ReviewCycleBaselineMigrationPreviewResponse, ReviewCycleWithItems } from '../../types'
import { stripHtml } from '../../utils/richText'
import { notifyApiError } from '../../utils/notify'
import { useToast } from '../../contexts/ToastContext'
import Tooltip from '../ui/Tooltip'

const truncatePreviewText = (value: string | null, limit = 220) => {
  if (!value) return 'No text available.'
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, Math.max(0, limit - 3))}...`
}

const MIGRATION_TEXT_EXPAND_THRESHOLD = 320

const formatMigrationPreviewText = (value: string | null) => {
  if (!value) return 'No text available.'
  const withLineBreaks = value
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|ul|ol|h[1-6])>/gi, '\n')
    .replace(/<li>/gi, '• ')
  const normalized = stripHtml(withLineBreaks)
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
  return normalized || 'No text available.'
}

const canExpandMigrationPreviewText = (value: string) =>
  value !== 'No text available.' && value.length > MIGRATION_TEXT_EXPAND_THRESHOLD

export default function ReviewBaselineMigration({ cycle, docMap, isAdminOrManager, hidden, hasUnsavedChanges }: {
  cycle: ReviewCycleWithItems
  docMap: Map<string, string>
  isAdminOrManager: boolean
  hidden: boolean
  hasUnsavedChanges: boolean
}) {
  const id = cycle.id
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [migrationPreview, setMigrationPreview] =
    useState<ReviewCycleBaselineMigrationPreviewResponse | null>(null)
  const [changedDecisions, setChangedDecisions] = useState<
    Record<string, 'reset_pending' | 'carry_forward'>
  >({})
  const [expandedMigrationTexts, setExpandedMigrationTexts] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setMigrationPreview(null)
    setChangedDecisions({})
    setExpandedMigrationTexts({})
  }, [id])

  const previewMigrationMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post<ReviewCycleBaselineMigrationPreviewResponse>(
        `/review-cycles/${id}/baseline-migrations/preview`
      )
      return response.data
    },
    onSuccess: (data) => {
      setMigrationPreview(data)
      setExpandedMigrationTexts({})
      setChangedDecisions({})
      toast.success('Latest-version gap analysis generated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to preview latest requirements migration')
    },
  })

  const executeMigrationMutation = useMutation({
    mutationFn: async (targetVersionIds: string[]) => {
      const response = await api.post<ReviewCycleBaselineMigrationExecuteResponse>(
        `/review-cycles/${id}/baseline-migrations/execute`,
        {
          target_version_ids: targetVersionIds,
          changed_decisions: Object.entries(changedDecisions).map(
            ([new_requirement_id, action]) => ({
              new_requirement_id,
              action,
            })
          ),
        }
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle'] })
      setMigrationPreview(null)
      setChangedDecisions({})
      toast.success(`Successor review cycle created (${data.migrated_items} items migrated)`)
      navigate(`/review-cycles/${data.to_cycle_id}`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to migrate review cycle to latest requirements')
    },
  })

  const baselineRows = useMemo(
    () =>
      (cycle?.baseline_versions || []).map((baseline) => ({
        ...baseline,
        displayName: baseline.set_name || docMap.get(baseline.document_id) || 'Requirement set',
        latestStatus:
          baseline.is_latest === true
            ? 'latest'
            : baseline.is_latest === false && typeof baseline.latest_version_number === 'number'
              ? 'outdated'
              : 'unknown',
      })),
    [cycle?.baseline_versions, docMap]
  )

  const outdatedBaselines = useMemo(
    () => baselineRows.filter((baseline) => baseline.latestStatus === 'outdated'),
    [baselineRows]
  )
  const unavailableBaselines = useMemo(
    () => baselineRows.filter((baseline) => baseline.latestStatus === 'unknown'),
    [baselineRows]
  )

  const canPreviewLatestMigration =
    isAdminOrManager && cycle?.status === 'active' && outdatedBaselines.length > 0

  const changedRequirementIds = useMemo(
    () =>
      (migrationPreview?.changed || [])
        .map((item) => item.new_requirement_id)
        .filter((value): value is string => Boolean(value)),
    [migrationPreview]
  )
  const decidedCount = changedRequirementIds.filter((requirementId) =>
    Boolean(changedDecisions[requirementId])
  ).length
  const carryForwardCount = changedRequirementIds.filter((requirementId) =>
    changedDecisions[requirementId] === 'carry_forward'
  ).length
  const resetCount = decidedCount - carryForwardCount
  const needsDecisions = decidedCount !== changedRequirementIds.length

  const areAllChangedRequirementsSetTo = (action: 'reset_pending' | 'carry_forward') =>
    changedRequirementIds.length > 0 &&
    changedRequirementIds.every((requirementId) => {
      return changedDecisions[requirementId] === action
    })

  const applyDecisionToAllChangedRequirements = (
    action: 'reset_pending' | 'carry_forward'
  ) => {
    setChangedDecisions((current) => {
      const next = { ...current }
      changedRequirementIds.forEach((requirementId) => {
        next[requirementId] = action
      })
      return next
    })
  }

  return (
            <details className="mt-2 py-1" hidden={hidden}><summary className="cursor-pointer text-sm font-medium text-ink">Requirement baseline and version history</summary>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>

                  <h2 className="mt-2 text-lg font-semibold text-ink">
                    Locked requirement-set versions
                  </h2>
                  <p className="mt-1 max-w-3xl text-sm text-muted">
                    Review items stay pinned to these approved versions until you migrate the cycle.
                  </p>
                </div>
                {canPreviewLatestMigration ? (
                  <button
                    type="button"
                    onClick={() => previewMigrationMutation.mutate()}
                    disabled={previewMigrationMutation.isPending}
                    className="rounded-md border border-line-strong bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-subtle disabled:opacity-50"
                  >
                    {previewMigrationMutation.isPending
                      ? 'Preparing gap analysis...'
                      : migrationPreview
                        ? 'Refresh gap analysis'
                        : 'Preview latest migration'}
                  </button>
                ) : null}
              </div>

              {baselineRows.length === 0 ? (
                <p className="mt-4 text-sm text-muted">
                  No locked requirement-set version snapshot is available for this cycle.
                </p>
              ) : (
                <div className="mt-4 space-y-3">
                  {baselineRows.map((baseline) => (
                    <div
                      key={`${baseline.document_id}-${baseline.requirement_set_version_id}`}
                      className="rounded-xl border border-line bg-surface px-4 py-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-ink">{baseline.displayName}</div>
                          <div className="mt-1 text-xs text-muted">
                            Locked to v{baseline.version_number}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full bg-subtle px-2.5 py-1 text-xs font-medium text-ink">
                            Locked v{baseline.version_number}
                          </span>
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                              baseline.latestStatus === 'latest'
                                ? 'bg-success-soft text-success'
                                : baseline.latestStatus === 'outdated'
                                  ? 'bg-warning-soft text-warning'
                                  : 'bg-line text-ink'
                            }`}
                          >
                            {baseline.latestStatus === 'latest'
                              ? 'Latest approved'
                              : baseline.latestStatus === 'outdated'
                                ? `Latest approved v${baseline.latest_version_number} available`
                                : 'Latest status unavailable'}
                          </span>
                        </div>
                      </div>
                      {baseline.latestStatus === 'outdated' ? (
                        <p className="mt-2 text-sm text-warning">
                          This cycle is using an older approved version. Preview the migration before continuing review work.
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-4 text-sm text-muted">
                {outdatedBaselines.length > 0
                  ? outdatedBaselines.length === 1
                    ? '1 requirement set has a newer approved version available.'
                    : `${outdatedBaselines.length} requirement sets have newer approved versions available.`
                  : unavailableBaselines.length > 0
                    ? unavailableBaselines.length === 1
                      ? 'Latest approved baseline status is unavailable for 1 requirement set.'
                      : `Latest approved baseline status is unavailable for ${unavailableBaselines.length} requirement sets.`
                  : 'This cycle already uses the latest approved requirement-set versions.'}
              </div>

              {migrationPreview && outdatedBaselines.length > 0 ? (
                <div className="mt-5 rounded-2xl border border-line bg-surface p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-semibold text-ink">Gap analysis</h3>
                      <p className="mt-1 text-sm text-muted">
                        Compare the locked wording with the latest approved wording. Your choices create a successor cycle and leave this cycle as the prior baseline.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded-full bg-subtle px-2.5 py-1 font-medium text-ink">
                        Retained unchanged {migrationPreview.matched.length}
                      </span>
                      <span className="rounded-full bg-warning-soft px-2.5 py-1 font-medium text-warning">
                        Changed: decide {migrationPreview.changed.length}
                      </span>
                      <span className="rounded-full bg-success-soft px-2.5 py-1 font-medium text-success">
                        Added new {migrationPreview.added.length}
                      </span>
                      <span className="rounded-full bg-danger-soft px-2.5 py-1 font-medium text-danger">
                        Removed from successor {migrationPreview.removed.length}
                      </span>
                    </div>
                  </div>

                  {migrationPreview.changed.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      <h4 className="text-sm font-semibold text-ink">
                        Changed requirements
                      </h4>
                      <div className="rounded-xl border border-line bg-canvas px-4 py-3">
                        <p className="text-sm text-ink">
                          Unchanged requirements carry forward automatically. Choose how to handle each changed requirement. Both choices require a new review.
                        </p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <span className="text-xs font-medium uppercase tracking-wide text-muted">
                            Change all changed requirements
                          </span>
                          <button
                            type="button"
                            onClick={() => applyDecisionToAllChangedRequirements('reset_pending')}
                            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
                              areAllChangedRequirementsSetTo('reset_pending')
                                ? 'border-line-strong bg-strong text-white'
                                : 'border-line-strong bg-surface text-ink hover:bg-subtle'
                            }`}
                          >
                            Reset all to pending
                          </button>
                          <button
                            type="button"
                            onClick={() => applyDecisionToAllChangedRequirements('carry_forward')}
                            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
                              areAllChangedRequirementsSetTo('carry_forward')
                                ? 'border-line-strong bg-strong text-white'
                                : 'border-line-strong bg-surface text-ink hover:bg-subtle'
                            }`}
                          >
                            Carry forward all
                          </button>
                        </div>
                      </div>
                      {migrationPreview.changed.map((item) => {
                        const decisionKey = item.new_requirement_id || ''
                        const itemKey =
                          item.new_requirement_id || `${item.document_id}-${item.reference_id}`
                        const oldText = formatMigrationPreviewText(item.old_text)
                        const newText = formatMigrationPreviewText(item.new_text)
                        const oldTextKey = `${itemKey}-old`
                        const newTextKey = `${itemKey}-new`
                        const oldTextExpanded = expandedMigrationTexts[oldTextKey] === true
                        const newTextExpanded = expandedMigrationTexts[newTextKey] === true
                        const oldTextCanExpand = canExpandMigrationPreviewText(oldText)
                        const newTextCanExpand = canExpandMigrationPreviewText(newText)
                        return (
                          <div
                            key={itemKey}
                            className="rounded-xl border border-line bg-canvas/70 p-3"
                          >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div>
                                <div className="font-medium text-ink">
                                  {item.set_name ? `${item.set_name} - ` : ''}
                                  {item.reference_id}
                                </div>
                                <div className="mt-1 text-xs text-muted">
                                  {oldText === newText
                                    ? 'The source formatting or requirement classification changed. Check the prior assessment against this version.'
                                    : 'The wording changed. Check whether the prior assessment still covers the latest requirement.'}
                                </div>
                              </div>
                              <div className="grid gap-2 text-sm text-ink sm:min-w-[24rem]">
                                <label className="flex items-start gap-3 rounded-lg border border-line bg-surface px-3 py-2.5">
                                  <input
                                    type="radio"
                                    name={`migration-decision-${decisionKey}`}
                                    className="mt-0.5"
                                    checked={
                                      changedDecisions[decisionKey] === 'reset_pending'
                                    }
                                    onChange={() =>
                                      setChangedDecisions((current) => ({
                                        ...current,
                                        [decisionKey]: 'reset_pending',
                                      }))
                                    }
                                  />
                                  <span>
                                    <span className="font-medium text-ink">
                                      Reset pending
                                    </span>
                                    <span className="mt-1 block text-xs leading-relaxed text-muted">
                                      Start pending with no prior comments, files, Jira links, or requirement status. Review the new wording from scratch.
                                    </span>
                                  </span>
                                </label>
                                <label className="flex items-start gap-3 rounded-lg border border-line bg-surface px-3 py-2.5">
                                  <input
                                    type="radio"
                                    name={`migration-decision-${decisionKey}`}
                                    className="mt-0.5"
                                    checked={changedDecisions[decisionKey] === 'carry_forward'}
                                    onChange={() =>
                                      setChangedDecisions((current) => ({
                                        ...current,
                                        [decisionKey]: 'carry_forward',
                                      }))
                                    }
                                  />
                                  <span>
                                    <span className="font-medium text-ink">
                                      Carry forward
                                    </span>
                                    <span className="mt-1 block text-xs leading-relaxed text-muted">
                                      Keep prior comments, files, Jira links, review assignments, and evidence. Start with no requirement status or review decision until reviewed again.
                                    </span>
                                  </span>
                                </label>
                              </div>
                            </div>

                            <div className="mt-3 grid gap-3 lg:grid-cols-2">
                              <div className="rounded-lg border border-line bg-surface p-3">
                                <div className="flex items-start justify-between gap-3">
                                  <div className="text-xs font-medium uppercase tracking-wide text-faint">
                                    Locked version
                                  </div>
                                  {oldTextCanExpand ? (
                                    <button
                                      type="button"
                                      aria-expanded={oldTextExpanded}
                                      onClick={() =>
                                        setExpandedMigrationTexts((current) => ({
                                          ...current,
                                          [oldTextKey]: !current[oldTextKey],
                                        }))
                                      }
                                      className="text-xs font-medium text-muted hover:text-ink"
                                    >
                                      {oldTextExpanded ? 'Show less' : 'Show full text'}
                                    </button>
                                  ) : null}
                                </div>
                                <div
                                  className={`mt-2 rounded-md bg-canvas/80 px-3 py-3 ${
                                    oldTextExpanded ? '' : 'max-h-56 overflow-hidden'
                                  }`}
                                >
                                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                                    {oldText}
                                  </p>
                                </div>
                              </div>
                              <div className="rounded-lg border border-warning-line bg-warning-soft/70 p-3">
                                <div className="flex items-start justify-between gap-3">
                                  <div className="text-xs font-medium uppercase tracking-wide text-warning">
                                    Latest approved version
                                  </div>
                                  {newTextCanExpand ? (
                                    <button
                                      type="button"
                                      aria-expanded={newTextExpanded}
                                      onClick={() =>
                                        setExpandedMigrationTexts((current) => ({
                                          ...current,
                                          [newTextKey]: !current[newTextKey],
                                        }))
                                      }
                                      className="text-xs font-medium text-warning hover:text-warning"
                                    >
                                      {newTextExpanded ? 'Show less' : 'Show full text'}
                                    </button>
                                  ) : null}
                                </div>
                                <div
                                  className={`mt-2 rounded-md bg-surface/80 px-3 py-3 ${
                                    newTextExpanded ? '' : 'max-h-56 overflow-hidden'
                                  }`}
                                >
                                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-ink">
                                    {newText}
                                  </p>
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : null}

                  {migrationPreview.added.length > 0 ? (
                    <div className="mt-4">
                      <h4 className="text-sm font-semibold text-ink">
                        Added requirements
                      </h4>
                      <div className="mt-2 space-y-2">
                        {migrationPreview.added.map((item) => (
                          <div
                            key={item.new_requirement_id || `${item.document_id}-${item.reference_id}`}
                            className="rounded-lg border border-success-line bg-success-soft/70 px-3 py-2 text-sm text-ink"
                          >
                            <span className="font-medium text-ink">
                              {item.set_name ? `${item.set_name} - ` : ''}
                              {item.reference_id}
                            </span>
                            <span className="ml-2">{truncatePreviewText(item.new_text, 160)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {migrationPreview.removed.length > 0 ? (
                    <div className="mt-4">
                      <h4 className="text-sm font-semibold text-ink">
                        Removed requirements
                      </h4>
                      <div className="mt-2 space-y-2">
                        {migrationPreview.removed.map((item) => (
                          <div
                            key={item.old_requirement_id || `${item.document_id}-${item.reference_id}`}
                            className="rounded-lg border border-danger-line bg-danger-soft/70 px-3 py-2 text-sm text-ink"
                          >
                            <span className="font-medium text-ink">
                              {item.set_name ? `${item.set_name} - ` : ''}
                              {item.reference_id}
                            </span>
                            <span className="ml-2">{truncatePreviewText(item.old_text, 160)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-5 flex flex-wrap items-center gap-3">
                    <span className="min-w-0 flex-1 text-sm text-muted" role="status">
                      {migrationPreview.matched.length} unchanged retained; {carryForwardCount} changed carry forward for re-review; {resetCount} changed reset; {migrationPreview.added.length} added; {migrationPreview.removed.length} removed. {needsDecisions ? `${changedRequirementIds.length - decidedCount} decisions needed.` : 'All changed requirements decided.'}
                    </span>
                    {hasUnsavedChanges && <span className="text-xs text-muted">Save review changes before migrating.</span>}
                    <Tooltip content={hasUnsavedChanges ? 'Save review changes before migrating' : needsDecisions ? 'Choose an action for every changed requirement' : undefined}><button
                      type="button"
                      onClick={() => executeMigrationMutation.mutate(migrationPreview.target_version_ids)}
                      disabled={executeMigrationMutation.isPending || hasUnsavedChanges || needsDecisions}
                      className="rounded-md bg-strong px-3 py-2 text-sm font-medium text-white hover:bg-strong disabled:opacity-50"
                    >
                      {executeMigrationMutation.isPending
                        ? 'Creating successor cycle...'
                        : 'Migrate to latest requirements'}
                    </button></Tooltip>
                  </div>
                </div>
              ) : null}
            </details>
  )
}
