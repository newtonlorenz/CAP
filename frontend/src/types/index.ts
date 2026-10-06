import type { ResourceAccess } from './access'
export type ProductFeedbackStatus = 'new' | 'in_progress' | 'done'
export interface ProductFeedbackReport {
  id: string
  author_id: string
  kind: 'bug' | 'feature' | 'other'
  message: string
  page_path: string
  pin: import('@page-feedback/react').FeedbackPin | null
  has_screenshot: boolean
  status: ProductFeedbackStatus
  created_at: string
  updated_at: string
}

export interface User {
  installation_operator?: boolean
  system_admin_designated?: boolean
  id: string
  organization_id?: string | null
  email: string
  full_name: string
  role: 'admin' | 'manager' | 'approver' | 'contributor' | 'assigned_reviewer'
  active: boolean
  created_at: string
}

export interface UserMention {
  id: string
  email: string
  full_name: string
}

export interface Jurisdiction {
  id: string
  code: string
  name: string
  regulator_name: string | null
  report_header_text: string | null
  pack_status?: 'published' | 'scaffold' | 'draft' | null
  pack_version?: string | null
  parser_mode?: string | null
  supports_deterministic_import?: boolean | null
  coverage_notes?: string | null
  active: boolean
  created_at: string
}

export interface JiraIntegration {
  base_url: string
  project_key: string
  user_email: string
  enabled: boolean
  token_configured: boolean
  last_tested_at: string | null
  last_test_status: string | null
  last_test_message: string | null
}

export interface JiraIntegrationEnvelope {
  configured: boolean
  integration: JiraIntegration | null
}

export interface BackupMetadata {
  id: string
  archive_filename: string
  created_at: string
  reason: string
  source_backup_id: string | null
  created_by_user_id: string | null
  created_by_user_name: string | null
  size_bytes: number
  sha256: string
  format_version: number
}

export interface BackupListResponse {
  items: BackupMetadata[]
  total: number
}

export interface BackupRestoreRequest {
  confirmation: string
  reason?: string
}

export interface BackupRestoreResponse {
  restored_backup_id: string
  pre_restore_backup_id: string
  completed_at: string
  reason: string | null
}

export interface ExtractionRun {
  id: string
  document_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timed_out'
  total_pages: number | null
  current_page: number
  requirements_found: number
  error_message: string | null
  error_page: number | null
  ai_provider: string
  ai_model: string
  pipeline_version?: string
  ocr_applied?: boolean
  ocr_pages?: number
  warning_count?: number
  parseability_score?: number | null
  fallback_trigger_reason?: string | null
  strategy_counts?: Record<string, number> | null
  diagnostics_available?: boolean
  started_at: string | null
  last_progress_at?: string | null
  completed_at: string | null
  created_at: string
}

export interface Document {
  id: string
  organization_id?: string | null
  jurisdiction_id: string
  filename: string | null
  has_source?: boolean
  name: string | null
  document_type: string
  version: string | null
  effective_date: string | null
  status: string
  uploaded_by: string
  approval_comment: string | null
  approved_by: string | null
  current_extraction_id: string | null
  current_extraction: ExtractionRun | null
  maintenance_plan_id?: string | null
  cadence_interval_days?: number | null
  testing_frequency: string | null
  archived_at: string | null
  created_at: string
}

export interface RequirementSetSummary {
  document_id: string
  jurisdiction_id?: string
  filename: string | null
  has_source?: boolean
  name: string | null
  document_type: string
  version?: string | null
  testing_frequency?: string | null
  document_status: string
  archived_at: string | null
  requirements_total: number
  requirements_active: number
  current_version_id?: string | null
  current_version_number?: number | null
  current_version_status?: string | null
}

export interface RequirementSetVersion {
  id: string
  organization_id: string | null
  document_id: string
  version_number: number
  status: string
  is_current: boolean
  based_on_version_id: string | null
  change_summary: string | null
  created_by: string
  approved_by: string | null
  created_at: string
  approved_at: string | null
  locked_at: string | null
}

export interface ExtractedRequirement {
  id: string
  document_id: string
  reference_id: string
  title?: string | null
  text: string
  original_text: string
  requirement_type: string
  parent_id: string | null
  page_number: number
  confidence_score: number
  status: string
  needs_review?: boolean
  review_reason?: string | null
  source_excerpt?: string | null
  parser_strategy?: string
  sort_order: number
  created_at: string
}

