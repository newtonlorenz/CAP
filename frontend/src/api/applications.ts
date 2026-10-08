import api from './client'
import type { ApplicationFollowup, ApplicationMetadata, ComponentInput, GuidedApplicationInput, LicenceApplication, MarketProfile } from '../types/applications'
import type { PreparationList } from '../types/preparation'
const root = '/applications'
export const applicationsApi = {
  list: async (params: URLSearchParams) => (await api.get<PreparationList<LicenceApplication>>(`${root}?${params}`)).data,
  get: async (id: string) => (await api.get<LicenceApplication>(`${root}/${id}`)).data,
  create: async (body: ApplicationMetadata) => (await api.post<LicenceApplication>(root, body)).data,
  guidedCreate: async (body: GuidedApplicationInput) => (await api.post<LicenceApplication>(`${root}/guided`, body)).data,
  marketProfile: async (jurisdictionId: string) => (await api.get<MarketProfile>(`${root}/market-profile`, { params: { jurisdiction_id: jurisdictionId } })).data,
  updateMarketProfile: async (body: Omit<MarketProfile, 'code' | 'version' | 'revision'> & { jurisdiction_id: string; expected_revision: number }) => (await api.patch<MarketProfile>(`${root}/market-profile`, body)).data,
  update: async (id: string, body: Partial<ApplicationMetadata> & { expected_revision: number }) => (await api.patch<LicenceApplication>(`${root}/${id}`, body)).data,
  addComponent: async (id: string, body: ComponentInput & { expected_revision: number }) => (await api.post<LicenceApplication>(`${root}/${id}/components`, body)).data,
  updateComponent: async (id: string, componentId: string, body: Partial<ComponentInput> & { expected_revision: number }) => (await api.patch<LicenceApplication>(`${root}/${id}/components/${componentId}`, body)).data,
  removeComponent: async (id: string, componentId: string, expected_revision: number) => (await api.delete<LicenceApplication>(`${root}/${id}/components/${componentId}`, { params: { expected_revision } })).data,
  duplicateComponent: async (id: string, componentId: string, body: { expected_revision: number; name: string }) => (await api.post<LicenceApplication>(`${root}/${id}/components/${componentId}/duplicate`, body)).data,
  action: async (id: string, action: string, body: { expected_revision: number; notes?: string; reason?: string; submitted_at?: string; reference?: string; outcome?: string }) => (await api.post<LicenceApplication>(`${root}/${id}/${action}`, body)).data,
  addFollowup: async (id: string, body: { expected_revision: number; question: string; owner_id: string | null; due_date: string | null }) => (await api.post<LicenceApplication>(`${root}/${id}/followups`, body)).data,
  updateFollowup: async (id: string, followupId: string, body: Partial<ApplicationFollowup> & { expected_revision: number }) => (await api.patch<LicenceApplication>(`${root}/${id}/followups/${followupId}`, body)).data,
  download: async (id: string, snapshotId: string, filename: string) => {
    const { data } = await api.get<Blob>(`${root}/${id}/snapshots/${snapshotId}/export`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
