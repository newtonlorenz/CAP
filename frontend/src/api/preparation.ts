import type { ImportEnhancement, ImportEnhancementRequest } from '../types/preparation'
import type { Visibility } from '../types/access'
import api from './client'
import type { PaginatedResponse, RequirementSetSummary, RequirementSetVersion } from '../types'
import type {
  PreparationCase,
  PreparationEvidence,
  PreparationField,
  PreparationKind,
  PreparationList,
  PreparationReuseSuggestion,
  PreparationRequirementsPreview,
  PreparationStarter,
  PreparationTemplate,
  PreparationValue,
} from '../types/preparation'

const root = '/preparation'
export const preparationApi = {
  importCapabilities: async () => (await api.get<{ jev?: { enabled: boolean; revision: number; model: string | null } }>('/capabilities')).data,
  enhanceImport: async (body: ImportEnhancementRequest) => (await api.post<ImportEnhancement>(`${root}/templates/import-enhancements`, body)).data,


  requirementSets: async (jurisdictionId: string, search = '') => {
    const params = new URLSearchParams({ jurisdiction_id: jurisdictionId, limit: '1000', include_archived_documents: 'false', include_archived_sets: 'false', include_empty_sets: 'true' })
    if (search.trim()) params.set('search', search.trim())
    return (await api.get<PaginatedResponse<RequirementSetSummary>>(`/requirements/sets?${params}`)).data
  },
  requirementVersions: async (documentId: string) =>
    (await api.get<PaginatedResponse<RequirementSetVersion>>(`/requirements/sets/${documentId}/versions`)).data,
  requirementsPreview: async (params: { document_id: string; jurisdiction_id: string; version_id?: string; skip?: number; limit?: number }) =>
    (await api.get<PreparationRequirementsPreview>(`${root}/templates/requirements-preview`, { params })).data,
  importPreview: async (file: File, sheetName?: string) => {
    const body = new FormData()
    body.append('file', file)
    if (sheetName) body.append('sheet_name', sheetName)
    return (await api.post<{ sheets: string[]; sheet_name: string; rows: string[][]; warnings: string[] }>(`${root}/templates/import-preview`, body)).data
  },
  templates: async () =>
    (
      await api.get<PreparationList<PreparationTemplate>>(
        `${root}/templates?limit=500`,
      )
    ).data,
  starters: async () =>
    (await api.get<PreparationList<PreparationStarter>>(`${root}/starters`))
      .data,
  createTemplate: async (body: {
    name: string
    description?: string
    kind: PreparationKind
    fields: PreparationField[]
  }) => (await api.post<PreparationTemplate>(`${root}/templates`, body)).data,
  updateTemplate: async (
    id: string,
    body: Partial<PreparationTemplate> & { expected_revision: number },
  ) =>
    (await api.patch<PreparationTemplate>(`${root}/templates/${id}`, body))
      .data,
  cases: async (params: URLSearchParams) =>
    (await api.get<PreparationList<PreparationCase>>(`${root}/cases?${params}`))
      .data,
  getCase: async (id: string) =>
    (await api.get<PreparationCase>(`${root}/cases/${id}`)).data,
  createCase: async (body: {
    visibility?: Visibility
    template_id?: string
    fields?: PreparationField[]
    original_evidence_ids?: string[]
    jurisdiction_id: string
    name: string
    owner_id?: string
    due_date?: string
    project_id?: string
  }) => (await api.post<PreparationCase>(`${root}/cases`, body)).data,
  updateCase: async (
    id: string,
    body: {
      expected_revision: number
      name?: string
      owner_id?: string | null
      due_date?: string | null
      project_id?: string | null
      status?: 'active' | 'archived'
    },
  ) => (await api.patch<PreparationCase>(`${root}/cases/${id}`, body)).data,
  saveResponse: async (
    id: string,
    fieldKey: string,
    body: {
      expected_revision: number
      value: PreparationValue
      not_applicable_reason: string | null
      evidence_ids: string[]
    },
  ) =>
    (
      await api.put<PreparationCase>(
        `${root}/cases/${id}/responses/${encodeURIComponent(fieldKey)}`,
        body,
      )
    ).data,
  acceptResponse: async (id: string, fieldKey: string, revision: number) =>
    (
      await api.post<PreparationCase>(
        `${root}/cases/${id}/responses/${encodeURIComponent(fieldKey)}/accept`,
        { expected_revision: revision },
      )
    ).data,
  reuseSuggestions: async (id: string, fieldKey: string) =>
    (
      await api.get<{ items: PreparationReuseSuggestion[] }>(
        `${root}/cases/${id}/reuse`,
        { params: { field_key: fieldKey } },
      )
    ).data,
  reuseResponse: async (
    id: string,
    fieldKey: string,
    body: {
      expected_revision: number
      source_case_id: string
      source_field_key: string
    },
  ) =>
    (
      await api.post<PreparationCase>(
        `${root}/cases/${id}/responses/${encodeURIComponent(fieldKey)}/reuse`,
        body,
      )
    ).data,
  evidence: async (params: URLSearchParams) =>
    (
      await api.get<PreparationList<PreparationEvidence>>(
        `${root}/evidence?${params}`,
      )
    ).data,
  getEvidence: async (id: string) =>
    (await api.get<PreparationEvidence>(`${root}/evidence/${id}`)).data,
  createEvidence: async (body: {
    visibility?: Visibility
    title: string
    kind: 'note' | 'link'
    body?: string
    link_url?: string
    valid_from?: string
    valid_until?: string
  }) => (await api.post<PreparationEvidence>(`${root}/evidence`, body)).data,
  uploadEvidence: async (body: FormData) =>
    (await api.post<PreparationEvidence>(`${root}/evidence/upload`, body)).data,
  archiveEvidence: async (id: string, archived: boolean) =>
    (
      await api.patch<PreparationEvidence>(`${root}/evidence/${id}`, {
        archived,
      })
    ).data,
  download: async (path: string, filename: string) => {
    const response = await api.get<Blob>(`${root}/${path}`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
