export type RegulatoryScope = 'unknown' | 'base_platform' | 'rng' | 'game' | 'game_platform' | 'other'
export type ResponsibilityRole = 'unknown' | 'licensed_operator' | 'licensed_game_supplier' | 'unlicensed_subcontractor'
export type ReadinessCheck = { ready: boolean; reasons: Array<{ code: string; message: string }> }
export type ProgrammeReadiness = ReadinessCheck & { certification_due_at?: string | null; report_due_at?: string | null }
export type ChangeReadiness = {
  approval: ReadinessCheck; implementation: ReadinessCheck; verification: ReadinessCheck
  certification_status?: string; certification_completed?: boolean; certification_overdue?: boolean
  certification_due_at?: string | null; release_ready: boolean; rule_profile: string
}
export type ChangeCompliance = {
  evaluation?: { status?: string; provider?: string; reference?: string; evidence?: string; approved_at?: string | null }
  certification?: { continuation_confirmed?: boolean; continuation_started_at?: string | null; continuation_evidence?: string; timing?: 'during' | 'direct_continuation'; planned_at?: string | null; schedule_reference?: string; status?: string; provider?: string; reference?: string; evidence?: string; certified_at?: string | null; component_versions?: Record<string, string>; component_checksums?: Record<string, string> }
  deferral?: { permission_reference?: string; permission_evidence?: string; qa_function?: string; qa_qualified?: boolean; qa_separate?: boolean; due_at?: string | null }
  regulator?: { rng_notified_at?: string | null; rng_reference?: string; game_approval_required?: boolean | null; game_approval_reference?: string; game_approval_at?: string | null; game_approval_basis?: string; error_identified_at?: string | null; error_notified_at?: string | null; error_reference?: string; error_notice_immediate?: boolean | null }
  supplier?: { recommended_at?: string | null; delay_justification?: string; whole_system_evaluation?: string; rejection_attestation?: string; rejection_ato?: string; rejection_evidence?: string }
  annual_certification_provider?: string; annual_certification_evidence?: string
  annual_certification_reference?: string
  annual_certification_due_at?: string | null
  annual_certification_anchor_at?: string | null
  integration_procedure_reference?: string
  integration_requirement_references?: string[]
}
export type ProgrammeAssurance = {
  change_plan_reference?: string; responsible_owner?: string
  change_plan_approved_by?: string; change_plan_approved_at?: string | null; change_plan_approval_evidence?: string
  ato_accreditation_reference?: string; ato_accreditation_evidence?: string; renewal_report_due_at?: string | null
  integration_procedure_reference?: string; integration_procedure_approved_at?: string | null; integration_procedure_ato?: string
  latest_certification_at?: string | null; certification_reference?: string; certification_evidence?: string; certification_ato?: string
  report_submitted_at?: string | null; cadence_anchor_at?: string | null; renewal_due_at?: string | null
  postponed_until?: string | null; postponement_notified_at?: string | null; postponement_reference?: string
}