export interface ExtractionBatchDistributionItem {
  key: string
  total: number
}

export interface ExtractionFeedbackBatchFilter {
  needs_review_only?: boolean
  confidence_min?: number
  confidence_max?: number
  requirement_types?: string[]
  section_prefixes?: string[]
  review_reasons?: string[]
  include_statuses?: string[]
  exclude_statuses?: string[]
}

export interface ExtractionFeedbackBatchAction {
  type: 'accept' | 'reject' | 'edit'
  edit?: {
    requirement_type?: string
    status?: string
  }
}

export interface ExtractionFeedbackBatchRequest {
  run_id?: string
  preview_only?: boolean
  filter?: ExtractionFeedbackBatchFilter
  action: ExtractionFeedbackBatchAction
}

export interface ExtractionFeedbackBatchResponse {
  preview_only: boolean
  matched_count: number
  affected_count: number
  affected_ids: string[]
  affected_ids_truncated: boolean
  failures: Array<{
    extraction_id?: string | null
    code: string
    detail: string
  }>
  distributions: {
    by_review_reason: ExtractionBatchDistributionItem[]
    by_requirement_type: ExtractionBatchDistributionItem[]
    by_section_prefix: ExtractionBatchDistributionItem[]
    by_confidence_band: ExtractionBatchDistributionItem[]
  }
}

export interface ExtractionSectionPrefixOption {
  value: string
  label: string
}

export interface ExtractionReorderRequest {
  run_id: string
  ordered_ids: string[]
}

export interface ExtractionReorderResponse {
  updated_count: number
  ordered_ids: string[]
}

export interface RequirementExtractionFlag {
  extraction_id: string | null
  flagged: boolean
  reason: string | null
}

export interface Requirement {
  id: string
  organization_id?: string | null
  jurisdiction_id: string
  source_extraction_id: string | null
  document_id: string | null
  requirement_set_version_id?: string | null
  source_requirement_id?: string | null
  reference_id: string
  title?: string | null
  text: string
  requirement_type: string
  parent_id: string | null
  default_owner_id: string | null
  active: boolean
  version: number
  sort_order: number
  created_at: string
}

export interface RequirementStatus {
  id: string
  requirement_id: string
  status: string
  assigned_to: string | null
  comment: string
  changed_by: string
  changed_at: string
}

export interface RequirementWithStatus extends Requirement {
  current_status: string | null
  assigned_to: string | null
  status_history: RequirementStatus[]
  evidence_counts?: {
    notes: number
    files: number
    links: number
  }
}

export interface EvidenceNote {
  id: string
  requirement_id: string
  note_text: string
  created_by: string
  created_at: string
}

export interface EvidenceFile {
  id: string
  requirement_id: string
  filename: string
  description: string | null
  uploaded_by: string
  uploaded_at: string
}

export interface EvidenceLink {
  id: string
  requirement_id: string
  url: string
  label: string
  added_by: string
  added_at: string
}

export interface Evidence {
  notes: EvidenceNote[]
  files: EvidenceFile[]
  links: EvidenceLink[]
}

export interface ReviewItemEvidenceFile {
  comment_id?: string | null
  id: string
  review_item_id: string
  filename: string
  description: string | null
  uploaded_by: string
  uploaded_at: string
}

export interface ReviewCycle {
  id: string
  organization_id?: string | null
  jurisdiction_id: string
  certification_project_id?: string | null
  change_entry_id?: string | null
  predecessor_cycle_id?: string | null
  cycle_type?: 'operational' | 'submission' | 'maintenance' | string
  name: string
  description: string | null
  scope: string
  scope_filter: string | null
  document_ids?: string[] | null
  baseline_versions?: ReviewCycleBaselineVersion[]
  deadline: string | null
  status: string
  created_by: string
  closed_at: string | null
  closed_by: string | null
  snapshot_id: string | null
  created_at: string
}

export interface ReviewItem {
  id: string
  review_cycle_id: string
  requirement_id: string
  review_status: string
  assigned_reviewer_id: string | null
  responsible_user_id: string | null
  reviewer_id: string | null
  reviewer_name?: string | null
  review_comment: string | null
  review_evidence: string | null
  evidence_changed_at?: string | null
  evidence_changed_since_review?: boolean
  jira_issue_key: string | null
  jira_issue_url: string | null
  jira_status: string | null
  jira_summary: string | null
  jira_assignee: string | null
  jira_priority: string | null
  jira_updated_at: string | null
  jira_synced_at: string | null
  jira_sync_error: string | null
  reviewed_at: string | null
  created_at: string
  comments: ReviewItemComment[]
  evidence_files: ReviewItemEvidenceFile[]
}

