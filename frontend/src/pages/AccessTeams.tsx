import './workflow-pages.css'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import type { PaginatedResponse, UserMention } from '../types'
import TeamsPanel from '../components/access/TeamsPanel'

export default function AccessTeams() {
  const people = useQuery({ queryKey: ['access', 'users'], queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data })
  return <div className="workflow-page teams-page mx-auto max-w-5xl space-y-6"><header><h1 className="text-2xl font-semibold">Teams</h1><p className="mt-2 text-sm text-muted">Share access through groups you manage.</p></header><TeamsPanel users={people.data?.items || []} usersLoading={people.isLoading} usersError={people.isError} /></div>
}
