import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import type { PaginatedResponse, RequirementSetSummary, ReviewCycle } from '../../types'

export function useGettingStarted(jurisdictionId: string | null, enabled: boolean) {
  const sets = useQuery({
    queryKey: ['getting-started-sets', jurisdictionId],
    queryFn: async () => {
      const params = new URLSearchParams({
        jurisdiction_id: jurisdictionId!,
        include_empty_sets: 'true',
        limit: '1000',
      })
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data.items
    },
    enabled: enabled && !!jurisdictionId,
  })
  const reviews = useQuery({
    queryKey: ['getting-started-reviews', jurisdictionId],
    queryFn: async () => {
      const params = new URLSearchParams({ jurisdiction_id: jurisdictionId!, limit: '1' })
      const response = await api.get<PaginatedResponse<ReviewCycle>>(
        `/review-cycles?${params.toString()}`
      )
      return response.data.total
    },
    enabled: enabled && !!jurisdictionId,
  })

  const hasRequirements = sets.data?.some((set) => set.requirements_active > 0) ?? false
  const hasApprovedSet = sets.data?.some((set) => set.current_version_status === 'approved') ?? false
  return {
    isLoading: sets.isLoading || reviews.isLoading,
    isError: sets.isError || reviews.isError,
    retry: () => { void sets.refetch(); void reviews.refetch() },
    stage: !hasRequirements ? 'requirements' as const
      : !hasApprovedSet ? 'approval' as const
      : (reviews.data ?? 0) === 0 ? 'review' as const
      : 'complete' as const,
  }
}