export interface ReviewItemComment {
  id: string
  review_item_id: string
  author_id: string | null
  author_name: string
  body: string
  created_at: string
  updated_at: string | null
  can_edit: boolean
}

export interface RequirementSummary {
  id: string
  document_id: string | null
  reference_id: string
  title?: string | null
  text: string
  requirement_type: string
  parent_id: string | null
  sort_order: number
}

export interface ReviewItemWithRequirement extends ReviewItem {
  requirement: RequirementSummary
  requirement_current_status: string | null
}

export interface ReviewItemBulkMutationRequest {
  item_ids: string[]
  review_status?: string | null
  review_evidence?: string | null
  assigned_reviewer_id?: string | null
  responsible_user_id?: string | null
}

export interface ReviewItemBulkMutationFailure {
  item_id: string
  detail: string
}

export interface ReviewItemBulkMutationResponse {
  updated_count: number
  failed_count: number
  updated_item_ids: string[]
  failures: ReviewItemBulkMutationFailure[]
}

export interface ReviewReadiness {
  snapshot_warning?: string | null
  can_close: boolean; total: number; applicable: number; ready: number; not_applicable: number; informational: number; blocker_count: number
  blockers: { item_id: string | null; reference_id: string; reasons: string[] }[]
}

export interface ReviewCycleWithItems extends ReviewCycle {
  readiness?: ReviewReadiness
  jira_integration_configured: boolean
  items: ReviewItemWithRequirement[]
  progress: {
    total: number
    completed: number
    pending: number
  }
}

export interface Snapshot {
  id: string
  organization_id?: string | null
  name: string
  description: string | null
  snapshot_type: string
  total_requirements: number
  evidenced_requirements: number
  created_by: string
  created_at: string
}

export interface AuditLogEntry {
  title?: string | null
  destination?: string | null
  id: string
  user_name: string
  action: string
  entity_type: string
  entity_id: string
  timestamp: string
  event_hash?: string | null
  prev_hash?: string | null
  summary?: string | null
}

export interface AuditLogDetail {
  id: string
  organization_id?: string | null
  user_id: string
  user_name: string
  action: string
  entity_type: string
  entity_id: string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  event_hash?: string | null
  prev_hash?: string | null
  timestamp: string
}

export interface Control {
  id: string
  jurisdiction_id: string
  code: string
  title: string
  description: string | null
  test_method: string | null
  evidence_expectations: string | null
  cadence_days: number | null
  status: string
  created_at: string
}

export interface Obligation {
  id: string
  jurisdiction_id: string
  code: string
  legal_reference: string | null
  title: string
  description: string | null
  status: string
  created_at: string
}

export interface ControlCrosswalk {
  id: string
  source_control_id: string
  target_obligation_id: string
  mapping_strength: string
  notes: string | null
  created_at: string
}

export interface ComponentRegister {
  responsibility_role?: import('./changeManagement').ResponsibilityRole
  programme_assurance?: import('./changeManagement').ProgrammeAssurance
  programme_readiness?: import('./changeManagement').ProgrammeReadiness
  id: string
  organization_id: string | null
  jurisdiction_id: string
  name: string
  status: 'active' | 'inactive' | string
  created_by: string
  created_at: string
  updated_at: string
}

export interface ManagedComponent {
  regulatory_scope?: import('./changeManagement').RegulatoryScope
  id: string
  register_id: string
  component_uid: string
  definition: string
  version: string
  identifying_characteristics: string
  change_owner_id: string | null
  change_owner_name: string | null
  confidentiality_code: 1 | 2 | 3 | number
  integrity_code: 1 | 2 | 3 | number
  availability_code: 1 | 2 | 3 | number
  accountability_code: 1 | 2 | 3 | number
  classification_code: 1 | 2 | 3 | number
  checksum_hash: string | null
  is_hardware: boolean
  geographic_location: string | null
  hosting_model: 'on_prem' | 'private_cloud' | 'public_cloud' | string
  virtualized: boolean
  public_cloud_provider: string | null
  public_cloud_certification: string | null
  public_cloud_independent: boolean
  public_cloud_redundancy: boolean
  status: 'active' | 'inactive' | 'retired' | string
  created_by: string
  created_at: string
  updated_at: string
}

