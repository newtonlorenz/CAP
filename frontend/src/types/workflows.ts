import type { MaintenancePlan, ReviewCycle } from './index'

export interface ChangeImpactInput {
  requirement_set_version_id: string
  requirement_id?: string | null
  certification_project_id?: string | null
  rationale?: string
}
export interface ChangeImpact extends ChangeImpactInput {
  id: string
  requirement_id: string | null
  certification_project_id: string | null
  rationale: string
  set_name: string
  version_number: number
  project_name: string | null
  requirement_reference_id?: string | null
  requirement_title?: string | null
}
export type ContextAssessment = ReviewCycle & { change_entry_id?: string | null }
export type ProjectMaintenancePlan = MaintenancePlan & { certification_project_id?: string | null }
export interface MaintenanceRunSummary {
  generated_cycles: number
  generated_items: number
}
