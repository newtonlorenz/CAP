import type { RequirementSetSummary } from '../types'

export type RequirementSetRoutingResult = {
  openPath: string
  openLabel: 'Open' | 'Import' | 'Edit'
  canEdit: boolean
}

const isManualRequirementSet = (set: RequirementSetSummary) =>
  set.has_source === undefined
    ? !set.filename || set.filename === 'manual-placeholder.pdf'
    : !set.has_source

const isDraftLikeWithRequirements = (set: RequirementSetSummary) =>
  ['draft', 'changes_requested'].includes(set.document_status) && set.requirements_total > 0

const isPreApprovalImportedSet = (set: RequirementSetSummary) =>
  ['extracted', 'reviewed', 'pending_approval'].includes(set.document_status)

export function getRequirementSetRouting(
  set: RequirementSetSummary,
  isAdminOrManager: boolean
): RequirementSetRoutingResult {
  const isManualSet = isManualRequirementSet(set)
  const canEdit =
    isAdminOrManager &&
    (
      isManualSet ||
      set.document_status === 'approved' ||
      isDraftLikeWithRequirements(set) ||
      isPreApprovalImportedSet(set)
    )
  const shouldOpenInEditMode = isAdminOrManager && isDraftLikeWithRequirements(set)

  const openPath = shouldOpenInEditMode
    ? `/requirements/sets/${set.document_id}/edit`
    : !isManualSet && set.requirements_total === 0
      ? `/requirements/sets/${set.document_id}/import`
      : `/requirements/sets/${set.document_id}`
  const openLabel: 'Open' | 'Import' | 'Edit' = shouldOpenInEditMode
    ? 'Edit'
    : openPath.endsWith('/import')
      ? 'Import'
      : 'Open'

  return { openPath, openLabel, canEdit }
}