export interface ChangeEntryComponent {
  frozen_snapshot?: { component_uid?: string; version?: string; checksum_hash?: string | null; classification_code?: number; regulatory_scope?: string }
  baseline_scope_assessment?: string | null
  baseline_id?: string | null
  planned_checksum_hash?: string | null
  implemented_checksum_hash?: string | null
  id: string
  change_entry_id: string
  component_id: string
  version_at_proposal: string | null
  planned_version: string | null
  implemented_version: string | null
  created_at: string
}

export interface ChangeEvent {
  id: string
  change_entry_id: string
  event_type: 'note' | 'decision' | 'status_change' | string
  status_from: string | null
  status_to: string | null
  note: string | null
  created_by: string | null
  created_at: string
  updated_by: string | null
  updated_at: string | null
  deleted_by: string | null
  deleted_at: string | null
  deletion_reason: string | null
}

export interface IntegrationCheck {
  id: string
  change_entry_id: string
  action: string
  action_reference: string | null
  result: 'pending' | 'pass' | 'fail' | string
  completed_by: string | null
  completed_at: string | null
  notes: string | null
  evidence_notes: string | null
  created_at: string
  updated_by: string | null
  updated_at: string | null
  deleted_by: string | null
  deleted_at: string | null
  deletion_reason: string | null
}

export interface ChangeEntry {
  compliance?: import('./changeManagement').ChangeCompliance
  readiness?: import('./changeManagement').ChangeReadiness
  blocking_assessment_ids?: string[]
  rollback?: { reason?: string; outcome?: string; follow_up?: string; recorded_at?: string }
  id: string
  register_id: string
  title: string
  description: string | null
  category: string | null
  change_type: 'standard' | 'normal' | 'emergency' | string
  proposed_by_name_snapshot: string | null
  complexity_classification: string | null
  resource_assessment: string | null
  scheduling_assessment: string | null
  affected_components_summary: string | null
  affected_docs_summary: string | null
  planned_start_at: string | null
  planned_end_at: string | null
  justification: string | null
  affected_documentation: string | null
  evaluation_effect: string | null
  evaluation_risk: string | null
  evaluation_regulatory_impact: string | null
  evaluation_ciaa_impact: string | null
  approval_decision: string | null
  approved_by: string | null
  approved_at: string | null
  rejection_reason: string | null
  rejected_by: string | null
  rejected_at: string | null
  implementation_notes: string | null
  implemented_by: string | null
  implemented_at: string | null
  implemented_start_at: string | null
  implemented_end_at: string | null
  verification_notes: string | null
  verified_by: string | null
  verified_at: string | null
  testing_org_required: boolean
  testing_org_status: string | null
  testing_org_due_at: string | null
  testing_org_cycle: 'immediate' | 'quarterly' | 'annual' | string | null
  testing_org_next_due_at: string | null
  testing_org_approved_at: string | null
  integration_related: boolean
  status: 'draft' | 'approved' | 'rejected' | 'implemented' | 'verified' | string
  proposed_by: string
  proposed_at: string
  created_at: string
  updated_at: string
  components: ChangeEntryComponent[]
  events: ChangeEvent[]
  integration_checks: IntegrationCheck[]
}

export interface ComponentBaseline {
  certification_scope?: 'manual' | 'whole_platform'
  certification_at?: string | null
  certification_evidence?: string | null
  certification_ato?: string | null
  certification_reference?: string | null
  id: string
  register_id: string
  label: string
  established_by: string
  established_at: string
  created_at: string
}

export interface BaselineDiffItem {
  component_uid: string
  change_type: 'added' | 'removed' | 'changed'
  baseline_version: string | null
  current_version: string | null
  baseline_classification_code: number | null
  current_classification_code: number | null
  changed_fields: string[]
  field_differences: Record<string, { baseline: unknown; current: unknown }>
}

export interface BaselineDiffResponse {
  baseline_id: string
  register_id: string
  summary: {
    added: number
    removed: number
    changed: number
    total: number
    generated_at: string
  }
  items: BaselineDiffItem[]
}

export interface ChangeActivityItem {
  id: string
  activity_type: 'status_event' | 'event' | 'integration_check' | 'audit_log' | string
  action: string
  occurred_at: string
  actor_id: string | null
  detail: string | null
  metadata: Record<string, unknown>
}

