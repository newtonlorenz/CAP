import type { ResourceAccess } from './access'
import type { PreparationEvidence } from './preparation'

export type CoverageStatus = 'unreviewed' | 'partial' | 'sufficient'
export interface DocumentationRegister {
  id: string; name: string; jurisdiction_id: string; description: string | null; revision: number; access: ResourceAccess
  process?: DocumentationProcess | null
}
export interface DocumentationProcess { kind: 'review' | 'application'; id?: string; name?: string; href?: string; project_id?: string | null; project_name?: string | null; available: boolean; status?: string }
export interface ProcessEvidence {
  kind: 'shared_evidence' | 'preparation_evidence' | 'review_file'; evidence_id?: string; file_id?: string; id?: string
  title: string; evidence_kind?: 'file' | 'note' | 'link'; filename?: string | null; locator?: string | null; rationale?: string
  body?: string | null; link_url?: string | null; download_href?: string | null; href?: string; problems?: string[]
}
export interface ProcessTarget {
  id?: string; available: boolean; kind?: 'review_item' | 'application_response'; review_item_id?: string; review_cycle_id?: string
  case_id?: string; field_key?: string; requirement_id?: string; requirement_set_version_id?: string
  reference_id?: string; title?: string; href?: string; owner_name?: string; case_name?: string; set_name?: string; version_number?: number
  process_name?: string; requirement_text?: string; requirement_text_truncated?: boolean
  requirement_context?: { reference_id: string; title: string }[]
  collection?: {
    application_status?: string; items: ProcessEvidence[]; readonly: boolean; can_edit?: boolean; unavailable?: boolean; warning?: string | null
    has_review_notes?: boolean; review_notes_summary?: string; shared_evidence_uri?: string; legacy_files_uri?: string; evidence_changed_at?: string | null
    revision?: number; case_revision?: number; owner_write_href?: string
    response?: { value: string | number | boolean | null; not_applicable_reason: string | null; evidence_ids: string[]; accepted_at?: string | null }
  }
}
export interface DocumentationSection { id: string; register_id: string; name: string; position: number; register_revision?: number }
export interface RequirementLink {
  requirement_id: string; requirement_set_version_id: string; reference_id?: string; version_number?: number; set_name?: string; title?: string; text?: string; stale?: boolean; is_current?: boolean
}
export interface CoverageLink {
  evidence_id: string; locator: string; scope: string; period: string; rationale: string
  evidence?: PreparationEvidence; title?: string; reasons?: string[]; stale?: boolean; expired?: boolean; problems?: string[]; is_current?: boolean
}
export interface NativeReference { component_id?: string; change_id?: string; jira_key?: string; jira_url?: string; kind: string; resource_id?: string; reference?: string; label?: string; url?: string; locator?: string; rationale?: string }
export interface DocumentationExpectation {
  review_cycle_id?: string | null; process?: DocumentationProcess | null; process_inherited?: boolean
  process_targets?: ProcessTarget[]; process_mapping_status?: 'unmapped' | 'mapped' | 'unavailable'
  source_rows?: { sheet: string; row_number: number; metadata: Record<string, unknown>; original_headers?: string[]; original_values?: unknown[] }[]
  section_name?: string | null; section_id?: string | null; required_documentation?: string | null; document_name?: string | null
  standalone_coverage_warning?: string | null; owner_name?: string; effective_coverage_status?: CoverageStatus; coverage_warning?: string | null
  id: string; register_id: string; title: string; description: string | null; category: string | null
  interpretation: string | null; basis: string | null; applicability: 'unknown' | 'applicable' | 'not_applicable'
  not_applicable_reason: string | null; responsible_party: string | null; owner_id: string | null
  source_reference: string | null; project_id: string | null; revision: number
  coverage_status: CoverageStatus; review_rationale: string | null; reviewed_by: string | null; reviewed_at: string | null
  requirements: RequirementLink[]; coverage: CoverageLink[]; references: NativeReference[]; reasons?: string[]
  coverage_reasons?: string[]; derived_reasons?: string[]
}
export type ExpectationDraft = Pick<DocumentationExpectation, 'title' | 'description' | 'category' | 'interpretation' | 'basis' | 'applicability' | 'not_applicable_reason' | 'responsible_party' | 'owner_id' | 'source_reference' | 'project_id' | 'section_id' | 'required_documentation' | 'document_name'>
export interface EvidenceGroup { id: string; title: string; revision: number; current_evidence_id?: string; versions: { evidence_id: string; title?: string; version?: number }[] }
