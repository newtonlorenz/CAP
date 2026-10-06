type SoAField = {
  key: string
  label: string
}

type SoAFieldGroup = {
  id: string
  label: string
  fields: SoAField[]
}

export const SOA_FIELD_GROUPS: SoAFieldGroup[] = [
  {
    id: 'jurisdiction',
    label: 'Jurisdiction',
    fields: [
      { key: 'jurisdiction_code', label: 'Jurisdiction Code' },
      { key: 'jurisdiction_name', label: 'Jurisdiction Name' },
      { key: 'jurisdiction_regulator_name', label: 'Jurisdiction Regulator Name' },
    ],
  },
  {
    id: 'review-cycle',
    label: 'Review',
    fields: [
      { key: 'review_cycle_id', label: 'Review ID' },
      { key: 'review_cycle_name', label: 'Review Name' },
      { key: 'review_cycle_description', label: 'Review Description' },
      { key: 'review_cycle_scope', label: 'Review Scope' },
      { key: 'review_cycle_scope_filter', label: 'Review Scope Filter' },
      { key: 'review_cycle_deadline', label: 'Review Deadline' },
      { key: 'review_cycle_status', label: 'Review Status' },
      { key: 'review_cycle_created_by', label: 'Review Created By' },
      { key: 'review_cycle_closed_at', label: 'Review Closed At' },
      { key: 'review_cycle_closed_by', label: 'Review Closed By' },
      { key: 'review_cycle_snapshot_id', label: 'Review Snapshot ID' },
      { key: 'review_cycle_created_at', label: 'Review Created At' },
    ],
  },
  {
    id: 'review-item',
    label: 'Review Item',
    fields: [
      { key: 'reviewer_name', label: 'Reviewed By' },
      { key: 'responsible_name', label: 'Responsible Person' },
      { key: 'review_item_id', label: 'Review Item ID' },
      { key: 'review_item_review_status', label: 'Review Item Review Status' },
      { key: 'review_item_assigned_reviewer_id', label: 'Assigned Reviewer ID' },
      { key: 'review_item_reviewer_id', label: 'Reviewer ID' },
      { key: 'review_item_review_evidence', label: 'Review Evidence' },
      { key: 'review_item_jira_issue_key', label: 'Jira Issue Key' },
      { key: 'review_item_jira_issue_url', label: 'Jira Issue URL' },
      { key: 'review_item_jira_status', label: 'Jira Status' },
      { key: 'review_item_jira_summary', label: 'Jira Summary' },
      { key: 'review_item_jira_assignee', label: 'Jira Assignee' },
      { key: 'review_item_jira_priority', label: 'Jira Priority' },
      { key: 'review_item_jira_updated_at', label: 'Jira Updated At' },
      { key: 'review_item_jira_synced_at', label: 'Jira Synced At' },
      { key: 'review_item_jira_sync_error', label: 'Jira Sync Error' },
      { key: 'review_item_reviewed_at', label: 'Reviewed At' },
      { key: 'review_item_created_at', label: 'Review Item Created At' },
    ],
  },
  {
    id: 'requirement',
    label: 'Requirement',
    fields: [
      { key: 'requirement_id', label: 'Requirement ID' },
      { key: 'requirement_document_id', label: 'Requirement Document ID' },
      { key: 'requirement_reference_id', label: 'Requirement Reference ID' },
      { key: 'requirement_title', label: 'Requirement Title' },
      { key: 'requirement_text', label: 'Requirement Text' },
      { key: 'requirement_type', label: 'Requirement Type' },
      { key: 'requirement_parent_id', label: 'Requirement Parent ID' },
      { key: 'requirement_default_owner_id', label: 'Requirement Default Owner ID' },
      { key: 'requirement_active', label: 'Requirement Active' },
      { key: 'requirement_version', label: 'Requirement Version' },
      { key: 'requirement_sort_order', label: 'Requirement Sort Order' },
      { key: 'requirement_created_at', label: 'Requirement Created At' },
    ],
  },
  {
    id: 'requirement-status',
    label: 'Requirement Current Status',
    fields: [
      { key: 'requirement_current_status', label: 'Requirement Current Status' },
      { key: 'requirement_current_assigned_to', label: 'Requirement Assigned To' },
    ],
  },
  {
    id: 'document',
    label: 'Document',
    fields: [
      { key: 'baseline_version', label: 'Approved Baseline Version' },
      { key: 'source_page', label: 'Source PDF Page' },
      { key: 'document_id', label: 'Document ID' },
      { key: 'document_filename', label: 'Document Filename' },
      { key: 'document_name', label: 'Document Name' },
      { key: 'document_type', label: 'Document Type' },
      { key: 'document_version', label: 'Document Version' },
      { key: 'document_effective_date', label: 'Document Effective Date' },
      { key: 'document_status', label: 'Document Status' },
      { key: 'document_testing_frequency', label: 'Document Testing Frequency' },
      { key: 'document_uploaded_by', label: 'Document Uploaded By' },
      { key: 'document_approved_by', label: 'Document Approved By' },
      { key: 'document_current_extraction_id', label: 'Document Current Extraction ID' },
      { key: 'document_archived_at', label: 'Document Archived At' },
      { key: 'document_created_at', label: 'Document Created At' },
    ],
  },
  {
    id: 'evidence',
    label: 'Evidence Files',
    fields: [
      { key: 'evidence_file_ids', label: 'Evidence File IDs' },
      { key: 'evidence_filenames', label: 'Evidence Filenames' },
      { key: 'evidence_file_descriptions', label: 'Evidence Descriptions' },
      { key: 'evidence_uploaded_by', label: 'Evidence Uploaded By' },
      { key: 'evidence_uploaded_at', label: 'Evidence Uploaded At' },
      { key: 'evidence_file_links', label: 'Evidence File Links' },
    ],
  },
]

export const READABLE_SOA_FIELD_KEYS = [
  'requirement_reference_id', 'requirement_title', 'requirement_text', 'requirement_type',
  'requirement_current_status', 'review_item_review_status', 'review_item_review_evidence',
  'responsible_name', 'reviewer_name', 'review_item_reviewed_at', 'evidence_filenames',
  'document_name', 'document_version', 'baseline_version', 'source_page', 'review_cycle_name',
]

export const ALL_SOA_FIELD_KEYS = SOA_FIELD_GROUPS.flatMap((group) =>
  group.fields.map((field) => field.key)
)