export interface ChangeActivityResponse {
  items: ChangeActivityItem[]
}

export interface CertificationProject {
  access?: ResourceAccess
  summary_only?: boolean
  id: string
  organization_id: string | null
  source_document_id: string | null
  requirement_set_ids?: string[]
  baseline_versions?: ProjectBaselineVersion[]
  jurisdiction_id: string
  name: string
  description: string | null
  stage:
    | 'intake'
    | 'scoping'
    | 'gap_assessment'
    | 'remediation'
    | 'pre_audit'
    | 'submission'
    | 'follow_up'
    | string
  status: 'active' | 'on_hold' | 'completed' | string
  owner_id: string | null
  created_by: string
  started_at: string | null
  target_submission_date: string | null
  assurance_type: 'test' | 'audit' | 'certification' | null
  provider_name: string | null
  engagement_reference: string | null
  assurance_scope: string | null
  system_version: string | null
  scheduled_test_date: string | null
  actual_test_date: string | null
  report_reference: string | null
  report_outcome: 'not_recorded' | 'passed' | 'passed_with_findings' | 'failed' | null
  report_issued_at: string | null
  report_link: string | null
  completed_at: string | null
  created_at: string
}

export interface CertificationProjectFromDocumentResponse {
  created: boolean
  project: CertificationProject
}

export interface CertificationProjectSubmissionCycleResponse {
  created: boolean
  review_cycle_id: string
  review_items_created?: number
  warning?: string | null
}

export interface ProjectBaselineVersion {
  document_id: string
  requirement_set_version_id: string
  version_number: number
  set_name: string | null
}

export interface CertificationProjectBaselineUpdateResponse {
  project: CertificationProject
  warning: string | null
}

export interface BaselineMigrationDeltaItem {
  document_id?: string | null
  set_name?: string | null
  reference_id: string
  old_requirement_id: string | null
  new_requirement_id: string | null
  old_text: string | null
  new_text: string | null
}

export interface BaselineMigrationPreviewResponse {
  migration_id: string
  from_cycle_id: string | null
  target_version_ids: string[]
  matched: BaselineMigrationDeltaItem[]
  changed: BaselineMigrationDeltaItem[]
  added: BaselineMigrationDeltaItem[]
  removed: BaselineMigrationDeltaItem[]
}

export interface BaselineMigrationExecuteResponse {
  created: boolean
  from_cycle_id: string | null
  to_cycle_id: string
  migrated_items: number
}

export interface ReviewCycleBaselineVersion {
  document_id: string
  requirement_set_version_id: string
  version_number: number
  set_name: string | null
  is_latest?: boolean
  latest_requirement_set_version_id?: string | null
  latest_version_number?: number | null
}

export interface ReviewCycleBaselineMigrationDeltaItem {
  document_id: string | null
  set_name: string | null
  reference_id: string
  old_requirement_id: string | null
  new_requirement_id: string | null
  old_text: string | null
  new_text: string | null
}

export interface ReviewCycleBaselineMigrationPreviewResponse {
  source_cycle_id: string
  target_version_ids: string[]
  matched: ReviewCycleBaselineMigrationDeltaItem[]
  changed: ReviewCycleBaselineMigrationDeltaItem[]
  added: ReviewCycleBaselineMigrationDeltaItem[]
  removed: ReviewCycleBaselineMigrationDeltaItem[]
}

export interface ReviewCycleBaselineMigrationExecuteResponse {
  created: boolean
  from_cycle_id: string
  to_cycle_id: string
  migrated_items: number
}

export interface CertificationProjectMilestone {
  id: string
  project_id: string
  stage: string
  title: string
  due_at: string | null
  status: 'pending' | 'done' | 'blocked' | string
  notes: string | null
  created_at: string
}

export interface SubmissionPackage {
  id: string
  project_id: string
  review_cycle_id: string | null
  snapshot_id: string | null
  version: string
  status: 'draft' | 'pending_approval' | 'approved' | 'locked' | string
  checklist_json: string | null
  checklist?: SubmissionChecklist | null
  checklist_completion?: SubmissionChecklistCompletion
  approval_requested_at: string | null
  approved_by: string | null
  approved_at: string | null
  locked_at: string | null
  created_by: string
  created_at: string
}

export interface SubmissionChecklistItem {
  id: string
  label: string
  required: boolean
  completed: boolean
  guidance?: string | null
}

