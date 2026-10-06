import { formatDateTime } from '../utils/dateFormat'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import type { DashboardData, ProgramWorkspaceSummary } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useToast } from '../contexts/ToastContext'
import LinkButton from '../components/ui/LinkButton'
import DecisionModal from '../components/ui/DecisionModal'
import { notifyApiError } from '../utils/notify'
import KpiCards from './dashboard/KpiCards'
import StatusBreakdown from './dashboard/StatusBreakdown'
import SnapshotTrend from './dashboard/SnapshotTrend'
import MyWorkPanel from './dashboard/MyWorkPanel'
import ReviewCyclesPanel from './dashboard/ReviewCyclesPanel'
import QueuesPanel from './dashboard/QueuesPanel'
import DataQualityAlerts from './dashboard/DataQualityAlerts'
import RecentActivityFeed from './dashboard/RecentActivityFeed'
import NextBestActionsPanel from './dashboard/NextBestActionsPanel'
import GettingStartedGuide from './dashboard/GettingStartedGuide'
import { useGettingStarted } from './dashboard/useGettingStarted'
import './dashboard/dashboard.css'

export default function Dashboard() {
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, isLoading: jurisdictionsLoading, error: jurisdictionError, retry: retryJurisdictions } = useJurisdiction()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const workScope = searchParams.get('work_scope') === 'all' ? 'all' : 'unresolved'
  const previousJurisdiction = useRef(jurisdictionId)
  const jurisdictionChanged = Boolean(previousJurisdiction.current && jurisdictionId && previousJurisdiction.current !== jurisdictionId)
  const requestedPage = Number(searchParams.get('work_page'))
  const workPage = !jurisdictionChanged && Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  useEffect(() => {
    if (!jurisdictionId) return
    previousJurisdiction.current = jurisdictionId
    if (!jurisdictionChanged || !Number.isSafeInteger(requestedPage) || requestedPage <= 1) return
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      next.set('work_page', '1')
      return next
    }, { replace: true })
  }, [jurisdictionId, jurisdictionChanged, requestedPage, setSearchParams])
  const workExpanded = searchParams.get('work_all') === 'true'
  const workPageSize = workExpanded ? 20 : 5
  const selectedMode = searchParams.get('work_mode')
  const updateWork = (values: Record<string, string>) => {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(values)) next.set(key, value)
      return next
    })
  }
  const [isInsightsOpen, setIsInsightsOpen] = useState(false)
  const [isSnapshotModalOpen, setIsSnapshotModalOpen] = useState(false)
  const [snapshotName, setSnapshotName] = useState('')
  const role = user?.role || 'contributor'
  const canCreateSnapshots = role === 'admin' || role === 'manager'
  const canSeeOpsInsights = role === 'admin' || role === 'manager'
  const gettingStarted = useGettingStarted(jurisdictionId, canSeeOpsInsights)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard', jurisdictionId, workScope, workPage, workPageSize],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      params.set('work_scope', workScope)
      params.set('work_page', String(workPage))
      params.set('work_page_size', String(workPageSize))
      const url = params.toString() ? `/dashboard?${params.toString()}` : '/dashboard'
      const response = await api.get<DashboardData>(url)
      return response.data
    },
    enabled: !!jurisdictionId,
  })
  const orchestrationQuery = useQuery({
    queryKey: ['program-workspace-summary', jurisdictionId, 'dashboard-next-actions'],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      params.set('limit', '25')
      const response = await api.get<ProgramWorkspaceSummary>(
        `/program-workspace/summary?${params.toString()}`
      )
      return response.data
    },
    enabled: !!jurisdictionId && canSeeOpsInsights,
  })

  const createSnapshotMutation = useMutation({
    mutationFn: async (payload: { name: string; description?: string }) => {
      await api.post('/snapshots', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Snapshot creation failed')
    },
  })

  if (!jurisdictionId) {
    if (jurisdictionsLoading) {
      return <div role="status" className="py-12 text-center text-muted">Loading jurisdictions…</div>
    }
    return (
      <div className="dashboard-shell min-w-0">
        <h1 className="dashboard-page-title mb-5 text-2xl font-semibold text-ink">Compliance Dashboard</h1>
        {jurisdictionError ? <div role="alert" className="mb-4 text-danger">{jurisdictionError} <button type="button" onClick={retryJurisdictions} className="underline">Try again</button></div> : null}
        {!jurisdictionError && <GettingStartedGuide stage="jurisdiction" isOperator={!!user?.installation_operator} />}
      </div>
    )
  }

  if (isLoading) {
    return <div role="status" className="py-12 text-center text-muted">Loading dashboard…</div>
  }

  if (error) {
    return <div role="alert" className="rounded-xl border border-danger-line bg-danger-soft p-6 text-danger">Unable to load the dashboard. <button type="button" onClick={() => refetch()} className="ml-2 font-semibold underline">Try again</button></div>
  }

  if (!data) return null

  const defaultMyWorkMode = (data.my_work.authority_queries?.total ?? 0) > 0 ? 'authority_queries' : (data.my_work.assigned_forms?.total ?? 0) > 0 ? 'forms' : role === 'assigned_reviewer' || (!data.my_work.assigned_requirements.total && data.my_work.assigned_review_items.total > 0) ? 'review_items' : 'requirements'

  const primaryMyWorkMode = selectedMode === 'requirements' || selectedMode === 'review_items' || selectedMode === 'forms' || selectedMode === 'authority_queries' ? selectedMode : defaultMyWorkMode

  const showStatusInsight = role !== 'assigned_reviewer' && data.kpis.by_status.length > 0
  const showQueueInsight = canSeeOpsInsights && !!data.queues
  const showDataQualityInsight = canSeeOpsInsights && !!data.data_quality
  const hasInsights =
    showStatusInsight || showQueueInsight || showDataQualityInsight

  const snapshotActions = canCreateSnapshots ? (
    <button
      type="button"
      disabled={createSnapshotMutation.isPending}
      onClick={() => {
        setSnapshotName(`Snapshot ${formatDateTime(new Date())}`)
        setIsSnapshotModalOpen(true)
      }}
      className="rounded-full border border-line-strong bg-surface/90 px-3 py-1.5 text-sm font-medium text-ink hover:border-brand-line hover:text-accent disabled:opacity-50"
    >
      {createSnapshotMutation.isPending ? 'Creating…' : 'Create snapshot'}
    </button>
  ) : null

  return (
    <div className="dashboard-shell min-w-0">
      <div className="dashboard-content space-y-6">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="dashboard-page-title text-2xl font-semibold text-ink">
              Compliance Dashboard
            </h1>
            {jurisdictionId && jurisdictionById[jurisdictionId] && (
              <div className="mt-1 text-sm text-muted">
                Jurisdiction: {jurisdictionById[jurisdictionId].name}
              </div>
            )}
            <div className="mt-1 text-sm text-muted">
              Generated: {formatDateTime(data.generated_at)}
            </div>
          </div>
          <nav aria-label="Compliance workflows" className="flex flex-wrap gap-2"><LinkButton to="/licence-applications">Licence Applications</LinkButton><LinkButton to="/certification-projects">Certifications</LinkButton><LinkButton to="/change-management">Change Management</LinkButton></nav>
        </div>

        {canSeeOpsInsights && !gettingStarted.isLoading && (gettingStarted.isError || gettingStarted.stage !== 'complete') ? (
          <GettingStartedGuide stage={gettingStarted.stage} isOperator={!!user?.installation_operator} error={gettingStarted.isError} onRetry={gettingStarted.retry} />
        ) : null}

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            <MyWorkPanel assignedRequirements={data.my_work.assigned_requirements} assignedReviewItems={data.my_work.assigned_review_items} assignedForms={data.my_work.assigned_forms} authorityQueries={data.my_work.authority_queries} primaryMode={primaryMyWorkMode}
              scope={workScope} page={workPage} pageSize={workPageSize} expanded={workExpanded}
              onScopeChange={scope => updateWork({ work_scope: scope, work_page: '1', work_mode: primaryMyWorkMode })}
              onModeChange={mode => updateWork({ work_mode: mode, work_page: '1' })}
              onPageChange={page => updateWork({ work_page: String(page), work_mode: primaryMyWorkMode })}
              onExpand={() => updateWork({ work_all: 'true', work_page: '1', work_mode: primaryMyWorkMode })}
            />
            {canSeeOpsInsights && <NextBestActionsPanel actions={orchestrationQuery.data?.next_actions ?? []} projects={orchestrationQuery.data?.items ?? []} isLoading={orchestrationQuery.isLoading} isError={orchestrationQuery.isError} onRetry={() => { void orchestrationQuery.refetch() }} />}
          </div>
          <div className="space-y-6">
            <ReviewCyclesPanel cycles={data.review_cycles.active} />
          </div>
        </div>

        {(data.kpis.overall.total > 0 || data.kpis.mandatory.total > 0 || data.kpis.at_risk_count > 0) && <KpiCards overall={data.kpis.overall} mandatory={data.kpis.mandatory} atRiskCount={data.kpis.at_risk_count} />}

        <RecentActivityFeed items={data.recent_activity} />

        {hasInsights ? (
          <section className="dashboard-reveal rounded-2xl border border-line/80 bg-surface/70 p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="dashboard-card-heading text-base font-semibold text-ink">
                Additional data
              </h2>
              <button
                type="button"
                onClick={() => setIsInsightsOpen((open) => !open)}
                aria-expanded={isInsightsOpen}
                aria-controls="dashboard-more-insights"
                className="rounded-full border border-line-strong bg-surface/90 px-3 py-1.5 text-sm font-medium text-ink hover:border-brand-line hover:text-accent"
              >
                {isInsightsOpen ? 'Hide additional data' : 'Show additional data'}
              </button>
            </div>

            {isInsightsOpen ? (
              <div id="dashboard-more-insights" className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
                <SnapshotTrend snapshots={data.snapshots} actions={snapshotActions} />
                {showStatusInsight ? <StatusBreakdown rows={data.kpis.by_status} /> : null}
                {showQueueInsight ? <QueuesPanel queues={data.queues ?? null} /> : null}
                {showDataQualityInsight ? (
                  <DataQualityAlerts dataQuality={data.data_quality ?? null} />
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
      <DecisionModal
        open={isSnapshotModalOpen}
        title="Create snapshot"
        description="Capture current approved requirements across all jurisdictions in your organization. This snapshot is separate from individual review assessments."
        confirmLabel="Create snapshot"
        confirmVariant="primary"
        rationaleMode="required"
        rationaleLabel="Snapshot name"
        rationalePlaceholder="Snapshot name"
        rationaleValue={snapshotName}
        onRationaleChange={setSnapshotName}
        onConfirm={() => {
          createSnapshotMutation.mutate({
            name: snapshotName.trim(),
            description: 'Created from dashboard',
          })
          setIsSnapshotModalOpen(false)
          setSnapshotName('')
        }}
        onClose={() => {
          setIsSnapshotModalOpen(false)
          setSnapshotName('')
        }}
        isWorking={createSnapshotMutation.isPending}
      />
    </div>
  )
}
