import type { PreparationCase } from './preparation'

export interface AnswerReviewFeedback {
  id: string
  comment: string
  created_by: string
  created_by_name: string | null
  created_at: string
  returned_revision: number
  resolved_at: string | null
  resolved_by: string | null
}
export type AnswerReviewStatus = 'pending_review' | 'changes_requested' | 'accepted'
export type PilotPreparationCase = Omit<PreparationCase, 'responses'> & {
  reviewer_id?: string | null
  reviewer_name?: string | null
  reviewer_source?: 'case' | 'project' | 'pack' | null
  responses: Array<PreparationCase['responses'][number] & {
    review_status?: AnswerReviewStatus
    last_saved_at?: string | null
    last_saved_by?: string | null
    feedback?: AnswerReviewFeedback[]
  }>
}
export interface ReviewQueueItem {
  change_kind?: 'evidence_changed' | 'answer_updated' | 'new_answer' | null
  case_id: string
  case_name: string
  jurisdiction_id: string
  field_key: string
  question: string
  section: string
  guidance: string | null
  revision: number
  review_status: AnswerReviewStatus
  reviewer_id: string | null
  reviewer_name: string | null
  owner_id: string | null
  owner_name: string | null
  due_date: string | null
  last_saved_at: string | null
  last_saved_by: string | null
  open_feedback_count: number
  can_approve: boolean
}
export interface ReviewQueueFilters {
  jurisdiction_id?: string
  case_id?: string
  reviewer_id?: string
  status?: 'pending_review' | 'changes_requested' | 'all'
  unassigned?: boolean
  overdue?: boolean
  include_excluded?: boolean
  changed_evidence?: boolean
  q?: string
  skip?: number
  limit?: number
}
export interface PilotPage<T> { items: T[]; total: number; skip: number; limit: number }
export type TeamWorkKind = 'requirement' | 'review' | 'form' | 'answer_review' | 'authority_query' | 'change'
export interface TeamWorkItem {
  id: string
  kind: TeamWorkKind
  title: string
  context: string
  status: string
  action_label: string
  owner_id: string | null
  owner_name: string | null
  due_date: string | null
  overdue: boolean
  href: string
  case_id?: string
  field_key?: string
  jurisdiction_id: string
}
export interface TeamWorkFilters {
  sort_by?: 'programme' | 'owner' | 'priority'
  context?: string
  jurisdiction_id?: string
  kind?: TeamWorkKind
  owner_id?: string
  unassigned?: boolean
  overdue?: boolean
  q?: string
  skip?: number
  limit?: number
}
export interface TeamWorkPage extends PilotPage<TeamWorkItem> {
  contexts: string[]
  counts: { total: number; overdue: number; unassigned: number; by_kind: Record<TeamWorkKind, number> }
  people: Array<{ id: string | null; name: string; total: number; overdue: number }>
}
export interface AnswerHistoryItem {
  id: string
  action: string
  user_name: string | null
  timestamp: string
  details: { old_value: unknown; new_value: unknown }
}