export interface SubmissionChecklistSection {
  id: string
  title: string
  items: SubmissionChecklistItem[]
}

export interface SubmissionChecklist {
  sections: SubmissionChecklistSection[]
}

export interface SubmissionChecklistCompletion {
  required_total: number
  required_completed: number
  optional_total: number
  optional_completed: number
  completion_score: number
  ready: boolean
  blocking_items: string[]
}

export interface SubmissionPackageGateCheck {
  package_id: string
  project_id: string
  status: string
  review_cycle_linked: boolean
  review_cycle_closed: boolean
  review_cycle_snapshot_id: string | null
  snapshot_bound: boolean
  required_artifacts_total: number
  required_artifacts_included: number
  missing_required_artifacts: string[]
  checklist_required_total?: number
  checklist_required_completed?: number
  checklist_completion_score?: number
  checklist_blocking_items?: string[]
  checks_passed: boolean
  blocking_reasons: string[]
}

export interface SubmissionPackageArtifact {
  id: string
  submission_package_id: string
  artifact_type: string
  name: string
  file_path: string | null
  link_url: string | null
  required: boolean
  included: boolean
  notes: string | null
  created_at: string
}

export interface MaintenancePlan {
  id: string
  organization_id: string | null
  jurisdiction_id: string
  document_id: string | null
  certification_project_id?: string | null
  name: string
  cadence_days: number
  reminder_days: number
  escalation_days: number
  next_run_at: string | null
  last_run_at: string | null
  status: 'active' | 'paused' | 'archived' | string
  auto_generated: boolean
  owner_id: string | null
  created_by: string | null
  created_at: string
}

export interface MaintenanceEvent {
  id: string
  maintenance_plan_id: string
  review_cycle_id: string | null
  event_type: 'generated' | 'reminder' | 'escalation' | 'closed' | string
  due_at: string | null
  sent_at: string | null
  status: string
  created_at: string
}

