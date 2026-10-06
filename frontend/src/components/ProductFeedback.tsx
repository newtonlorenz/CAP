import { lazy, Suspense } from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import type { FeedbackSubmission } from '@page-feedback/react'
import '@page-feedback/react/style.css'

const Widget = lazy(() => import('@page-feedback/react').then(module => ({ default: module.FeedbackWidget })))

export default function ProductFeedback() {
  const { user } = useAuth()
  const location = useLocation()
  const queryClient = useQueryClient()
  const config = useQuery({
    queryKey: ['product-feedback-config', user?.id],
    queryFn: async () => (await api.get<{ enabled: boolean }>('/product-feedback/config')).data,
    enabled: !!user,
    staleTime: 60_000,
    retry: false,
  })
  if (!config.data?.enabled || !user) return null
  const submit = async (report: FeedbackSubmission) => {
    await api.post('/product-feedback', report)
    void queryClient.invalidateQueries({ queryKey: ['product-feedback'] })
  }
  return <Suspense fallback={null}><Widget key={user.id} pagePath={`${import.meta.env.BASE_URL.replace(/\/$/, '')}${location.pathname}`}
    onSubmit={submit} /></Suspense>
}
