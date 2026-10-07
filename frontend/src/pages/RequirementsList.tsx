import './workflow-pages.css'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import type { CertificationProjectFromDocumentResponse, PaginatedResponse, RequirementSetSummary } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useToast } from '../contexts/ToastContext'
import { notifyApiError } from '../utils/notify'
import { getRequirementSetRouting } from '../utils/requirementSetRouting'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import DecisionModal from '../components/ui/DecisionModal'
import DropdownMenu from '../components/ui/DropdownMenu'
import LinkButton from '../components/ui/LinkButton'
import Modal from '../components/ui/Modal'
import { Table, TBody, TD, TH, THead, TR } from '../components/ui/Table'

type CreateMode = 'choose' | 'pdf' | 'manual'
type SortKey = 'name' | 'status' | 'version' | 'testing_frequency' | 'requirements'
type SortDirection = 'asc' | 'desc'

export default function RequirementsList() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const isAdminOrManager = isAdmin || user?.role === 'manager'
  const { jurisdictionId, jurisdictionById } = useJurisdiction()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const useInProject = useMutation({
    mutationFn: async (documentId: string) => (await api.post<CertificationProjectFromDocumentResponse>(`/certification-projects/from-document/${documentId}`)).data,
    onSuccess: ({ project }) => { void queryClient.invalidateQueries({ queryKey: ['certification-projects'] }); navigate(`/certification-projects?project=${project.id}`) },
    onError: (error) => notifyApiError(toast, error, 'Approve the requirement set before using it in a certification project.'),
  })

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createMode, setCreateMode] = useState<CreateMode>('choose')
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('q') || ''
  const statusFilter = searchParams.get('status') || ''
  const documentTypeFilter = searchParams.get('type') || ''
  const setFilter = (key: string, value: string) => setSearchParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next }, { replace: true })
  const setSearch = (value: string) => setFilter('q', value)
  const setStatusFilter = (value: string) => setFilter('status', value)
  const setDocumentTypeFilter = (value: string) => setFilter('type', value)
  const [showEmptyDocs, setShowEmptyDocs] = useState(isAdminOrManager)
  const [showArchivedSets, setShowArchivedSets] = useState(false)
  const [showArchivedDocuments, setShowArchivedDocuments] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc')
  const [confirm, setConfirm] = useState<null | {
    title: string
    description: string
    confirmLabel: string
    dangerDetails?: string[]
    onConfirm: () => void
  }>(null)

  const jurisdictionName = useMemo(() => {
    if (!jurisdictionId) return null
    return jurisdictionById[jurisdictionId]?.name || null
  }, [jurisdictionById, jurisdictionId])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
      'requirements-sets',
      jurisdictionId,
      search,
      statusFilter,
      documentTypeFilter,
      showEmptyDocs,
      showArchivedSets,
      showArchivedDocuments,
    ],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      params.set('include_archived_documents', showArchivedDocuments ? 'true' : 'false')
      params.set('include_empty_sets', showEmptyDocs ? 'true' : 'false')
      params.set('include_archived_sets', showArchivedSets ? 'true' : 'false')
      if (search.trim()) params.set('search', search.trim())
      if (statusFilter) params.set('status', statusFilter)
      if (documentTypeFilter) params.set('document_type', documentTypeFilter)
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data
    },
    enabled: !!jurisdictionId,
  })

  const archiveMutation = useMutation({
    mutationFn: async (documentId: string) => {
      await api.post(`/requirements/by-document/${documentId}/archive`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Requirement set archived')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Archive failed')
    },
  })

  const restoreMutation = useMutation({
    mutationFn: async (documentId: string) => {
      await api.post(`/requirements/by-document/${documentId}/restore`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Requirement set restored')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Restore failed')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (documentId: string) => {
      await api.delete(`/requirements/sets/${documentId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Requirement set deleted')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Delete failed')
    },
  })

  const createFromPdfMutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const response = await api.post('/documents', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data as { id: string }
    },
    onSuccess: (doc) => {
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setShowCreateModal(false)
      setCreateMode('choose')
      toast.success('Requirement set created', { description: 'Starting import.' })
      navigate(`/requirements/sets/${doc.id}/import`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Create from PDF failed')
    },
  })

  const createManualMutation = useMutation({
    mutationFn: async (payload: {
      jurisdiction_id: string
      name: string
      document_type: string
      testing_frequency: string
      version?: string | null
      effective_date?: string | null
    }) => {
      const response = await api.post('/requirements/sets', payload)
      return response.data as { id: string }
    },
    onSuccess: (doc) => {
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setShowCreateModal(false)
      setCreateMode('choose')
      toast.success('Draft requirement set created')
      navigate(`/requirements/sets/${doc.id}/edit`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Create manual set failed')
    },
  })

  const sets = useMemo(() => data?.items ?? [], [data?.items])

  const sortLabel = (set: RequirementSetSummary) => (set.name || set.filename || '').trim()

  const formatTestingFrequency = (value?: string | null) => {
    if (!value) return 'N/A'
    return value
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  }

  const formatVersion = (set: RequirementSetSummary) => {
    const normalized = set.version?.trim()
    if (normalized) return normalized
    if (typeof set.current_version_number === 'number') {
      return `v${set.current_version_number}`
    }
    return 'N/A'
  }

  const sortedSets = useMemo(() => {
    const frequencyRank: Record<string, number> = {
      one_off: 0,
      monthly: 1,
      quarterly: 2,
      annually: 3,
    }
    const items = [...sets]
    const direction = sortDirection === 'asc' ? 1 : -1

    items.sort((a, b) => {
      const compareText = (left: string, right: string) =>
        left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' })

      let comparison = 0

      if (sortKey === 'name') {
        comparison = compareText(sortLabel(a), sortLabel(b))
      } else if (sortKey === 'status') {
        comparison = compareText(a.document_status || '', b.document_status || '')
      } else if (sortKey === 'version') {
        comparison = compareText(formatVersion(a), formatVersion(b))
      } else if (sortKey === 'testing_frequency') {
        const aRank = frequencyRank[a.testing_frequency || ''] ?? Number.MAX_SAFE_INTEGER
        const bRank = frequencyRank[b.testing_frequency || ''] ?? Number.MAX_SAFE_INTEGER
        if (aRank !== bRank) {
          comparison = aRank - bRank
        } else {
          comparison = compareText(a.testing_frequency || '', b.testing_frequency || '')
        }
      } else if (sortKey === 'requirements') {
        const totalComparison = a.requirements_total - b.requirements_total
        if (totalComparison !== 0) {
          comparison = totalComparison
        } else {
          comparison = a.requirements_active - b.requirements_active
        }
      }

      if (comparison === 0) {
        comparison = compareText(sortLabel(a), sortLabel(b))
      }

      return comparison * direction
    })

    return items
  }, [sets, sortDirection, sortKey])

  const onSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setSortDirection('asc')
  }

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return '↕'
    return sortDirection === 'asc' ? '↑' : '↓'
  }

  const sortAria = (key: SortKey): 'none' | 'ascending' | 'descending' => {
    if (sortKey !== key) return 'none'
    return sortDirection === 'asc' ? 'ascending' : 'descending'
  }

  const statusTone = (status: string) => {
    if (status === 'approved') return 'green'
    if (status === 'extraction_failed') return 'red'
    if (status === 'changes_requested') return 'amber'
    if (status === 'pending_approval') return 'amber'
    if (status.includes('pending') || status.includes('extract')) return 'blue'
    if (status === 'draft') return 'slate'
    return 'slate'
  }

  const buildMenuItems = (set: RequirementSetSummary) => {
    const label = set.name || set.filename
    const hasAny = set.requirements_total > 0
    const isArchivedSet = hasAny && set.requirements_active === 0
    const { canEdit } = getRequirementSetRouting(set, isAdminOrManager)

    const items: Array<{
      key: string
      label: string
      onSelect: () => void
      disabled?: boolean
      tone?: 'default' | 'destructive'
    }> = []

    items.push({
      key: 'view',
      label: 'View',
      onSelect: () => navigate(`/requirements/sets/${set.document_id}`),
    })
    if (isAdminOrManager && !isArchivedSet) {
      items.push({ key: 'form', label: 'Use as form questions', onSelect: () => navigate(`/library?${new URLSearchParams({ section: 'templates', kind: 'licence_application', sourceDocument: set.document_id, jurisdiction: set.jurisdiction_id || jurisdictionId || '' })}`) })
      items.push({ key: 'project', label: 'Use in a certification project', disabled: set.document_status !== 'approved' || useInProject.isPending, onSelect: () => useInProject.mutate(set.document_id) })
    }

    if (canEdit) {
      items.push({
        key: 'edit',
        label: 'Edit',
        onSelect: () => navigate(`/requirements/sets/${set.document_id}/edit`),
      })
    }

    if (isAdminOrManager && hasAny) {
      if (isArchivedSet) {
        items.push({
          key: 'restore',
          label: restoreMutation.isPending ? 'Restoring...' : 'Restore set',
          disabled: restoreMutation.isPending || deleteMutation.isPending,
          onSelect: () => restoreMutation.mutate(set.document_id),
        })
      } else {
        items.push({
          key: 'archive',
          label: archiveMutation.isPending ? 'Archiving...' : 'Archive set',
          disabled: archiveMutation.isPending || deleteMutation.isPending,
          onSelect: () =>
            setConfirm({
              title: 'Archive requirement set?',
              description: `Archive "${label}"? You can restore it later.`,
              confirmLabel: 'Archive',
              dangerDetails: ['The requirements will be hidden from active views and reports.'],
              onConfirm: () => archiveMutation.mutate(set.document_id),
            }),
        })
      }
    }

    if (isAdminOrManager) {
      items.push({
        key: 'delete',
        label: deleteMutation.isPending ? 'Deleting...' : 'Delete set',
        tone: 'destructive',
        disabled: deleteMutation.isPending || archiveMutation.isPending || restoreMutation.isPending,
        onSelect: () =>
          setConfirm({
            title: 'Delete requirement set?',
            description: `Delete "${label}"? This cannot be undone.`,
            confirmLabel: 'Delete',
            dangerDetails: [
              'Delete the requirement set and all requirements',
              'Delete evidence, review items, extracted data, and uploaded files',
            ],
            onConfirm: () => deleteMutation.mutate(set.document_id),
          }),
      })
    }

    return items
  }

  return (
    <div className="workflow-page requirements-page min-w-0 space-y-4">
      <header className="py-1">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-ink">Requirements</h1>
            {jurisdictionName ? (
              <div className="mt-1 text-sm text-muted">Jurisdiction: {jurisdictionName}</div>
            ) : (
              <div className="mt-1 text-sm text-muted">Select a jurisdiction to view sets.</div>
            )}
            <p className="mt-1 text-sm text-muted">
              Shared sources for certification assessments and licence application forms. Create requirements manually or import a document, then check their wording and source.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {isAdminOrManager ? (
              <Button
                variant="primary"
                onClick={() => {
                  if (!jurisdictionId) {
                    toast.info('Select a jurisdiction first.')
                    return
                  }
                  setCreateMode('choose')
                  setShowCreateModal(true)
                }}
              >
                Create requirement set
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      <Card className="workflow-toolbar p-4 sm:p-5">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium uppercase tracking-wide text-muted">
              Search
            </label>
            <input aria-label="Search"
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search sets..."
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium uppercase tracking-wide text-muted">
              Set status
            </label>
            <select aria-label="Set status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            >
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="uploaded">Uploaded</option>
              <option value="pending_extraction">Pending extraction</option>
              <option value="extracting">Extracting</option>
              <option value="extracted">Extracted</option>
              <option value="reviewed">Reviewed</option>
              <option value="pending_approval">Pending approval</option>
              <option value="changes_requested">Changes requested</option>
              <option value="approved">Approved</option>
              <option value="extraction_failed">Extraction failed</option>
              <option value="extraction_cancelled">Extraction cancelled</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium uppercase tracking-wide text-muted">
              Document category
            </label>
            <input type="text" maxLength={50} placeholder="All categories" aria-label="Document category"
              value={documentTypeFilter}
              onChange={(e) => setDocumentTypeFilter(e.target.value)}
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showEmptyDocs}
                onChange={(e) => setShowEmptyDocs(e.target.checked)}
                className="h-4 w-4 rounded border-line-strong"
             />
              Show empty sets
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showArchivedSets}
                onChange={(e) => setShowArchivedSets(e.target.checked)}
                className="h-4 w-4 rounded border-line-strong"
             />
              Show archived sets
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showArchivedDocuments}
                onChange={(e) => setShowArchivedDocuments(e.target.checked)}
                className="h-4 w-4 rounded border-line-strong"
             />
              Show archived sources
            </label>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setSearchParams({})
              setShowEmptyDocs(isAdminOrManager)
              setShowArchivedSets(false)
              setShowArchivedDocuments(false)
            }}
          >
            Clear filters
          </Button>
        </div>
      </Card>

      {!jurisdictionId ? (
        <Card className="p-6 text-sm text-muted">
          Select a jurisdiction to view requirement sets.
        </Card>
      ) : isError ? <Card className="p-5"><p role="alert">Requirement sets could not be loaded.</p><Button onClick={() => refetch()}>Try again</Button></Card> : isLoading ? (
        <Card className="p-6 text-sm text-muted">Loading...</Card>
      ) : sortedSets.length ? (
        <Card className="overflow-hidden"><div className="workflow-table-heading"><h2>Requirement sets</h2><p>{sortedSets.length} matching {sortedSets.length === 1 ? 'set' : 'sets'}</p></div>
          <div data-testid="requirements-sets-mobile-cards" className="space-y-3 p-3 lg:hidden">
            {sortedSets.map((set) => {
              const label = set.name || set.filename
              const { openPath, openLabel } = getRequirementSetRouting(set, isAdminOrManager)
              const hasAny = set.requirements_total > 0
              const isArchivedSet = hasAny && set.requirements_active === 0

              return (
                <div key={set.document_id} className="rounded-xl border border-line p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink break-words">
                        {label}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Badge tone="slate">{set.document_type.replace(/_/g, ' ')}</Badge>
                        <Badge tone={statusTone(set.document_status)}>
                          {set.document_status.replace(/_/g, ' ')}
                        </Badge>
                        {set.archived_at ? <Badge tone="amber">Source archived</Badge> : null}
                        {isArchivedSet ? <Badge tone="amber">Archived</Badge> : null}
                      </div>
                      <div className="mt-2 text-xs text-muted">
                        Requirements: {set.requirements_active}/{set.requirements_total}
                      </div>
                      <div className="mt-1 text-xs text-muted">
                        Version: {formatVersion(set)}
                      </div>
                      <div className="mt-1 text-xs text-muted">
                        Testing frequency: {formatTestingFrequency(set.testing_frequency)}
                      </div>
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      <LinkButton
                        to={openPath}
                        aria-label={`${openLabel} ${label}`}
                        variant="secondary"
                        size="sm"
                      >
                        {openLabel}
                      </LinkButton>
                      <DropdownMenu ariaLabel={`Actions for ${label}`} items={buildMenuItems(set)} />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="hidden lg:block">
            <Table>
              <THead>
                <tr>
                  <TH aria-sort={sortAria('name')}>
                    <button
                      type="button"
                      onClick={() => onSort('name')}
                      className="inline-flex items-center gap-1"
                    >
                      Requirement set
                      <span aria-hidden>{sortIndicator('name')}</span>
                    </button>
                  </TH>
                  <TH aria-sort={sortAria('status')}>
                    <button
                      type="button"
                      onClick={() => onSort('status')}
                      className="inline-flex items-center gap-1"
                    >
                      Status
                      <span aria-hidden>{sortIndicator('status')}</span>
                    </button>
                  </TH>
                  <TH aria-sort={sortAria('version')}>
                    <button
                      type="button"
                      onClick={() => onSort('version')}
                      className="inline-flex items-center gap-1"
                    >
                      Version
                      <span aria-hidden>{sortIndicator('version')}</span>
                    </button>
                  </TH>
                  <TH aria-sort={sortAria('testing_frequency')}>
                    <button
                      type="button"
                      onClick={() => onSort('testing_frequency')}
                      className="inline-flex items-center gap-1"
                    >
                      Testing frequency
                      <span aria-hidden>{sortIndicator('testing_frequency')}</span>
                    </button>
                  </TH>
                  <TH aria-sort={sortAria('requirements')}>
                    <button
                      type="button"
                      onClick={() => onSort('requirements')}
                      className="inline-flex items-center gap-1"
                    >
                      Requirements
                      <span aria-hidden>{sortIndicator('requirements')}</span>
                    </button>
                  </TH>
                  <TH className="w-[1%]">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {sortedSets.map((set) => {
                  const label = set.name || set.filename
                  const { openPath } = getRequirementSetRouting(set, isAdminOrManager)
                  const hasAny = set.requirements_total > 0
                  const isArchivedSet = hasAny && set.requirements_active === 0

                  return (
                    <TR key={set.document_id}>
                      <TD className="text-ink">
                        <Link
                          to={openPath}
                          className="font-semibold text-ink hover:underline break-words"
                        >
                          {label}
                        </Link>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                          <span>{set.document_type.replace(/_/g, ' ')}</span>
                          {set.archived_at ? <Badge tone="amber">Source archived</Badge> : null}
                        </div>
                      </TD>
                      <TD>
                        <Badge tone={statusTone(set.document_status)}>
                          {set.document_status.replace(/_/g, ' ')}
                        </Badge>
                      </TD>
                      <TD>{formatVersion(set)}</TD>
                      <TD>{formatTestingFrequency(set.testing_frequency)}</TD>
                      <TD>
                        <span className="text-ink">
                          {set.requirements_active}/{set.requirements_total}
                        </span>
                        {isArchivedSet ? (
                          <span className="ml-2">
                            <Badge tone="amber">Archived</Badge>
                          </span>
                        ) : null}
                      </TD>
                      <TD className="text-right">
                        <DropdownMenu ariaLabel={`Actions for ${label}`} items={buildMenuItems(set)} />
                      </TD>
                    </TR>
                  )
                })}
              </TBody>
            </Table>
          </div>
        </Card>
      ) : (
        <Card className="p-6 text-sm text-muted">No requirement sets found.</Card>
      )}

      <Modal
        open={showCreateModal}
        title="Create requirement set"
        description={jurisdictionName ? `Jurisdiction: ${jurisdictionName}` : undefined}
        onClose={() => {
          setShowCreateModal(false)
          setCreateMode('choose')
        }}
        size="lg"
      >
        {createMode === 'choose' ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => setCreateMode('pdf')}
              className="rounded-xl border border-line bg-surface p-4 text-left hover:bg-canvas"
            >
              <div className="text-sm font-semibold text-ink">Import from PDF</div>
              <div className="mt-1 text-xs text-muted">
                Upload a source PDF, extract requirements, review, and approve to publish.
              </div>
            </button>
            <button
              type="button"
              onClick={() => setCreateMode('manual')}
              className="rounded-xl border border-line bg-surface p-4 text-left hover:bg-canvas"
            >
              <div className="text-sm font-semibold text-ink">Create manually</div>
              <div className="mt-1 text-xs text-muted">
                Start a draft set and add requirements from scratch, then submit for approval.
              </div>
            </button>
          </div>
        ) : null}

            {createMode === 'pdf' ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (!jurisdictionId) return
                  const formData = new FormData(e.currentTarget)
                  formData.set('jurisdiction_id', jurisdictionId)
                  createFromPdfMutation.mutate(formData)
                }}
                className="space-y-4"
              >
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Requirement Set Name
                  </label>
                  <input aria-label="Requirement Set Name"
                    type="text"
                    name="name"
                    required
                    placeholder="Requirement set name"
                    className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                 />
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Document category
                    </label>
                    <input type="text" maxLength={50} placeholder="Enter a category" defaultValue="other" aria-label="Document category"
                      name="document_type"
                      required
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Testing Frequency
                    </label>
                    <select aria-label="Testing Frequency"
                      name="testing_frequency"
                      required
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                    >
                      <option value="one_off">One off</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annually">Annually</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Source PDF
                  </label>
                  <input aria-label="Source PDF"
                    type="file"
                    name="file"
                    accept=".pdf"
                    required
                    className="w-full text-sm text-muted file:mr-4 file:rounded file:border-0 file:bg-info-soft file:px-4 file:py-2 file:text-sm file:font-semibold file:text-info hover:file:bg-info-soft"
                 />
                </div>

                <div className="flex flex-wrap justify-end gap-2 pt-2">
                  <Button
                    type="button"
                    onClick={() => setCreateMode('choose')}
                  >
                    Back
                  </Button>
                  <Button
                    type="submit"
                    disabled={createFromPdfMutation.isPending}
                    variant="primary"
                  >
                    {createFromPdfMutation.isPending ? 'Creating...' : 'Create & Import'}
                  </Button>
                </div>
              </form>
            ) : null}

            {createMode === 'manual' ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (!jurisdictionId) return
                  const formData = new FormData(e.currentTarget)
                  const effectiveDate = String(formData.get('effective_date') || '').trim()
                  createManualMutation.mutate({
                    jurisdiction_id: jurisdictionId,
                    name: String(formData.get('name') || '').trim(),
                    document_type: String(formData.get('document_type') || '').trim(),
                    testing_frequency: String(formData.get('testing_frequency') || '').trim(),
                    version: String(formData.get('version') || '').trim() || null,
                    effective_date: effectiveDate ? `${effectiveDate}T00:00:00Z` : null,
                  })
                }}
                className="space-y-4"
              >
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Requirement Set Name
                  </label>
                  <input aria-label="Requirement Set Name"
                    type="text"
                    name="name"
                    required
                    placeholder="Requirement set name"
                    className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                 />
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Document category
                    </label>
                    <input type="text" maxLength={50} placeholder="Enter a category" defaultValue="other" aria-label="Document category"
                      name="document_type"
                      required
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Testing Frequency
                    </label>
                    <select aria-label="Testing Frequency"
                      name="testing_frequency"
                      required
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                    >
                      <option value="one_off">One off</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="annually">Annually</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Version (optional)
                    </label>
                    <input aria-label="Version (optional)"
                      type="text"
                      name="version"
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                   />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-ink">
                      Effective Date (optional)
                    </label>
                    <input aria-label="Effective Date (optional)"
                      type="date"
                      name="effective_date"
                      className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                   />
                  </div>
                </div>

                <div className="flex flex-wrap justify-end gap-2 pt-2">
                  <Button
                    type="button"
                    onClick={() => setCreateMode('choose')}
                  >
                    Back
                  </Button>
                  <Button
                    type="submit"
                    disabled={createManualMutation.isPending}
                    variant="primary"
                  >
                    {createManualMutation.isPending ? 'Creating...' : 'Create Draft Set'}
                  </Button>
                </div>
              </form>
            ) : null}
      </Modal>

      <DecisionModal
        open={!!confirm}
        title={confirm?.title || ''}
        description={confirm?.description || ''}
        confirmLabel={confirm?.confirmLabel || 'Confirm'}
        dangerDetails={confirm?.dangerDetails}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          const handler = confirm?.onConfirm
          setConfirm(null)
          handler?.()
        }}
        isWorking={archiveMutation.isPending || restoreMutation.isPending || deleteMutation.isPending}
      />
    </div>
  )
}
