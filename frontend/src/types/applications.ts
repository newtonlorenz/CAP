import type { ResourceAccess, Visibility } from './access'
export type ApplicationScope = 'annex_only' | 'licence' | 'full_pack'
export type ApplicationStatus = 'draft' | 'in_review' | 'approved' | 'submitted' | 'follow_up' | 'completed'
export interface ApplicationMetadata {
  visibility?: Visibility
  name: string
  scope: ApplicationScope
  jurisdiction_id: string
  applicant: string | null
  authority: string | null
  description: string | null
  owner_id: string | null
  due_date: string | null
}
export interface SetupAnswers {
  foreign_applicant: boolean
  foreign_people: boolean
  representative_used: boolean
  people: string[]
}
export interface MarketProfileItem {
  key: string
  name: string
  kind: 'form' | 'annex' | 'document'
  required: boolean
  condition?: 'foreign_applicant' | 'foreign_people' | 'representative_used' | null
  repeat_for?: 'people' | null
  source_url?: string | null
  guidance?: string | null
}
export interface MarketProfile {
  code: string
  version: string
  revision: number
  status: 'published' | 'draft'
  label: string
  authority: string
  setup_questions: Record<string, unknown>[]
  items: MarketProfileItem[]
  guidance: string[]
  source_urls: string[]
  checked_at: string | null
}
export interface GuidedItem {
  name: string
  kind: MarketProfileItem['kind']
  required: boolean
  included: boolean
  owner_id: string | null
  due_date: string | null
  profile_item_key: string | null
}
export interface GuidedApplicationInput extends ApplicationMetadata {
  profile_version: string
  setup_answers: SetupAnswers
  items: GuidedItem[]
}
export interface ApplicationBlocker {
  component_id?: string | null
  case_id?: string | null
  field_key?: string | null
  field_label?: string | null
  field_type?: string | null
  section?: string | null
  code: string
  message: string
}
export interface ApplicationComponent {
  id: string
  name: string
  kind: 'form' | 'annex' | 'document'
  required: boolean
  included: boolean
  owner_id: string | null
  due_date: string | null
  case_id: string | null
  evidence_id: string | null
  case_name: string | null
  ready: boolean
  blockers: ApplicationBlocker[]
  form_field_count?: number
  profile_item_key?: string | null
}
export interface ApplicationFollowup {
  id: string
  question: string
  owner_id: string | null
  due_date: string | null
  response: string | null
  evidence_ids: string[]
  status: 'open' | 'resolved'
  resolved_at: string | null
  created_at: string
}
export interface ApplicationSnapshot {
  id: string
  version: number
  approved_at: string
  approved_by: string
  submitted_at: string | null
  reference: string | null
  notes: string | null
  sha256: string
  size_bytes: number
}
export interface LicenceApplication extends ApplicationMetadata {
  profile_snapshot?: MarketProfile | null
  setup_answers?: SetupAnswers | null
  access?: ResourceAccess
  summary_only?: boolean
  id: string
  status: ApplicationStatus
  revision: number
  outcome: string | null
  created_at: string
  updated_at: string
  components: ApplicationComponent[]
  followups: ApplicationFollowup[]
  snapshots: ApplicationSnapshot[]
  history: { id: string; action: string; user_name: string | null; timestamp: string; details: Record<string, unknown> }[]
  readiness: { ready: boolean; required_count: number; ready_count: number; blockers: ApplicationBlocker[] }
}
export type ComponentInput = Pick<ApplicationComponent, 'name' | 'kind' | 'required' | 'included' | 'owner_id' | 'due_date' | 'case_id' | 'evidence_id'> & { template_id?: string; form_fields?: import('./preparation').PreparationField[]; original_evidence_ids?: string[] }
export const scopeLabels: Record<ApplicationScope, string> = { annex_only: 'Annexes only', licence: 'Licence application', full_pack: 'Full application pack' }
export const statusLabels: Record<ApplicationStatus, string> = { draft: 'Draft', in_review: 'In review', approved: 'Approved internally', submitted: 'Submitted', follow_up: 'Follow-up', completed: 'Completed' }
