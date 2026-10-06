import api from './client'
import type { ChangeImpact, ChangeImpactInput, ContextAssessment, ProjectMaintenancePlan, MaintenanceRunSummary } from '../types/workflows'
import type { PaginatedResponse } from '../types'

export const workflowsApi = {
  impacts: async (changeId: string) => (await api.get<{ items: ChangeImpact[] }>(`/change-management/changes/${changeId}/impacts`)).data,
  saveImpacts: async (changeId: string, items: ChangeImpactInput[]) => (await api.put<{ items: ChangeImpact[] }>(`/change-management/changes/${changeId}/impacts`, { items })).data,
  changeAssessments: async (changeId: string) => (await api.get<{ items: ContextAssessment[] }>(`/change-management/changes/${changeId}/assessments`)).data,
  createChangeAssessments: async (changeId: string, body: { impact_ids: string[]; name: string; deadline?: string }) => (await api.post<{ items: ContextAssessment[] }>(`/change-management/changes/${changeId}/assessments`, body)).data,
  maintenancePlans: async (projectId: string) => (await api.get<PaginatedResponse<ProjectMaintenancePlan>>('/maintenance-plans', { params: { certification_project_id: projectId, limit: 1000 } })).data,
  createMaintenancePlan: async (body: { jurisdiction_id: string; certification_project_id: string; name: string; cadence_days: number; next_run_at: string; reminder_days: number; escalation_days: number }) => (await api.post<ProjectMaintenancePlan>('/maintenance-plans', body)).data,
  updateMaintenancePlan: async (id: string, body: { status: string }) => (await api.patch<ProjectMaintenancePlan>(`/maintenance-plans/${id}`, body)).data,
  runDue: async (projectId: string) => (await api.post<MaintenanceRunSummary>('/maintenance-plans/run-due', null, { params: { certification_project_id: projectId } })).data,
}
