import './workflow-pages.css'
import { formatDate } from '../utils/dateFormat'
import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type {
  ReviewCycle,
  PaginatedResponse,
  RequirementSetSummary,
  UserMention,
} from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useToast } from '../contexts/ToastContext'
import SoAFieldSelector from '../components/SoAFieldSelector'
import { READABLE_SOA_FIELD_KEYS } from '../utils/soaFields'
import { notifyApiError } from '../utils/notify'
import { getApiErrorMessage } from '../api/errors'
import Badge from '../components/ui/Badge'
import Button, { type ButtonVariant } from '../components/ui/Button'
import Card from '../components/ui/Card'
import DecisionModal from '../components/ui/DecisionModal'
import DropdownMenu from '../components/ui/DropdownMenu'
import Modal from '../components/ui/Modal'
import { Table, TBody, TD, TH, THead, TR } from '../components/ui/Table'

type ReviewerDisplay = 'both' | 'names' | 'emails'

export default function ReviewCycles() {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const statusFilter = ['active', 'closed', 'archived'].includes(searchParams.get('status') || '') ? searchParams.get('status')! : 'all'
  const search = searchParams.get('q') || ''
  const projectFilter = searchParams.get('project')
  const changeFilter = searchParams.get('change')
  const setFilter = (key: string, value: string) => setSearchParams((current) => { const next = new URLSearchParams(current); if (value && value !== 'all') next.set(key, value); else next.delete(key); return next }, { replace: true })
  const setStatusFilter = (value: string) => setFilter('status', value)
  const setSearch = (value: string) => setFilter('q', value)
  const [scopeMode, setScopeMode] = useState<'all' | 'documents'>('documents')
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([])
  const [isDownloading, setIsDownloading] = useState<string | null>(null)
  const [soaFields, setSoaFields] = useState<string[]>(READABLE_SOA_FIELD_KEYS)
  const [soaSelectorOpen, setSoaSelectorOpen] = useState(false)
  const [soaCycleId, setSoaCycleId] = useState<string | null>(null)
  const [soaFormat, setSoaFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const [reportsModalOpen, setReportsModalOpen] = useState(false)
  const [reportsCycle, setReportsCycle] = useState<ReviewCycle | null>(null)
  const [reviewerDisplay, setReviewerDisplay] = useState<ReviewerDisplay>('both')
  const [archivingCycleId, setArchivingCycleId] = useState<string | null>(null)
  const [restoringCycleId, setRestoringCycleId] = useState<string | null>(null)
  const [deletingCycleId, setDeletingCycleId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | {
    title: string
    description: string
    confirmLabel: string
    confirmVariant?: ButtonVariant
    dangerDetails?: string[]
    onConfirm: () => void
  }>(null)
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById } = useJurisdiction()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const isAdminOrManager = user?.role === 'admin' || user?.role === 'manager'

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['review-cycles', statusFilter, jurisdictionId, projectFilter, changeFilter],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      if (statusFilter !== 'all') params.set('status', statusFilter)
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      if (projectFilter) params.set('certification_project_id', projectFilter)
      if (changeFilter) params.set('change_entry_id', changeFilter)
      const response = await api.get<PaginatedResponse<ReviewCycle>>(
        `/review-cycles?${params.toString()}`
      )
      return response.data
    },
    enabled: !!jurisdictionId,
  })

  const { data: requirementSetsAll, isLoading: setsLoading, isError: setsError, refetch: retrySets } = useQuery({
    queryKey: ['requirements-sets', 'all', jurisdictionId],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      params.set('include_archived_documents', 'true')
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data
    },
    enabled: !!jurisdictionId,
  })

  const { data: mentionUsers, isError: ownersError, refetch: retryOwners } = useQuery({
    queryKey: ['mention-users'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')
      return response.data
    },
    enabled: showCreateModal,
  })

  const createMutation = useMutation({
    mutationFn: async (data: {
      jurisdiction_id: string
      name: string
      description: string
      deadline: string | null
      scope: string
      document_ids?: string[]
      default_assigned_reviewer_id?: string
      default_responsible_user_id?: string
    }) => {
      const response = await api.post<ReviewCycle>('/review-cycles', data)
      return response.data
    },
    onSuccess: (cycle) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      if (cycle?.id) navigate(`/review-cycles/${cycle.id}?mode=focus`)
      setShowCreateModal(false)
      setSelectedDocuments([])
      setScopeMode('documents')
      toast.success('Assessment created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create assessment')
    },
  })

  const archiveMutation = useMutation({
    mutationFn: async (cycleId: string) => {
      await api.post(`/review-cycles/${cycleId}/archive`)
    },
    onMutate: (cycleId) => {
      setArchivingCycleId(cycleId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle'] })
      toast.success('Assessment archived')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to archive assessment')
    },
    onSettled: () => {
      setArchivingCycleId(null)
    },
  })

  const restoreMutation = useMutation({
    mutationFn: async (cycleId: string) => {
      await api.post(`/review-cycles/${cycleId}/restore`)
    },
    onMutate: (cycleId) => {
      setRestoringCycleId(cycleId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle'] })
      toast.success('Assessment unarchived')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to unarchive assessment')
    },
    onSettled: () => {
      setRestoringCycleId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (cycleId: string) => {
      await api.delete(`/review-cycles/${cycleId}`)
    },
    onMutate: (cycleId) => {
      setDeletingCycleId(cycleId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle'] })
      toast.success('Assessment deleted')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to delete assessment')
    },
    onSettled: () => {
      setDeletingCycleId(null)
    },
  })

  const approvedSets = (requirementSetsAll?.items || []).filter((set) => set.document_status === 'approved')
  const validDocuments = selectedDocuments.filter((id) => approvedSets.some((set) => set.document_id === id))
  const scopeReady = !setsLoading && !setsError && (scopeMode === 'all' ? approvedSets.length > 0 : validDocuments.length > 0)

  const handleCreate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!jurisdictionId) {
      toast.info('Select a jurisdiction first.')
      return
    }
    const formData = new FormData(e.currentTarget)
    if (!scopeReady) {
      toast.error('Select at least one requirement set or choose "All approved requirement sets".')
      return
    }
    const defaultAssigned = formData.get('default_assigned_reviewer_id') as string
    const defaultResponsible = formData.get('default_responsible_user_id') as string
    createMutation.mutate({
      jurisdiction_id: jurisdictionId,
      name: formData.get('name') as string,
      description: formData.get('description') as string,
      deadline: formData.get('deadline') ? new Date(`${formData.get('deadline')}T00:00:00Z`).toISOString() : null,
      scope: scopeMode === 'all' ? 'all' : 'documents',
      document_ids: scopeMode === 'documents' ? validDocuments : undefined,
      ...(defaultAssigned ? { default_assigned_reviewer_id: defaultAssigned } : {}),
      ...(defaultResponsible ? { default_responsible_user_id: defaultResponsible } : {}),
    })
  }

  const cycleStatusTone = (status: string) => {
    if (status === 'active') return 'green'
    if (status === 'archived') return 'amber'
    return 'slate'
  }

  const downloadReport = async (
    endpoint: string,
    filename: string,
    params?: URLSearchParams
  ) => {
    setIsDownloading(endpoint)
    try {
      const url = params ? `${endpoint}?${params.toString()}` : endpoint
      const response = await api.get(url, { responseType: 'blob' })
      const blob = new Blob([response.data])
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = filename
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (error) {
      console.error('Download failed:', error)
    } finally {
      setIsDownloading(null)
    }
  }

  const openSoaSelector = (cycleId: string, format: 'xlsx' | 'pdf') => {
    setSoaCycleId(cycleId)
    setSoaFormat(format)
    setSoaSelectorOpen(true)
  }

  const confirmSoaDownload = () => {
    if (!soaCycleId) return
    const params = new URLSearchParams()
    params.set('review_cycle_id', soaCycleId)
    params.set('format', soaFormat)
    if (soaFields.length) {
      params.set('fields', soaFields.join(','))
    }
    const filename =
      soaFormat === 'pdf'
        ? 'statement-of-applicability.pdf'
        : 'statement-of-applicability.xlsx'
    downloadReport('/reports/statement-of-applicability', filename, params)
    setSoaSelectorOpen(false)
  }

  const confirmReviewCycleReport = () => {
    if (!reportsCycle) return
    const params = new URLSearchParams()
    params.set('review_cycle_id', reportsCycle.id)
    params.set('reviewer_display', reviewerDisplay)
    downloadReport('/reports/review-cycle-report', 'review-cycle-report.pdf', params)
    setReportsModalOpen(false)
  }

  const openReportsModal = (cycle: ReviewCycle) => {
    setReportsCycle(cycle)
    setReportsModalOpen(true)
  }

  const restoreStatusLabel = (cycle: ReviewCycle) =>
    cycle.closed_at || cycle.closed_by || cycle.snapshot_id ? 'closed' : 'active'

  const buildCycleMenuItems = (cycle: ReviewCycle) => {
    const isArchiving = archivingCycleId === cycle.id && archiveMutation.isPending
    const isRestoring = restoringCycleId === cycle.id && restoreMutation.isPending
    const isDeleting = deletingCycleId === cycle.id && deleteMutation.isPending
    const statusActionDisabled = isArchiving || isRestoring || isDeleting
    const isArchived = cycle.status === 'archived'

    const items: Array<{
      key: string
      label: string
      onSelect: () => void
      disabled?: boolean
      tone?: 'default' | 'destructive'
    }> = (isAdminOrManager || user?.role === 'approver') ? [
      {
        key: 'reports',
        label: 'Reports',
        onSelect: () => openReportsModal(cycle),
      },
    ] : []

    if (isAdminOrManager) {
      items.push({
        key: isArchived ? 'restore' : 'archive',
        label: isArchived
          ? isRestoring
            ? 'Unarchiving...'
            : 'Unarchive'
          : isArchiving
            ? 'Archiving...'
            : 'Archive',
        disabled: statusActionDisabled,
        onSelect: () =>
          setConfirm({
            title: isArchived ? 'Unarchive assessment?' : 'Archive assessment?',
            description: isArchived ? `Unarchive "${cycle.name}"?` : `Archive "${cycle.name}"?`,
            confirmLabel: isArchived ? 'Unarchive' : 'Archive',
            confirmVariant: isArchived ? 'secondary' : undefined,
            dangerDetails: isArchived
              ? [`Return this cycle to ${restoreStatusLabel(cycle)} status.`]
              : ['Move this cycle to archived status.'],
            onConfirm: () =>
              isArchived ? restoreMutation.mutate(cycle.id) : archiveMutation.mutate(cycle.id),
          }),
      })
      if (!cycle.closed_at && !cycle.snapshot_id && cycle.status !== 'closed') items.push({
        key: 'delete',
        label: isDeleting ? 'Deleting...' : 'Delete',
        tone: 'destructive',
        disabled: isDeleting || isArchiving || isRestoring,
        onSelect: () =>
          setConfirm({
            title: 'Delete assessment?',
            description: `Delete "${cycle.name}"? This cannot be undone.`,
            confirmLabel: 'Delete',
            dangerDetails: ['Remove assessment items, comments, and uploaded evidence files.'],
            onConfirm: () => deleteMutation.mutate(cycle.id),
          }),
      })
    }

    return items
  }

  const filteredCycles = (data?.items || []).filter((cycle) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return cycle.name.toLowerCase().includes(q)
  })

  const requirementSetNameByDocumentId = useMemo(() => {
    const map = new Map<string, string>()
    for (const set of requirementSetsAll?.items || []) {
      map.set(set.document_id, set.name || set.filename || 'Requirement set')
    }
    return map
  }, [requirementSetsAll?.items])

  const formatScope = (cycle: ReviewCycle): { label: string; details?: string } => {
    if (cycle.scope === 'all') {
      return { label: 'All requirement sets' }
    }
    if (cycle.scope === 'documents') {
      const ids = cycle.document_ids || []
      const names = ids
        .map((id) => requirementSetNameByDocumentId.get(id) || id)
        .filter(Boolean)
      return {
        label: names.length ? names.join(', ') : 'Selected requirement sets',
      }
    }
    return { label: cycle.scope }
  }

  const formatBaselineSummary = (cycle: ReviewCycle): string => {
    const baselines = cycle.baseline_versions || []
    if (baselines.length === 0) {
      return `${formatScope(cycle).label} · No baseline snapshot`
    }
    return baselines
      .map((baseline) => {
        const name = requirementSetNameByDocumentId.get(baseline.document_id) || baseline.document_id
        return `${name} v${baseline.version_number}`
      })
      .join(', ')
  }

  return (
    <div data-tour="assessments-page" className="workflow-page assessments-page min-w-0 space-y-4">
      <header className="py-1">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-ink">Assessment overview</h1>
            {(projectFilter || changeFilter) && <p className="mt-2 text-sm"><Link className="text-accent underline" to={changeFilter ? `/change-management?change=${changeFilter}&tab=changes` : `/certification-projects?project=${projectFilter}&section=review`}>Back to {changeFilter ? 'change' : 'certification project'}</Link> · <Link className="text-accent underline" to="/review-cycles">All assessments</Link></p>}
            {jurisdictionId && jurisdictionById[jurisdictionId] ? (
              <div className="mt-1 text-sm text-muted">
                Jurisdiction: {jurisdictionById[jurisdictionId].name}
              </div>
            ) : (
              <div className="mt-1 text-sm text-muted">Select a jurisdiction to view assessments.</div>
            )}
            <p className="mt-1 text-sm text-muted">
              Assess approved requirements against the available evidence and record reviewer decisions. Each assessment retains the requirement versions selected when it was created.
            </p>
          </div>

          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium uppercase tracking-wide text-muted">
                Status
              </label>
              <select
                aria-label="Assessment status"
                value={statusFilter}
                onChange={(e) =>
                  setStatusFilter(e.target.value as 'all' | 'active' | 'closed' | 'archived')
                }
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none sm:w-44"
              >
                <option value="all">All</option>
                <option value="active">Active</option>
                <option value="closed">Closed</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium uppercase tracking-wide text-muted">
                Search
              </label>
              <input
                aria-label="Search assessments"
              value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Assessment name"
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none sm:w-56"
              />
            </div>

            {(user?.role === 'admin' || user?.role === 'manager') && (
              <Button variant="primary" disabled={!jurisdictionId} className="mt-2 shrink-0 whitespace-nowrap sm:mt-6" onClick={() => setShowCreateModal(true)}>
                Create assessment
              </Button>
            )}
          </div>
        </div>
      </header>

      {!jurisdictionId ? (
        <Card className="p-6 text-sm text-muted">Select a jurisdiction to view assessments.</Card>
      ) : isError ? <Card className="p-5"><p role="alert">Assessments could not be loaded.</p><Button onClick={() => refetch()}>Try again</Button></Card> : isLoading ? (
        <Card className="p-6 text-sm text-muted">Loading...</Card>
      ) : (
        <Card className="overflow-hidden"><div className="workflow-table-heading"><h2>Requirement assessments</h2><p>{filteredCycles.length} matching {filteredCycles.length === 1 ? 'assessment' : 'assessments'}</p></div>
          <div data-testid="review-cycles-mobile-cards" className="divide-y divide-line lg:hidden">
            {filteredCycles.map((cycle) => (
              <div
                key={cycle.id}
                className="cursor-pointer p-4 hover:bg-canvas"
                onClick={() => navigate(`/review-cycles/${cycle.id}`)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-ink break-words"><Link to={`/review-cycles/${cycle.id}`} onClick={(event) => event.stopPropagation()} className="hover:text-accent hover:underline">{cycle.name}</Link></h2>
                    {cycle.status === 'active' && <Link to={`/review-cycles/${cycle.id}?mode=focus`} aria-label={`Continue ${cycle.name}`} onClick={(event) => event.stopPropagation()} className="mt-2 inline-flex min-h-10 items-center text-sm font-semibold text-accent hover:underline">Continue assessment →</Link>}
                    <div className="mt-2 space-y-1 text-xs text-muted">
                      <div>
                        Baseline: <span className="text-ink">{formatBaselineSummary(cycle)}</span>
                      </div>
                      {cycle.predecessor_cycle_id ? (
                        <div>
                          <Link to={`/review-cycles/${cycle.predecessor_cycle_id}`} onClick={(event) => event.stopPropagation()} className="text-accent underline">View previous assessment</Link>
                        </div>
                      ) : null}
                      <div>
                        Deadline:{' '}
                        <span className="text-ink">
                          {cycle.deadline ? formatDate(cycle.deadline) : '-'}
                        </span>
                      </div>
                      <div>
                        Created:{' '}
                        <span className="text-ink">
                          {formatDate(cycle.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="shrink-0 flex items-start gap-2">
                    <Badge tone={cycleStatusTone(cycle.status)}>{cycle.status}</Badge>
                    <DropdownMenu ariaLabel={`Actions for ${cycle.name}`} items={buildCycleMenuItems(cycle)} />
                  </div>
                </div>
              </div>
            ))}
            {filteredCycles.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted">No assessments found.</div>
            ) : null}
          </div>

          <div className="hidden lg:block">
            <Table>
              <THead>
                <tr>
                  <TH>Name</TH>
                  <TH>Jurisdiction</TH>
                  <TH>Deadline</TH>
                  <TH>Status</TH>
                  <TH>Created</TH>
                  <TH className="w-[1%]">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {filteredCycles.map((cycle) => (
                  <TR
                    key={cycle.id}
                    className="group cursor-pointer"
                    onClick={() => navigate(`/review-cycles/${cycle.id}`)}
                  >
                    <TD className="text-ink font-semibold break-words">
                      <Link to={`/review-cycles/${cycle.id}`} onClick={(event) => event.stopPropagation()} className="hover:text-accent hover:underline">{cycle.name}</Link>
                      {cycle.status === 'active' && <Link to={`/review-cycles/${cycle.id}?mode=focus`} aria-label={`Continue ${cycle.name}`} onClick={(event) => event.stopPropagation()} className="mt-1 block w-fit py-1 text-sm font-semibold text-accent hover:underline">Continue assessment →</Link>}
                      <div className="mt-1 text-xs text-muted">
                        Baseline: {formatBaselineSummary(cycle)}
                      </div>
                      {cycle.predecessor_cycle_id ? (
                        <div className="mt-1 text-xs text-muted">
                          <Link to={`/review-cycles/${cycle.predecessor_cycle_id}`} onClick={(event) => event.stopPropagation()} className="text-accent underline">View previous assessment</Link>
                        </div>
                      ) : null}
                    </TD>
                    <TD className="text-muted break-words">
                      {jurisdictionById[cycle.jurisdiction_id]?.name || '-'}
                    </TD>
                    <TD className="text-muted">
                      {cycle.deadline ? formatDate(cycle.deadline) : '-'}
                    </TD>
                    <TD>
                      <Badge tone={cycleStatusTone(cycle.status)}>{cycle.status}</Badge>
                    </TD>
                    <TD className="text-muted">
                      {formatDate(cycle.created_at)}
                    </TD>
                    <TD className="text-right" onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu ariaLabel={`Actions for ${cycle.name}`} items={buildCycleMenuItems(cycle)} />
                    </TD>
                  </TR>
                ))}
                {filteredCycles.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-10 text-center text-sm text-muted">
                      No assessments found.
                    </td>
                  </tr>
                ) : null}
              </TBody>
            </Table>
          </div>
        </Card>
      )}

      <Modal
        open={showCreateModal}
        title="Create requirement assessment"
        description={
          jurisdictionId && jurisdictionById[jurisdictionId]
            ? `Jurisdiction: ${jurisdictionById[jurisdictionId].name}. Selected requirement sets are version-locked at creation.`
            : undefined
        }
        onClose={() => {
          setShowCreateModal(false)
          setSelectedDocuments([])
          setScopeMode('documents')
        }}
        size="lg"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {createMutation.isError && <p role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{getApiErrorMessage(createMutation.error, 'Unable to create the assessment. Check the fields and try again.')}</p>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-ink">Name</label>
              <input aria-label="Name"
                type="text"
                name="name"
                required
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-ink">Deadline</label>
              <input aria-label="Deadline"
                type="date"
                name="deadline"
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
          </div>

          <div>
            <div className="text-sm font-medium text-ink">Scope</div>
            <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:gap-4">
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="scope"
                  value="documents"
                  checked={scopeMode === 'documents'}
                  onChange={() => setScopeMode('documents')}
                />
                Select requirement sets
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="radio"
                  name="scope"
                  value="all"
                  checked={scopeMode === 'all'}
                  onChange={() => {
                    setScopeMode('all')
                    setSelectedDocuments([])
                  }}
                />
                All approved requirement sets (lock snapshot now)
              </label>
            </div>
          </div>

          {setsLoading ? <p role="status" className="text-sm text-muted">Loading approved requirement sets…</p>
            : setsError ? <p role="alert" className="text-sm text-danger">Requirement sets could not be loaded. <button type="button" className="font-semibold underline" onClick={() => void retrySets()}>Try again</button></p>
            : approvedSets.length === 0 ? <p className="rounded-lg bg-info-soft p-4 text-sm text-info">Approve a requirement set before starting an assessment. <Link className="font-semibold underline" to="/requirements">Open requirements</Link></p> : null}

          {scopeMode === 'documents' && !setsLoading && !setsError && approvedSets.length > 0 ? (
            <div>
              <div className="text-sm font-medium text-ink">Requirement sets</div>
              <div className="mt-2 max-h-48 overflow-y-auto rounded-md border border-line p-3 space-y-2">
                {approvedSets
                  .map((set) => (
                    <label key={set.document_id} className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={selectedDocuments.includes(set.document_id)}
                        onChange={(e) => {
                          setSelectedDocuments((prev) =>
                            e.target.checked
                              ? [...prev, set.document_id]
                              : prev.filter((id) => id !== set.document_id)
                          )
                        }}
                      />
                      <span className="break-words">{set.name || set.filename}</span>
                    </label>
                  ))}
              </div>
            </div>
          ) : null}

          <details className="rounded-lg border border-line p-4">
            <summary className="text-sm font-semibold">Description and assignments <span className="font-normal text-muted">(optional)</span></summary>
            <div className="mt-4 space-y-4">
              <p className="text-sm text-muted">Assign a reviewer or responsible owner to every item. You can also assign them in the assessment.</p>
              {ownersError && <p role="alert" className="text-sm text-warning">Owner names could not be loaded. <button type="button" className="underline" onClick={() => void retryOwners()}>Try again</button></p>}
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-ink">Description</label>
            <textarea aria-label="Description"
              name="description"
              rows={3}
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-ink">Default assigned reviewer</label>
              <select aria-label="Default assigned reviewer"
                name="default_assigned_reviewer_id"
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              >
                <option value="">No default</option>
                {mentionUsers?.items?.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-ink">Default responsible user</label>
              <select aria-label="Default responsible user"
                name="default_responsible_user_id"
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              >
                <option value="">No default</option>
                {mentionUsers?.items?.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
            </div>
          </div>

            </div>
          </details>

          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setShowCreateModal(false)
                setSelectedDocuments([])
                setScopeMode('documents')
              }}
            >
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={!scopeReady} loading={createMutation.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>

      <DecisionModal
        open={!!confirm}
        title={confirm?.title || ''}
        description={confirm?.description || ''}
        confirmLabel={confirm?.confirmLabel || 'Confirm'}
        confirmVariant={confirm?.confirmVariant}
        dangerDetails={confirm?.dangerDetails}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          const handler = confirm?.onConfirm
          setConfirm(null)
          handler?.()
        }}
        isWorking={archiveMutation.isPending || restoreMutation.isPending || deleteMutation.isPending}
      />

      <SoAFieldSelector
        open={soaSelectorOpen}
        selected={soaFields}
        onChange={setSoaFields}
        onClose={() => setSoaSelectorOpen(false)}
        onConfirm={confirmSoaDownload}
      />
      <ReviewCycleReportsModal
        open={reportsModalOpen}
        cycle={reportsCycle}
        reviewerDisplay={reviewerDisplay}
        onReviewerDisplayChange={setReviewerDisplay}
        isDownloading={isDownloading}
        onClose={() => setReportsModalOpen(false)}
        onDownload={(endpoint, filename, params) => downloadReport(endpoint, filename, params)}
        onDownloadSoA={(format) => {
          if (!reportsCycle) return
          openSoaSelector(reportsCycle.id, format)
        }}
        onDownloadReviewCycleReport={confirmReviewCycleReport}
      />
    </div>
  )
}

export function ReviewCycleReportsModal(props: {
  open: boolean
  cycle: ReviewCycle | null
  reviewerDisplay: ReviewerDisplay
  onReviewerDisplayChange: (value: ReviewerDisplay) => void
  isDownloading: string | null
  onClose: () => void
  onDownload: (endpoint: string, filename: string, params?: URLSearchParams) => void
  onDownloadSoA: (format: 'xlsx' | 'pdf') => void
  onDownloadReviewCycleReport: () => void
}) {
  const {
    open,
    cycle,
    reviewerDisplay,
    onReviewerDisplayChange,
    isDownloading,
    onClose,
    onDownload,
    onDownloadSoA,
    onDownloadReviewCycleReport,
  } = props

  if (!open || !cycle) return null

  const cycleParams = new URLSearchParams()
  cycleParams.set('review_cycle_id', cycle.id)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl bg-surface shadow-xl ring-1 ring-line">
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">
              Reports
            </div>
            <div className="mt-1 text-lg font-semibold text-ink break-words">
              {cycle.name}
            </div>
            <div className="mt-1 text-sm text-muted">
              Choose an export. Statement of Applicability opens field selection.
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="space-y-6 px-5 py-5">
          <section className="space-y-3">
            <div className="text-sm font-semibold text-ink">Cycle Exports</div>
            <div className="rounded-xl border border-line bg-canvas p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-medium text-ink">
                    Assessment report (PDF)
                  </div>
                  <div className="text-xs text-muted">
                    Includes assessment details, evidence and reviewer decisions.
                  </div>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={onDownloadReviewCycleReport}
                  disabled={isDownloading === '/reports/review-cycle-report'}
                >
                  {isDownloading === '/reports/review-cycle-report' ? 'Downloading...' : 'Download'}
                </Button>
              </div>

              <div className="mt-4">
                <div className="text-xs font-medium uppercase tracking-wide text-muted">
                  Reviewer Display
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {(
                    [
                      { value: 'both', label: 'Names + emails' },
                      { value: 'names', label: 'Names only' },
                      { value: 'emails', label: 'Emails only' },
                    ] as const
                  ).map((opt) => (
                    <label
                      key={opt.value}
                      className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink"
                    >
                      <input
                        type="radio"
                        name="reviewer-display"
                        value={opt.value}
                        checked={reviewerDisplay === opt.value}
                        onChange={() => onReviewerDisplayChange(opt.value)}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => onDownloadSoA('xlsx')}
                className="rounded-xl border border-line bg-surface px-4 py-3 text-left hover:bg-canvas"
              >
                <div className="text-sm font-medium text-ink">
                  Statement of Applicability (XLSX)
                </div>
                <div className="text-xs text-muted">Select fields, then export.</div>
              </button>
              <button
                type="button"
                onClick={() => onDownloadSoA('pdf')}
                className="rounded-xl border border-line bg-surface px-4 py-3 text-left hover:bg-canvas"
              >
                <div className="text-sm font-medium text-ink">
                  Statement of Applicability (PDF)
                </div>
                <div className="text-xs text-muted">Select fields, then export.</div>
              </button>
            </div>
          </section>

          <section className="space-y-3">
            <div className="text-sm font-semibold text-ink">Compliance Exports</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() =>
                  onDownload('/reports/compliance-summary', 'compliance-summary.pdf', cycleParams)
                }
                disabled={isDownloading === '/reports/compliance-summary'}
                className="rounded-xl border border-line bg-surface px-4 py-3 text-left hover:bg-canvas disabled:opacity-50"
              >
                <div className="text-sm font-medium text-ink">Compliance Summary</div>
                <div className="text-xs text-muted">PDF</div>
              </button>
              <button
                type="button"
                onClick={() =>
                  onDownload('/reports/detailed', 'detailed-compliance-report.pdf', cycleParams)
                }
                disabled={isDownloading === '/reports/detailed'}
                className="rounded-xl border border-line bg-surface px-4 py-3 text-left hover:bg-canvas disabled:opacity-50"
              >
                <div className="text-sm font-medium text-ink">Detailed Compliance</div>
                <div className="text-xs text-muted">PDF</div>
              </button>
              <div
                className={`rounded-xl border border-line bg-surface px-4 py-3 text-left ${
                  isDownloading === '/reports/gap-analysis' ? 'opacity-50' : ''
                }`}
              >
                <div className="text-sm font-medium text-ink">Gap Analysis</div>
                <div className="text-xs text-muted">XLSX, PDF, or CSV</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={isDownloading === '/reports/gap-analysis'}
                    onClick={() => {
                      const params = new URLSearchParams(cycleParams)
                      params.set('format', 'xlsx')
                      onDownload('/reports/gap-analysis', 'gap-analysis.xlsx', params)
                    }}
                  >
                    XLSX
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={isDownloading === '/reports/gap-analysis'}
                    onClick={() => {
                      const params = new URLSearchParams(cycleParams)
                      params.set('format', 'pdf')
                      onDownload('/reports/gap-analysis', 'gap-analysis.pdf', params)
                    }}
                  >
                    PDF
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={isDownloading === '/reports/gap-analysis'}
                    onClick={() => {
                      const params = new URLSearchParams(cycleParams)
                      params.set('format', 'csv')
                      onDownload('/reports/gap-analysis', 'gap-analysis.csv', params)
                    }}
                  >
                    CSV
                  </Button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
