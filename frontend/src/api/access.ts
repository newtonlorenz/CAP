import api from './client'
import type { AccessPolicy, AccessTeam, ResourceType } from '../types/access'
export const accessApi = {
  get: async (type: ResourceType, id: string) => (await api.get<AccessPolicy>(`/access/${type}/${id}`)).data,
  update: async (type: ResourceType, id: string, body: Pick<AccessPolicy, 'visibility' | 'grants'> & { expected_revision: number; reason: string }) => (await api.put<AccessPolicy>(`/access/${type}/${id}`, body)).data,
  teams: async () => (await api.get<AccessTeam[]>('/access/teams')).data,
  createTeam: async (body: { name: string; member_ids: string[] }) => (await api.post<AccessTeam>('/access/teams', body)).data,
  updateTeam: async (id: string, body: { name: string; member_ids: string[]; expected_revision: number }) => (await api.put<AccessTeam>(`/access/teams/${id}`, body)).data,
}
