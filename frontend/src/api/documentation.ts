import api from './client'
import type { PaginatedResponse } from '../types'
import type { DocumentationRegister, DocumentationExpectation, DocumentationSection, DocumentationProcess, ProcessTarget, ExpectationDraft, CoverageLink, CoverageStatus, RequirementLink, EvidenceGroup } from '../types/documentation'

const root = '/documentation'
export const documentationApi = {
  registers: async (jurisdiction_id: string) => (await api.get<PaginatedResponse<DocumentationRegister>>(`${root}/registers`, { params: { jurisdiction_id, limit: 500 } })).data,
  createRegister: async (body: { name: string; description?: string; jurisdiction_id: string; visibility: string }) => (await api.post<DocumentationRegister>(`${root}/registers`, body)).data,
  sections: async (id: string) => (await api.get<PaginatedResponse<DocumentationSection> & { revision: number }>(`${root}/registers/${id}/sections`)).data,
  createSection: async (id: string, revision: number, name: string) => (await api.post<DocumentationSection>(`${root}/registers/${id}/sections`, { revision, name })).data,
  processOptions: async (id: string, q: string, skip: number) => (await api.get<{ review_cycles: PaginatedResponse<DocumentationProcess>; applications: PaginatedResponse<DocumentationProcess> }>(`${root}/registers/${id}/process-options`, { params: { q, skip, limit: 100 } })).data,
  linkProcess: async (id: string, revision: number, process: DocumentationProcess | null, clearTargets = false) => (await api.put<DocumentationRegister>(`${root}/registers/${id}/process`, { revision, clear_targets: clearTargets, review_cycle_id: process?.kind === 'review' ? process.id : null, application_id: process?.kind === 'application' ? process.id : null })).data,
  rowReviewOptions: async (id: string, q: string, skip: number) => (await api.get<PaginatedResponse<DocumentationProcess>>(`${root}/expectations/${id}/review-options`, { params: { q, skip, limit: 100 } })).data,
  rowProcessTargets: async (id: string, q: string, skip: number) => (await api.get<PaginatedResponse<ProcessTarget>>(`${root}/expectations/${id}/process-targets`, { params: { q, skip, limit: 100 } })).data,
  linkRowReview: async (id: string, revision: number, review_cycle_id: string | null, clear_targets: boolean) => (await api.put<DocumentationExpectation>(`${root}/expectations/${id}/review-process`, { revision, review_cycle_id, clear_targets })).data,
  linkTargets: async (id: string, revision: number, targets: ProcessTarget[]) => (await api.put<DocumentationExpectation>(`${root}/expectations/${id}/process-targets`, { revision, targets: targets.map(target => target.kind === 'review_item' ? { review_item_id: target.review_item_id, requirement_id: target.requirement_id, requirement_set_version_id: target.requirement_set_version_id } : { case_id: target.case_id, field_key: target.field_key, requirement_id: target.requirement_id, requirement_set_version_id: target.requirement_set_version_id }) })).data,
  expectations: async (id: string, params: Record<string, string> = {}) => (await api.get<PaginatedResponse<DocumentationExpectation>>(`${root}/registers/${id}/expectations`, { params: { limit: 500, ...params } })).data,
  createExpectation: async (id: string, body: ExpectationDraft) => (await api.post<DocumentationExpectation>(`${root}/registers/${id}/expectations`, body)).data,
  updateExpectation: async (id: string, revision: number, body: Partial<ExpectationDraft>) => (await api.patch<DocumentationExpectation>(`${root}/expectations/${id}`, { revision, ...body })).data,
  requirements: async (id: string, revision: number, links: RequirementLink[]) => (await api.put<DocumentationExpectation>(`${root}/expectations/${id}/requirements`, { revision, links: links.map(({ requirement_id, requirement_set_version_id }) => ({ requirement_id, requirement_set_version_id })) })).data,
  coverage: async (id: string, revision: number, links: CoverageLink[]) => (await api.put<DocumentationExpectation>(`${root}/expectations/${id}/coverage`, { revision, links: links.map(({ evidence_id, locator, scope, period, rationale }) => ({ evidence_id, locator, scope, period, rationale })) })).data,
  references: async (id: string, revision: number, body: { component_ids: string[]; change_ids: string[]; jira_references: { key: string; url?: string }[] }) => (await api.put<DocumentationExpectation>(`${root}/expectations/${id}/references`, { revision, ...body })).data,
  review: async (id: string, revision: number, status: CoverageStatus, rationale: string) => (await api.post<DocumentationExpectation>(`${root}/expectations/${id}/review`, { revision, status, rationale })).data,
  evidenceGroups: async (id: string) => (await api.get<PaginatedResponse<EvidenceGroup>>(`${root}/registers/${id}/evidence-groups`, { params: { limit: 500 } })).data,
  createEvidenceGroup: async (id: string, title: string, evidence_id: string) => (await api.post<EvidenceGroup>(`${root}/registers/${id}/evidence-groups`, { title, evidence_id })).data,
  addEvidenceVersion: async (id: string, revision: number, evidence_id: string) => (await api.post<EvidenceGroup>(`${root}/evidence-groups/${id}/versions`, { revision, evidence_id })).data,
}
