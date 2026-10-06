import type { ResourceAccess } from './access'
export type PreparationKind =
  | 'licence_application'
  | 'certification'
  | 'pre_audit'
  | 'audit'
  | 'evidence_collection'
  | 'questionnaire'
export type PreparationFieldType =
  | 'text'
  | 'multiline'
  | 'yes_no'
  | 'date'
  | 'number'
  | 'choice'
  | 'evidence'
export type PreparationValue = string | number | boolean | null

export interface PreparationFieldSource {
  kind: 'requirement' | 'extracted_requirement'
  document_id: string
  document_name: string
  document_status: string
  jurisdiction_id: string
  requirement_id: string | null
  extracted_requirement_id: string | null
  extraction_run_id: string | null
  extraction_status: string | null
  extraction_review_status: string | null
  requirement_set_version_id: string | null
  version_number: number | null
  version_status: string | null
  reference_id: string
  source_extraction_id: string | null
  text_sha256: string
}

export interface PreparationField {
  key: string
  label: string
  section: string
  help_text: string | null
  type: PreparationFieldType
  required: boolean
  options: string[]
  reuse_key: string | null
  source?: PreparationFieldSource | null
}
export interface PreparationRequirementsPreview {
  source: {
    kind: 'requirements' | 'extracted_requirements'
    document_id: string
    name: string
    status: string
    jurisdiction_id: string
    version_id: string | null
    version_number: number | null
    version_status: string | null
    has_source: boolean
    extraction_run_id: string | null
    extraction_status: string | null
  }
  fields: PreparationField[]
  unavailable: { requirement_id: string | null; reference_id: string; reason: string }[]
  warnings: string[]
  total: number
  skip: number
  limit: number
}
export interface PreparationTemplate {
  id: string
  name: string
  description: string | null
  kind: PreparationKind
  fields: PreparationField[]
  revision: number
  active: boolean
  created_at: string
  updated_at: string
}
export type PreparationStarter = Pick<
  PreparationTemplate,
  'name' | 'description' | 'kind' | 'fields'
>
export interface PreparationResponse {
  field_key: string
  value: PreparationValue
  not_applicable_reason: string | null
  evidence_ids: string[]
  accepted_by: string | null
  accepted_at: string | null
  reused_from_case_id: string | null
  reused_from_field_key: string | null
}
export interface PreparationBlocker {
  field_key: string
  code: string
  message: string
}
export interface PreparationReadiness {
  required_count: number
  answered_count: number
  accepted_count: number
  blockers: PreparationBlocker[]
  ready: boolean
}
export interface PreparationCase {
  access?: ResourceAccess
  summary_only?: boolean
  id: string
  name: string
  kind: PreparationKind
  jurisdiction_id: string
  project_id: string | null
  owner_id: string | null
  due_date: string | null
  status: 'active' | 'archived'
  revision: number
  template_id: string | null
  template_name: string
  template_revision: number
  original_evidence_ids?: string[]
  fields: PreparationField[]
  created_at: string
  updated_at: string
  readiness: PreparationReadiness
  responses: PreparationResponse[]
}
export interface PreparationCaseSummary
  extends Omit<PreparationCase, 'fields' | 'responses'> {
  fields?: PreparationField[]
  responses?: PreparationResponse[]
}
export interface PreparationEvidence {
  access?: ResourceAccess
  summary_only?: boolean
  id: string
  title: string
  kind: 'note' | 'link' | 'file'
  body: string | null
  link_url: string | null
  filename: string | null
  sha256: string | null
  size_bytes: number | null
  valid_from: string | null
  valid_until: string | null
  archived: boolean
  created_at: string
  created_by: string
}
export interface PreparationReuseSuggestion {
  source_case_id: string
  source_case_name: string
  source_jurisdiction_id: string
  source_field_key: string
  value: PreparationValue
  accepted_at: string | null
}
export interface PreparationList<T> {
  items: T[]
  total: number
}

export const PREPARATION_KINDS: PreparationKind[] = [
  'licence_application',
  'certification',
  'pre_audit',
  'audit',
  'evidence_collection',
  'questionnaire',
]
export const PREPARATION_FIELD_TYPES: PreparationFieldType[] = [
  'text',
  'multiline',
  'yes_no',
  'date',
  'number',
  'choice',
  'evidence',
]
export const preparationLabel = (value: string) =>
  value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export function nextPreparationFieldKey(fields: PreparationField[]): string {
  const used = new Set(fields.map((field) => field.key))
  let index = 1
  while (used.has(`field_${index}`)) index += 1
  return `field_${index}`
}

export function isEvidenceCurrent(
  evidence: PreparationEvidence,
  today = new Date().toISOString().slice(0, 10),
): boolean {
  return (
    !evidence.archived &&
    (!evidence.valid_from || evidence.valid_from <= today) &&
    (!evidence.valid_until || evidence.valid_until >= today)
  )
}

export function parseFieldValue(
  type: PreparationFieldType,
  raw: string,
): PreparationValue {
  if (raw === '') return null
  if (type === 'yes_no') return raw === 'true'
  if (type === 'number') return Number(raw)
  return raw
}

export function fieldValueToString(value: PreparationValue): string {
  return value === null ? '' : String(value)
}

export type ImportEnhancement = {
  status: 'completed' | 'partial' | 'skipped'
  suggested_mapping: Partial<Record<'question' | 'reference' | 'section' | 'type' | 'options' | 'required' | 'help', number>>
  field_suggestions: { row_index: number; type?: PreparationFieldType | null; required?: boolean | null; duplicate_of?: number | null; confidence: number }[]
  warnings: string[]
  usage: Record<string, number>
  model: string | null
  input_fingerprint: string
}
export type ImportEnhancementRequest = {
  headers: string[]
  rows: { row_index: number; question: string; help: string; explicit_type: boolean; explicit_required: boolean }[]
  header_row: number
  mapping: Record<string, number>
  external_processing_confirmed: boolean
  settings_revision: number
}