export interface EvidenceItem {
  id: string
  organization_id: string | null
  requirement_id: string
  evidence_type: string
  title: string
  body: string | null
  file_path: string | null
  link_url: string | null
  owner_id: string | null
  reviewer_id: string | null
  approved_by: string | null
  review_status: 'draft' | 'in_review' | 'approved' | 'rejected' | string
  valid_from: string | null
  valid_to: string | null
  approved_at: string | null
  expires_in_days: number | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface EvidenceValidation {
  id: string
  evidence_item_id: string
  validator_id: string | null
  validation_status: 'pass' | 'fail' | 'needs_update' | string
  comment: string | null
  created_at: string
}

export interface IntegrationConnection {
  id: string
  organization_id: string | null
  provider: 'jira' | 'confluence' | 'github' | 'webhook' | string
  name: string
  config_json: string | null
  enabled: boolean
  last_sync_at: string | null
  last_sync_status: string | null
  last_sync_message: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface ExportManifest {
  id: string
  organization_id: string | null
  scope_type: 'snapshot' | 'submission_package' | 'report_bundle' | string
  scope_id: string
  payload_json: string
  hash_algo: string
  signature: string
  signed_by: string | null
  created_at: string
}

export interface LoginHistoryEntry {
  id: string
  user_id: string
  ip_address: string | null
  user_agent: string | null
  timestamp: string
}

export interface ProgramStageCheck {
  code: string
  label: string
  passed: boolean
  severity: 'error' | 'warning' | string
  reason: string | null
  cta_label: string | null
  cta_path: string | null
}

export interface ProgramGateBlocker {
  code: string
  reason: string
  cta_label: string | null
  cta_path: string | null
}

export interface ProgramStageState {
  stage: string
  title: string
  order: number
  state: 'completed' | 'in_progress' | 'ready' | 'blocked' | 'upcoming' | string
  ready_to_advance: boolean
  checks: ProgramStageCheck[]
}

export interface ProgramStageReadiness {
  ready: boolean
  blocker_count: number
}

export interface ProgramWorkspaceProjectDeepLinks {
  project: string
  review_cycle: string | null
  submission_package: string | null
}

export interface ProgramWorkspaceProjectSummary {
  project_id: string
  project_name: string
  jurisdiction_id: string
  stage: string
  status: string
  target_submission_date: string | null
  stage_states: ProgramStageState[]
  current_stage_readiness: ProgramStageReadiness
  blockers: ProgramGateBlocker[]
  deep_links: ProgramWorkspaceProjectDeepLinks
}

export interface ProgramWorkspaceAction {
  id: string
  project_id: string
  stage: string
  priority: 'high' | 'medium' | 'low' | string
  title: string
  summary: string
  cta_label: string
  cta_path: string
  role_scope: string[]
}

export interface ProgramWorkspaceSummary {
  generated_at: string
  jurisdiction_id: string | null
  items: ProgramWorkspaceProjectSummary[]
  next_actions: ProgramWorkspaceAction[]
}

export interface DashboardData {
  generated_at: string
  kpis: {
    overall: {
      total: number
      evidenced: number
      percentage: number
    }
    mandatory: {
      total: number
      evidenced: number
      percentage: number
    }
    at_risk_count: number
    by_status: Array<{
      status: string
      total: number
      percentage_of_total: number
    }>
  }
  breakdowns: {
    by_document: Array<{
      document_id: string
      name: string
      document_type: string
      total: number
      evidenced: number
      percentage: number
    }>
    by_document_type: Array<{
      document_type: string
      total: number
      evidenced: number
      percentage: number
    }>
    by_requirement_type: Array<{
      requirement_type: string
      total: number
      evidenced: number
      percentage: number
    }>
  }
  my_work: {
    assigned_requirements: {
      total: number
      by_status: Array<{
        status: string
        total: number
        percentage_of_total: number
      }>
      items: Array<{
        action_reasons?: string[]
        requirement_id: string
        reference_id: string
        title?: string | null
        document_name: string
        status: string
        assigned_to?: string | null
        last_changed_at?: string | null
      }>
    }
    assigned_review_items: {
      total: number
      by_status: Array<{
        status: string
        total: number
        percentage_of_total: number
      }>
      items: Array<{
        cycle_id: string
        cycle_name: string
        deadline?: string | null
        action_reasons?: string[]
        review_item_id: string
        requirement_reference_id: string
        requirement_title?: string | null
        review_status: string
        project_id?: string | null
        project_name?: string | null
        change_entry_id?: string | null
        change_title?: string | null
      }>
    }
    assigned_forms?: {
      total: number
      items: Array<{
        case_id: string
        name: string
        kind?: string
        status: string
        owner_id: string | null
        due_date: string | null
        application_id?: string | null
        application_name?: string | null
        project_id?: string | null
        project_name?: string | null
      }>
    }
    authority_queries?: {
      total: number
      items: Array<{
        query_id: string
        application_id: string
        application_name: string
        question: string
        status: string
        owner_id: string | null
        due_date: string | null
      }>
    }
  }
  review_cycles: {
    active: Array<{
      id: string
      name: string
      deadline: string | null
      progress: {
        total: number
        completed: number
        pending: number
      }
      due_in_days: number | null
      my_pending_count: number | null
    }>
  }
  snapshots: Array<{
    id: string
    name: string
    snapshot_type: string
    total_requirements: number
    evidenced_requirements: number
    created_at: string
  }>
  recent_activity: AuditLogEntry[]
  queues?: {
    document_status_counts: Array<{ status: string; total: number }>
    documents_pending_approval: Array<{
      id: string
      name?: string | null
      filename: string
      document_type: string
      status: string
      created_at: string
      missing_fields: string[]
    }>
    documents_needing_submission: Array<{
      id: string
      name?: string | null
      filename: string
      document_type: string
      status: string
      created_at: string
      missing_fields: string[]
    }>
    documents_needing_extraction: Array<{
      id: string
      name?: string | null
      filename: string
      document_type: string
      status: string
      created_at: string
      missing_fields: string[]
    }>
    extraction_failures_recent: {
      last_7_days: number
      last_30_days: number
      items: Array<{
        run_id: string
        document_id: string
        document_name: string
        status: string
        error_message?: string | null
        error_page?: number | null
        created_at: string
        completed_at?: string | null
      }>
    }
  } | null
  data_quality?: {
    evidenced_without_evidence: Array<{
      requirement_id: string
      reference_id: string
      title?: string | null
      document_name: string
      current_status: string
      evidence_counts: { notes: number; files: number; links: number }
    }>
    evidence_without_evidenced_status: Array<{
      requirement_id: string
      reference_id: string
      title?: string | null
      document_name: string
      current_status: string
      evidence_counts: { notes: number; files: number; links: number }
    }>
    unassigned_requirements_count: number
    unlinked_requirements_count: number
  } | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
}

export interface TokenResponse {
  token_type: string
}
