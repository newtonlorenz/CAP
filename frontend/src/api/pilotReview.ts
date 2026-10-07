import api from './client'
import type {
  AnswerHistoryItem, PilotPage, PilotPreparationCase, ReviewQueueFilters, ReviewQueueItem,
  TeamWorkFilters, TeamWorkPage,
} from '../types/pilotReview'

export const pilotReviewApi = {
  reviewQueue: async (params: ReviewQueueFilters = {}) =>
    (await api.get<PilotPage<ReviewQueueItem>>('/preparation/review-queue', { params })).data,
  getCase: async (id: string) =>
    (await api.get<PilotPreparationCase>(`/preparation/cases/${id}`)).data,
  returnResponse: async (caseId: string, fieldKey: string, body: { expected_revision: number; comment: string }) =>
    (await api.post<PilotPreparationCase>(`/preparation/cases/${caseId}/responses/${encodeURIComponent(fieldKey)}/return`, body)).data,
  acceptResponse: async (caseId: string, fieldKey: string, expectedRevision: number) =>
    (await api.post<PilotPreparationCase>(`/preparation/cases/${caseId}/responses/${encodeURIComponent(fieldKey)}/accept`, { expected_revision: expectedRevision })).data,
  reviewers: async (caseId: string) =>
    (await api.get<{ items: Array<{ id: string; full_name: string }> }>(`/preparation/cases/${caseId}/reviewers`)).data,
  assignReviewer: async (caseId: string, reviewerId: string | null, expectedRevision: number) =>
    (await api.patch<PilotPreparationCase>(`/preparation/cases/${caseId}`, { reviewer_id: reviewerId, expected_revision: expectedRevision })).data,
  history: async (caseId: string, fieldKey: string) =>
    (await api.get<{ items: AnswerHistoryItem[] }>(`/preparation/cases/${caseId}/responses/${encodeURIComponent(fieldKey)}/history`)).data,
  teamWork: async (params: TeamWorkFilters = {}) =>
    (await api.get<TeamWorkPage>('/dashboard/team-work', { params })).data,
}
