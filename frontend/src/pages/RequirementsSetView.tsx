import { formatDate } from '../utils/dateFormat'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import type {
  CertificationProjectFromDocumentResponse,
  Document,
  ExtractedRequirement,
  ExtractionReorderRequest,
  ExtractionReorderResponse,
  PaginatedResponse,
  RequirementSetSummary,
  RequirementSetVersion,
  RequirementWithStatus,
} from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import DecisionModal from '../components/ui/DecisionModal'
import Modal from '../components/ui/Modal'
import DropdownMenu from '../components/ui/DropdownMenu'
import LoadError from '../components/ui/LoadError'
import SectionNav from '../components/ui/SectionNav'
import HierarchyDepthSelect from '../components/HierarchyDepthSelect'
import { useHierarchyDepth } from '../hooks/useHierarchyDepth'
import { normalizeRichText, stripHtml } from '../utils/richText'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { buildHierarchyTree, flattenHierarchyTree } from '../utils/requirementHierarchy'
import { notifyApiError } from '../utils/notify'

type PendingExtractionDelete = {
  id: string
  reference_id: string
  title: string | null
}

type ExtractionEditDraft = {
  id: string
  reference_id: string
  title: string
  text: string
  requirement_type: string
  status: string
  needs_review: boolean
  review_reason: string | null
}

export default function RequirementsSetView() {
  const { documentId } = useParams<{ documentId: string }>()
  const { user } = useAuth()
  const toast = useToast()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const queryClient = useQueryClient()
  const hierarchyDepth = useHierarchyDepth()
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin'
  const isAdminOrManager = isAdmin || user?.role === 'manager'
  const canApprove = isAdminOrManager || user?.role === 'approver'

  const [filters, setFilters] = useState({
    search: '',
  })
  const [metadataForm, setMetadataForm] = useState({
    name: '',
    document_type: '',
    version: '',
    effective_date: '',
    testing_frequency: '',
  })
  const [metadataDirty, setMetadataDirty] = useState(false)
  const [metadataError, setMetadataError] = useState<string | null>(null)
  const [showDeleteSetModal, setShowDeleteSetModal] = useState(false)
  const [decisionAction, setDecisionAction] = useState<'approve' | 'reject' | null>(null)
  const [decisionComment, setDecisionComment] = useState('')
  const [decisionCommentError, setDecisionCommentError] = useState<string | null>(null)
  const [showRejectedExtractions, setShowRejectedExtractions] = useState(false)
  const [sourceView, setSourceView] = useState('extraction')
  const [extractionPage, setExtractionPage] = useState(0)
  const [showAllExtractions, setShowAllExtractions] = useState(false)
  useEffect(() => setExtractionPage(0), [filters.search, showRejectedExtractions, documentId])
  const [pendingExtractionDelete, setPendingExtractionDelete] = useState<PendingExtractionDelete | null>(null)
  const [draggingExtractionId, setDraggingExtractionId] = useState<string | null>(null)
  const [editingExtraction, setEditingExtraction] = useState<ExtractionEditDraft | null>(null)
  const [extractionEditError, setExtractionEditError] = useState<string | null>(null)

  useEffect(() => {
    setFilters({ search: '' })
    setMetadataForm({
      name: '',
      document_type: '',
      version: '',
      effective_date: '',
      testing_frequency: '',
    })
    setMetadataDirty(false)
    setMetadataError(null)
    setShowDeleteSetModal(false)
    setDecisionAction(null)
    setDecisionComment('')
    setDecisionCommentError(null)
    setShowRejectedExtractions(false)
    setPendingExtractionDelete(null)
    setDraggingExtractionId(null)
    setEditingExtraction(null)
    setExtractionEditError(null)
  }, [documentId])

  const { data: doc, isLoading: documentLoading, isError: documentError, refetch: refetchDocument } = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const response = await api.get<Document>(`/documents/${documentId}`)
      return response.data
    },
    enabled: !!documentId,
  })

  useEffect(() => {
    if (!doc) return
    if (metadataDirty) return
    const effectiveDate = doc.effective_date
      ? new Date(doc.effective_date).toISOString().slice(0, 10)
      : ''
    setMetadataForm({
      name: doc.name || '',
      document_type: doc.document_type || '',
      version: doc.version || '',
      effective_date: effectiveDate,
      testing_frequency: doc.testing_frequency || '',
    })
  }, [doc, metadataDirty])

  useEffect(() => {
    if (!doc?.jurisdiction_id) return
    if (jurisdictionId && doc.jurisdiction_id !== jurisdictionId) {
      setJurisdictionId(doc.jurisdiction_id)
    }
  }, [doc?.jurisdiction_id, jurisdictionId, setJurisdictionId])

  const activeExtractionRunId = doc?.current_extraction?.id || doc?.current_extraction_id || null

  const { data: setSummaryResponse } = useQuery({
    queryKey: ['requirements-set-summary', documentId],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1')
      params.set('include_archived_documents', 'true')
      params.set('include_empty_sets', 'true')
      params.set('include_archived_sets', 'true')
      params.set('document_id', documentId || '')
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data
    },
    enabled: !!documentId,
  })

  const setSummary = setSummaryResponse?.items?.[0]
  const hasAny = (setSummary?.requirements_total || 0) > 0
  const hasActive = (setSummary?.requirements_active || 0) > 0
  const isArchivedSet = hasAny && !hasActive
  const versionsQuery = useQuery({
    queryKey: ['requirement-set-versions', documentId],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<RequirementSetVersion>>(
        `/requirements/sets/${documentId}/versions`
      )
      return response.data
    },
    enabled: !!documentId,
  })
  const versions = versionsQuery.data?.items || []
  const latestDraftVersion = versions.find((version) => version.status === 'draft')
  const pendingApprovalVersion = versions.find((version) => version.status === 'pending_approval')
  const currentVersion = versions.find((version) => version.is_current)

  const archiveMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/requirements/by-document/${documentId}/archive`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Archive failed')
    },
  })

  const restoreMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/requirements/by-document/${documentId}/restore`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Restore failed')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/requirements/sets/${documentId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      navigate('/requirements')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Delete failed')
    },
  })

  const updateMetadataMutation = useMutation({
    mutationFn: async (payload: {
      name?: string | null
      document_type?: string | null
      version?: string | null
      effective_date?: string | null
      testing_frequency?: string | null
    }) => {
      await api.put(`/documents/${documentId}`, payload)
      const response = await api.get<Document>(`/documents/${documentId}`)
      return response.data
    },
    onSuccess: (updatedDoc) => {
      setMetadataDirty(false)
      queryClient.setQueryData(['document', documentId], updatedDoc)
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Update failed')
    },
  })

  const approveMutation = useMutation({
    mutationFn: async (comment?: string) => {
      await api.post(`/documents/${documentId}/approve`, null, {
        params: comment ? { comment } : undefined,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Approve failed')
    },
  })

  const cloneVersionMutation = useMutation({
    mutationFn: async () => {
      const sourceVersion =
        currentVersion ||
        versions.find((version) => version.status === 'approved') ||
        versions[0]
      if (!sourceVersion) {
        throw new Error('No source version available for clone')
      }
      await api.post(`/requirements/sets/${documentId}/versions/clone`, {
        source_version_id: sourceVersion.id,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirement-set-versions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Clone version failed')
    },
  })

  const submitVersionMutation = useMutation({
    mutationFn: async () => {
      if (!latestDraftVersion) {
        throw new Error('No draft version to submit')
      }
      await api.post(`/requirements/sets/${documentId}/versions/${latestDraftVersion.id}/submit`, {
        change_summary: 'Submitted for approval from requirement set view',
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirement-set-versions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Submit version failed')
    },
  })

  const approveVersionMutation = useMutation({
    mutationFn: async () => {
      if (!pendingApprovalVersion) {
        throw new Error('No version pending approval')
      }
      await api.post(`/requirements/sets/${documentId}/versions/${pendingApprovalVersion.id}/approve`, {
        comment: 'Approved from requirement set view',
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirement-set-versions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Approve version failed')
    },
  })

  const rejectMutation = useMutation({
    mutationFn: async (comment: string) => {
      await api.post(`/documents/${documentId}/reject`, null, {
        params: { comment },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Reject failed')
    },
  })

  const updateExtractionMutation = useMutation({
    mutationFn: async (payload: {
      extractionId: string
      data: {
        reference_id?: string
        title?: string | null
        text?: string
        requirement_type?: string
        status?: string
      }
    }) => {
      const response = await api.put<ExtractedRequirement>(
        `/documents/${documentId}/extractions/${payload.extractionId}`,
        payload.data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      setExtractionEditError(null)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Update extracted requirement failed')
    },
  })

  const feedbackMutation = useMutation({
    mutationFn: async (payload: {
      extractionId: string
      action: 'accept' | 'edit' | 'reject'
      corrected_reference_id?: string
      corrected_text?: string
    }) => {
      const response = await api.post(
        `/documents/${documentId}/extractions/${payload.extractionId}/feedback`,
        {
          action: payload.action,
          corrected_reference_id: payload.corrected_reference_id,
          corrected_text: payload.corrected_text,
        }
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      setExtractionEditError(null)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Submit extraction feedback failed')
    },
  })

  const softDeleteExtractionMutation = useMutation({
    mutationFn: async (extractionId: string) => {
      const response = await api.put<ExtractedRequirement>(
        `/documents/${documentId}/extractions/${extractionId}`,
        {
          status: 'rejected',
          needs_review: false,
          review_reason: 'rejected_by_reviewer',
        }
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      setPendingExtractionDelete(null)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Delete extracted requirement failed')
    },
  })

  const reorderExtractionMutation = useMutation({
    mutationFn: async (orderedIds: string[]) => {
      if (!activeExtractionRunId) {
        throw new Error('No active extraction run available for reorder')
      }
      const payload: ExtractionReorderRequest = {
        run_id: activeExtractionRunId,
        ordered_ids: orderedIds,
      }
      const response = await api.post<ExtractionReorderResponse>(
        `/documents/${documentId}/extractions/reorder`,
        payload
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
      setDraggingExtractionId(null)
    },
    onError: (error: unknown) => {
      setDraggingExtractionId(null)
      notifyApiError(toast, error, 'Reorder extracted requirements failed')
    },
  })

  const createProjectFromSetMutation = useMutation({
    mutationFn: async () => {
      if (!documentId) {
        throw new Error('Missing requirement set id')
      }
      const response = await api.post<CertificationProjectFromDocumentResponse>(
        `/certification-projects/from-document/${documentId}`
      )
      return response.data
    },
    onSuccess: ({ created, project }) => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      navigate(`/certification-projects?project=${project.id}`)
      if (!created) {
        toast.info('Existing certification project opened for this requirement set.')
      }
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Create certification project failed')
    },
  })

  const { data, isLoading } = useQuery({
    queryKey: ['requirements', 'set', documentId],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.append('document_id', documentId || '')
      params.append('active_only', 'true')
      params.append('limit', '10000')
      const response = await api.get<PaginatedResponse<RequirementWithStatus>>(
        `/requirements?${params.toString()}`
      )
      return response.data
    },
    enabled: !!documentId,
  })

  const { data: extractionResults } = useQuery({
    queryKey: ['document-extractions', documentId, activeExtractionRunId, 'view'],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.append('limit', '10000')
      if (activeExtractionRunId) {
        params.append('run_id', activeExtractionRunId)
      }
      const response = await api.get<PaginatedResponse<ExtractedRequirement>>(
        `/documents/${documentId}/extractions?${params.toString()}`
      )
      return response.data
    },
    enabled: !!documentId && !!activeExtractionRunId,
  })

  const { data: extractionSourceData } = useQuery({
    queryKey: ['document-extractions', documentId, 'flags', 'view'],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.append('limit', '10000')
      const response = await api.get<PaginatedResponse<ExtractedRequirement>>(
        `/documents/${documentId}/extractions?${params.toString()}`
      )
      return response.data
    },
    enabled: !!documentId,
  })

  const allRequirements = useMemo(
    () =>
      flattenHierarchyTree(
        buildHierarchyTree(data?.items || [], {
          getId: (item) => item.id,
          getReferenceId: (item) => item.reference_id,
          getParentId: (item) => item.parent_id,
          getSortOrder: (item) => item.sort_order,
        })
      ),
    [data?.items]
  )

  const flattenedRequirements = allRequirements.filter(({ item }) => {
    const query = filters.search.trim().toLowerCase()
    return !query || `${item.reference_id} ${item.title || ''} ${stripHtml(item.text || '')}`.toLowerCase().includes(query)
  })

  const visibleRequirements = flattenedRequirements.filter(({ depth }) => hierarchyDepth.levels === 'all' || depth < hierarchyDepth.levels)

  const extractionById = useMemo(() => {
    const map = new Map<string, ExtractedRequirement>()
    ;(extractionSourceData?.items || []).forEach((item) => {
      map.set(item.id, item)
    })
    return map
  }, [extractionSourceData?.items])

  const allExtractionItems = extractionResults?.items || []
  const visibleExtractionItems = showRejectedExtractions
    ? allExtractionItems
    : allExtractionItems.filter((item) => item.status !== 'rejected')
  const totalRejectedExtractions = allExtractionItems.filter((item) => item.status === 'rejected').length
  const extractionPageCount = Math.max(1, Math.ceil(visibleExtractionItems.length / 25))
  const currentExtractionPage = Math.min(extractionPage, extractionPageCount - 1)
  const pagedExtractions = showAllExtractions ? visibleExtractionItems : visibleExtractionItems.slice(currentExtractionPage * 25, (currentExtractionPage + 1) * 25)
  const hiddenRejectedExtractions = Math.max(0, allExtractionItems.length - visibleExtractionItems.length)
  const hasActiveExtractionRun = !!activeExtractionRunId
  const canEditExtractedRequirements =
    isAdminOrManager &&
    !isArchivedSet &&
    !!doc &&
    ['draft', 'extracted', 'reviewed', 'changes_requested', 'pending_approval'].includes(doc.status)

  const reorderExtraction = (movingId: string, targetId: string, placement: 'before' | 'after') => {
    if (reorderExtractionMutation.isPending || !activeExtractionRunId) return

    const orderedIds = allExtractionItems.map((item) => item.id)
    if (!orderedIds.length || movingId === targetId) return
    const movingIndex = orderedIds.indexOf(movingId)
    if (movingIndex < 0) return

    const nextIds = [...orderedIds]
    nextIds.splice(movingIndex, 1)
    const targetIndex = nextIds.indexOf(targetId)
    if (targetIndex < 0) return
    const insertIndex = placement === 'before' ? targetIndex : targetIndex + 1
    nextIds.splice(insertIndex, 0, movingId)
    reorderExtractionMutation.mutate(nextIds)
  }

  const moveVisibleExtraction = (extractionId: string, direction: 'up' | 'down') => {
    const visibleIds = visibleExtractionItems.map((item) => item.id)
    const currentIndex = visibleIds.indexOf(extractionId)
    if (currentIndex < 0) return
    if (direction === 'up' && currentIndex === 0) return
    if (direction === 'down' && currentIndex === visibleIds.length - 1) return

    const targetId =
      direction === 'up' ? visibleIds[currentIndex - 1] : visibleIds[currentIndex + 1]
    if (!targetId) return
    reorderExtraction(extractionId, targetId, direction === 'up' ? 'before' : 'after')
  }

  const openExtractionEditor = (req: ExtractedRequirement) => {
    setExtractionEditError(null)
    setEditingExtraction({
      id: req.id,
      reference_id: req.reference_id || '',
      title: req.title || '',
      text: req.text || '',
      requirement_type: req.requirement_type || 'mandatory',
      status: req.status || 'pending',
      needs_review: !!req.needs_review,
      review_reason: req.review_reason || null,
    })
  }

  const requestExtractionDelete = (req: Pick<ExtractedRequirement, 'id' | 'reference_id' | 'title'>) => {
    setPendingExtractionDelete({
      id: req.id,
      reference_id: req.reference_id || '-',
      title: req.title || null,
    })
  }

  const confirmPendingExtractionDelete = () => {
    if (!pendingExtractionDelete) return
    const extractionId = pendingExtractionDelete.id
    softDeleteExtractionMutation.mutate(extractionId, {
      onSuccess: () => {
        if (editingExtraction?.id === extractionId) {
          setEditingExtraction(null)
        }
      },
    })
  }

  const submitExtractionEdit = () => {
    if (!editingExtraction) return

    const referenceId = editingExtraction.reference_id.trim()
    const text = editingExtraction.text.trim()
    if (!referenceId) {
      setExtractionEditError('Reference is required.')
      return
    }
    if (!text) {
      setExtractionEditError('Text is required.')
      return
    }

    const draft = editingExtraction
    updateExtractionMutation.mutate(
      {
        extractionId: draft.id,
        data: {
          reference_id: referenceId,
          title: draft.title.trim() || null,
          text,
          requirement_type: draft.requirement_type,
          status: draft.status,
        },
      },
      {
        onSuccess: () => {
          if (draft.needs_review) {
            feedbackMutation.mutate(
              {
                extractionId: draft.id,
                action: 'edit',
                corrected_reference_id: referenceId,
                corrected_text: text,
              },
              {
                onSuccess: () => {
                  setEditingExtraction(null)
                },
              }
            )
            return
          }
          setEditingExtraction(null)
        },
      }
    )
  }

  const openDecision = (action: 'approve' | 'reject') => {
    setDecisionAction(action)
    setDecisionComment('')
    setDecisionCommentError(null)
  }

  const handleDecisionConfirm = () => {
    if (!decisionAction) return
    const trimmedComment = decisionComment.trim()
    if (decisionAction === 'reject' && !trimmedComment) {
      setDecisionCommentError('Rejection comment is required.')
      return
    }
    setDecisionCommentError(null)
    if (decisionAction === 'approve') {
      approveMutation.mutate(trimmedComment || undefined, {
        onSuccess: () => {
          setDecisionAction(null)
          setDecisionComment('')
        },
      })
      return
    }
    rejectMutation.mutate(trimmedComment, {
      onSuccess: () => {
        setDecisionAction(null)
        setDecisionComment('')
      },
    })
  }

  if (documentLoading) return <p role="status" className="py-8 text-muted">Loading requirement set…</p>
  if (documentError) return <LoadError subject="This requirement set" onRetry={() => refetchDocument()} />

  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">
            {doc?.name || doc?.filename || 'Requirements Set'}
          </h1>
          {doc?.jurisdiction_id && (
            <div className="mt-1 text-sm text-muted">
              Jurisdiction:{' '}
              {jurisdictionById[doc.jurisdiction_id]?.name || doc.jurisdiction_id}
            </div>
          )}
          <p className="text-sm text-muted mt-1">
            Shared requirements can define a certification baseline or supply questions for an application form.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/requirements" className="text-sm text-muted hover:text-ink">
            &larr; Back to Requirements
          </Link>

          {isAdminOrManager && documentId ? (
            <Link
              to={`/requirements/sets/${documentId}/edit`}
              className="inline-flex rounded-md bg-strong px-3 py-1.5 text-sm font-medium text-white hover:bg-strong"
            >
              Edit
            </Link>
          ) : null}
          {isAdminOrManager && documentId ? (
            <Link to={`/library?${new URLSearchParams({ section: 'templates', kind: 'licence_application', sourceDocument: documentId, jurisdiction: doc?.jurisdiction_id || jurisdictionId || '' })}`} className="inline-flex rounded-md border border-line px-3 py-1.5 text-sm font-medium text-accent hover:bg-subtle">Use as form questions</Link>
          ) : null}
          {isAdminOrManager && documentId ? (
            <button
              type="button"
              onClick={() => createProjectFromSetMutation.mutate()}
              disabled={createProjectFromSetMutation.isPending || doc?.status !== 'approved' || !versions.some((version) => version.status === 'approved')}
              title={doc?.status !== 'approved' || !versions.some((version) => version.status === 'approved') ? 'Approve a requirement version before using it as a certification baseline.' : undefined}
              className="inline-flex rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50"
            >
              {createProjectFromSetMutation.isPending
                ? 'Opening project...'
                : 'Use in a certification project'}
            </button>
          ) : null}

          {canApprove && doc?.status === 'pending_approval' ? (
            <>
              <button
                type="button"
                onClick={() => openDecision('approve')}
                disabled={approveMutation.isPending || rejectMutation.isPending}
                className="inline-flex rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {approveMutation.isPending ? 'Approving...' : 'Approve'}
              </button>
              <button
                type="button"
                onClick={() => openDecision('reject')}
                disabled={approveMutation.isPending || rejectMutation.isPending}
                className="inline-flex rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
              </button>
            </>
          ) : null}

          {isAdminOrManager && <DropdownMenu ariaLabel="Requirement set actions" disabled={deleteMutation.isPending || archiveMutation.isPending || restoreMutation.isPending} items={[
            ...(hasAny ? [{ key: 'archive', label: isArchivedSet ? 'Restore Set' : 'Archive Set', onSelect: () => isArchivedSet ? restoreMutation.mutate() : archiveMutation.mutate() }] : []),
            ...(doc?.status !== 'approved' && !versions.some(version => version.status === 'approved') ? [{ key: 'delete', label: 'Delete Set', tone: 'destructive' as const, onSelect: () => setShowDeleteSetModal(true) }] : []),
          ]} />}

        </div>
      </div>

      <details className="mb-4 rounded-lg border border-line bg-surface p-4">
        <summary className="cursor-pointer font-semibold text-ink">Baseline versions <span className="ml-2 text-xs font-normal text-muted">{currentVersion ? `Current: v${currentVersion.version_number} · ${currentVersion.status}` : "No approved baseline"}</span></summary>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="mt-4 text-sm font-semibold text-ink">Version history & actions</h2>
            <p className="mt-1 text-xs text-muted">
              Current baseline: {currentVersion ? `v${currentVersion.version_number} (${currentVersion.status})` : 'None'}
            </p>
          </div>
          {isAdminOrManager ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => cloneVersionMutation.mutate()}
                disabled={cloneVersionMutation.isPending || !documentId}
                className="inline-flex rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
              >
                {cloneVersionMutation.isPending ? 'Cloning...' : 'Clone to Draft'}
              </button>
              <button
                type="button"
                onClick={() => submitVersionMutation.mutate()}
                disabled={submitVersionMutation.isPending || !latestDraftVersion}
                className="inline-flex rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
              >
                {submitVersionMutation.isPending ? 'Submitting...' : 'Submit Draft'}
              </button>
              {canApprove ? (
                <button
                  type="button"
                  onClick={() => approveVersionMutation.mutate()}
                  disabled={approveVersionMutation.isPending || !pendingApprovalVersion}
                  className="inline-flex rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {approveVersionMutation.isPending ? 'Approving...' : 'Approve Version'}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="mt-3 max-h-40 overflow-y-auto rounded-md border border-line">
          <table className="min-w-full text-xs">
            <thead className="bg-canvas text-muted">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Version</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((version) => (
                <tr key={version.id} className="border-t border-line">
                  <td className="px-3 py-2 text-ink">
                    v{version.version_number} {version.is_current ? '(current)' : ''}
                  </td>
                  <td className="px-3 py-2 text-ink">{version.status}</td>
                  <td className="px-3 py-2 text-muted">
                    {formatDate(version.created_at)}
                  </td>
                </tr>
              ))}
              {versions.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-3 text-muted">
                    No requirement set versions available.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </details>

      {canApprove ? (
        <details className="rounded-lg border border-line bg-surface p-4 mb-4">
          <summary className="cursor-pointer font-semibold text-ink">Requirement set details</summary>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              const name = metadataForm.name.trim()
              const documentType = metadataForm.document_type.trim()
              if (!documentType) {
                setMetadataError('Document category is required')
                return
              }
              setMetadataError(null)
              const version = metadataForm.version.trim()
              const effectiveDate = metadataForm.effective_date.trim()
              updateMetadataMutation.mutate({
                name: name ? name : null,
                document_type: documentType,
                version: version ? version : null,
                effective_date: effectiveDate ? `${effectiveDate}T00:00:00Z` : null,
                testing_frequency: metadataForm.testing_frequency || null,
              })
            }}
            className="mt-4 grid grid-cols-1 gap-4 items-end md:grid-cols-6"
          >
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-ink mb-1">
                Requirement Set Name
              </label>
              <input
                type="text"
                aria-label="Requirement Set Name"
                value={metadataForm.name}
                onChange={(e) => {
                  setMetadataDirty(true)
                  setMetadataForm((prev) => ({ ...prev, name: e.target.value }))
                }}
                placeholder="Requirement set name"
                className="w-full px-3 py-2 border border-line-strong rounded-md"
             />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">Document category</label>
              <input type="text" maxLength={50} placeholder="Enter a category"
                aria-label="Document category"
                value={metadataForm.document_type}
                onChange={(e) => {
                  setMetadataDirty(true)
                  setMetadataError(null)
                  setMetadataForm((prev) => ({ ...prev, document_type: e.target.value }))
                }}
                className={`w-full px-3 py-2 border rounded-md ${
                  metadataError ? 'border-danger-line' : 'border-line-strong'
                }`}
                required
              />
              {metadataError ? (
                <p className="mt-1 text-xs text-danger">{metadataError}</p>
              ) : null}
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Testing Frequency
              </label>
              <select
                aria-label="Testing Frequency"
                value={metadataForm.testing_frequency}
                onChange={(e) => {
                  setMetadataDirty(true)
                  setMetadataForm((prev) => ({ ...prev, testing_frequency: e.target.value }))
                }}
                className="w-full px-3 py-2 border border-line-strong rounded-md"
              >
                <option value="">Select frequency...</option>
                <option value="one_off">One off</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="annually">Annually</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Version (optional)
              </label>
              <input
                type="text"
                aria-label="Version (optional)"
                value={metadataForm.version}
                onChange={(e) => {
                  setMetadataDirty(true)
                  setMetadataForm((prev) => ({ ...prev, version: e.target.value }))
                }}
                className="w-full px-3 py-2 border border-line-strong rounded-md"
             />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Effective Date (optional)
              </label>
              <input
                type="date"
                aria-label="Effective Date (optional)"
                value={metadataForm.effective_date}
                onChange={(e) => {
                  setMetadataDirty(true)
                  setMetadataForm((prev) => ({ ...prev, effective_date: e.target.value }))
                }}
                className="w-full px-3 py-2 border border-line-strong rounded-md"
             />
            </div>
            <div className="md:col-span-6 flex items-center justify-end gap-2">
              {metadataDirty ? (
                <span className="text-xs text-muted">Unsaved changes</span>
              ) : null}
              <button
                type="submit"
                disabled={updateMetadataMutation.isPending || !documentId}
                className="inline-flex rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50"
              >
                {updateMetadataMutation.isPending ? 'Saving...' : 'Save Details'}
              </button>
            </div>
          </form>
        </details>
      ) : null}

      {hasActiveExtractionRun && <SectionNav label="Requirement set views" value={sourceView} onChange={setSourceView} items={[{id: 'extraction', label: 'Extracted sections'}, {id: 'requirements', label: 'Requirement library'}]} />}
      <div className="bg-surface rounded-lg border border-line p-4 my-4">
        <div className="grid grid-cols-1 gap-4">
          <div>
            <label className="block text-sm font-medium text-ink mb-1">Search</label>
            <input
              type="text"
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              placeholder="Search requirements..."
              aria-label="Requirements search"
              className="w-full px-3 py-2 border border-line-strong rounded-md"
            />
          </div>
        </div>
      </div>

      <section hidden={sourceView !== 'extraction'} aria-label="Extracted sections">
      {hasActiveExtractionRun ? (
        <div className="bg-surface rounded-lg border border-line p-4 mb-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 id="extracted-requirements" className="scroll-mt-24 text-sm font-semibold text-ink">Extracted Requirements</h2>
            <div className="flex flex-wrap items-center gap-3">
              {totalRejectedExtractions > 0 ? (
                <label className="inline-flex items-center gap-2 text-xs text-ink">
                  <input
                    type="checkbox"
                    checked={showRejectedExtractions}
                    onChange={(event) => setShowRejectedExtractions(event.target.checked)}
                    className="h-4 w-4 rounded border-line-strong"
                 />
                  Show rejected ({totalRejectedExtractions})
                </label>
              ) : null}
              <Link
                to={`/requirements/sets/${documentId}/import`}
                className="text-xs text-info hover:underline"
              >
                Open Import Workspace
              </Link>
            </div>
          </div>
          {extractionResults ? (
            <>
              <div className="mb-3 text-xs text-muted">
                Showing {pagedExtractions.length} of {visibleExtractionItems.length} matching sections · {extractionResults.total} total
                {visibleExtractionItems.filter((item) => item.needs_review && item.status !== 'rejected').length > 0
                  ? ` • ${visibleExtractionItems.filter((item) => item.needs_review && item.status !== 'rejected').length} flagged`
                  : ''}
              </div>
              {visibleExtractionItems.length > 25 && <nav aria-label="Source requirement pages" className="mb-4 flex flex-wrap items-center justify-between gap-3 text-sm">
                <label className="inline-flex items-center gap-2"><input type="checkbox" checked={showAllExtractions} onChange={event => setShowAllExtractions(event.target.checked)} />Show all sections</label>
                {!showAllExtractions && <div className="flex flex-wrap items-center gap-2"><button className="rounded-md border border-line-strong px-3 py-2 disabled:opacity-50" disabled={currentExtractionPage === 0} onClick={() => { setExtractionPage(currentExtractionPage - 1); requestAnimationFrame(() => document.getElementById('extracted-requirements')?.scrollIntoView({ block: 'start' })) }}>Previous page</button><span>Page {currentExtractionPage + 1} of {extractionPageCount}</span><button className="rounded-md border border-line-strong px-3 py-2 disabled:opacity-50" disabled={currentExtractionPage + 1 >= extractionPageCount} onClick={() => { setExtractionPage(currentExtractionPage + 1); requestAnimationFrame(() => document.getElementById('extracted-requirements')?.scrollIntoView({ block: 'start' })) }}>Next page</button></div>}
              </nav>}
              {!showRejectedExtractions && hiddenRejectedExtractions > 0 ? (
                <div className="mb-3 rounded-md border border-line bg-canvas px-3 py-2 text-xs text-ink">
                  {hiddenRejectedExtractions} rejected item(s) hidden.
                </div>
              ) : null}

              {visibleExtractionItems.length ? (
                <div className="space-y-3">
                  <div className="space-y-3 lg:hidden">
                    {pagedExtractions.map((req, pageIndex) => {
                      const visibleIndex = showAllExtractions ? pageIndex : currentExtractionPage * 25 + pageIndex
                      const canMoveUp = visibleIndex > 0
                      const canMoveDown = visibleIndex < visibleExtractionItems.length - 1
                      const isRejected = req.status === 'rejected'
                      return (
                        <div
                          key={req.id}
                          className={`rounded-lg border p-3 ${
                            isRejected ? 'border-danger-line bg-danger-soft' : 'border-line'
                          }`}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <div className="text-sm font-medium text-ink">{req.reference_id || '-'}</div>
                              {req.title ? <div className="text-xs text-muted">{req.title}</div> : null}
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {req.needs_review ? (
                                <span className="rounded bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning">
                                  Flagged
                                </span>
                              ) : null}
                              {isRejected ? (
                                <span className="rounded bg-danger-soft px-2 py-0.5 text-[10px] font-semibold text-danger">
                                  Rejected
                                </span>
                              ) : null}
                            </div>
                          </div>
                          {req.needs_review ? (
                            <div className="mt-2 text-xs text-warning">
                              {req.review_reason || 'needs_review'}
                            </div>
                          ) : null}
                          <p className="mt-2 whitespace-pre-line break-words text-sm text-ink">{req.text}</p>
                          {canEditExtractedRequirements ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => openExtractionEditor(req)}
                                disabled={updateExtractionMutation.isPending || feedbackMutation.isPending}
                                aria-label={`Edit extracted requirement ${req.reference_id || req.id}`}
                                className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                              >
                                Edit
                              </button>
                              {!isRejected ? (
                                <button
                                  type="button"
                                  onClick={() => requestExtractionDelete(req)}
                                  disabled={softDeleteExtractionMutation.isPending}
                                  className="rounded-md border border-danger-line px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                                >
                                  Delete
                                </button>
                              ) : null}
                              <button
                                type="button"
                                onClick={() => moveVisibleExtraction(req.id, 'up')}
                                disabled={!canMoveUp || reorderExtractionMutation.isPending}
                                className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                              >
                                Move up
                              </button>
                              <button
                                type="button"
                                onClick={() => moveVisibleExtraction(req.id, 'down')}
                                disabled={!canMoveDown || reorderExtractionMutation.isPending}
                                className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                              >
                                Move down
                              </button>
                            </div>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>

                  <div className="hidden lg:block">
                    <table className="min-w-full divide-y divide-line text-sm">
                      <thead className="bg-canvas">
                        <tr>
                          {canEditExtractedRequirements ? (
                            <th className="w-12 px-2 py-2 text-left text-xs font-medium uppercase text-muted">
                              Order
                            </th>
                          ) : null}
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase text-muted">
                            Reference
                          </th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase text-muted">
                            Type
                          </th>
                          <th className="px-4 py-2 text-left text-xs font-medium uppercase text-muted">
                            Text
                          </th>
                          {canEditExtractedRequirements ? (
                            <th className="px-4 py-2 text-left text-xs font-medium uppercase text-muted">
                              Actions
                            </th>
                          ) : null}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line bg-surface">
                        {pagedExtractions.map((req) => {
                          const isRejected = req.status === 'rejected'
                          const isDragging = draggingExtractionId === req.id
                          return (
                            <tr
                              key={req.id}
                              className={isRejected ? 'bg-danger-soft/60' : isDragging ? 'bg-info-soft' : ''}
                              onDragOver={
                                canEditExtractedRequirements && !reorderExtractionMutation.isPending
                                  ? (event) => {
                                      event.preventDefault()
                                      event.dataTransfer.dropEffect = 'move'
                                    }
                                  : undefined
                              }
                              onDrop={
                                canEditExtractedRequirements && !reorderExtractionMutation.isPending
                                  ? (event) => {
                                      event.preventDefault()
                                      const movingId =
                                        event.dataTransfer.getData('text/plain') || draggingExtractionId
                                      setDraggingExtractionId(null)
                                      if (!movingId || movingId === req.id) return
                                      const rect = (
                                        event.currentTarget as HTMLTableRowElement
                                      ).getBoundingClientRect()
                                      const placement =
                                        event.clientY < rect.top + rect.height / 2 ? 'before' : 'after'
                                      reorderExtraction(movingId, req.id, placement)
                                    }
                                  : undefined
                              }
                            >
                              {canEditExtractedRequirements ? (
                                <td className="px-2 py-2 align-top">
                                  <button
                                    type="button"
                                    draggable={!reorderExtractionMutation.isPending}
                                    disabled={reorderExtractionMutation.isPending}
                                    onDragStart={(event) => {
                                      event.dataTransfer.effectAllowed = 'move'
                                      event.dataTransfer.setData('text/plain', req.id)
                                      setDraggingExtractionId(req.id)
                                    }}
                                    onDragEnd={() => setDraggingExtractionId(null)}
                                    className="rounded border border-line-strong px-2 py-1 text-xs text-muted hover:bg-canvas disabled:opacity-50"
                                    aria-label={`Drag to reorder ${req.reference_id || req.id}`}
                                  >
                                    &#8942;&#8942;
                                  </button>
                                </td>
                              ) : null}
                              <td className="px-4 py-2 text-ink">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span>{req.reference_id || '-'}</span>
                                  {req.needs_review ? (
                                    <span className="rounded bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning">
                                      Flagged
                                    </span>
                                  ) : null}
                                  {isRejected ? (
                                    <span className="rounded bg-danger-soft px-2 py-0.5 text-[10px] font-semibold text-danger">
                                      Rejected
                                    </span>
                                  ) : null}
                                </div>
                                {req.needs_review ? (
                                  <div className="mt-1 text-xs text-warning">
                                    {req.review_reason || 'needs_review'}
                                  </div>
                                ) : null}
                              </td>
                              <td className="px-4 py-2 text-ink">{req.requirement_type}</td>
                              <td className="px-4 py-2 text-ink">
                                <div className="max-w-2xl whitespace-pre-line break-words">{req.text}</div>
                              </td>
                              {canEditExtractedRequirements ? (
                                <td className="px-4 py-2">
                                  <div className="flex flex-wrap gap-2">
                                    <button
                                      type="button"
                                      onClick={() => openExtractionEditor(req)}
                                      disabled={
                                        updateExtractionMutation.isPending ||
                                        feedbackMutation.isPending
                                      }
                                      aria-label={`Edit extracted requirement ${req.reference_id || req.id}`}
                                      className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                                    >
                                      Edit
                                    </button>
                                  {!isRejected ? (
                                    <button
                                      type="button"
                                      onClick={() => requestExtractionDelete(req)}
                                      disabled={softDeleteExtractionMutation.isPending}
                                      className="rounded-md border border-danger-line px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                                    >
                                      Delete
                                    </button>
                                  ) : null}
                                  </div>
                                </td>
                              ) : null}
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted">
                  {allExtractionItems.length
                    ? 'No non-rejected rows visible. Enable "Show rejected" to see hidden rows.'
                    : 'No extracted rows available.'}
                </p>
              )}
              {visibleExtractionItems.length > 25 && <nav aria-label="Source requirement pages below" className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
                <label className="inline-flex items-center gap-2"><input type="checkbox" checked={showAllExtractions} onChange={event => setShowAllExtractions(event.target.checked)} />Show all sections</label>
                {!showAllExtractions && <div className="flex flex-wrap items-center gap-2"><button className="rounded-md border border-line-strong px-3 py-2 disabled:opacity-50" disabled={currentExtractionPage === 0} onClick={() => { setExtractionPage(currentExtractionPage - 1); requestAnimationFrame(() => document.getElementById('extracted-requirements')?.scrollIntoView({ block: 'start' })) }}>Previous page</button><span>Page {currentExtractionPage + 1} of {extractionPageCount}</span><button className="rounded-md border border-line-strong px-3 py-2 disabled:opacity-50" disabled={currentExtractionPage + 1 >= extractionPageCount} onClick={() => { setExtractionPage(currentExtractionPage + 1); requestAnimationFrame(() => document.getElementById('extracted-requirements')?.scrollIntoView({ block: 'start' })) }}>Next page</button></div>}
              </nav>}
            </>
          ) : (
            <p className="text-sm text-muted">Loading extracted rows...</p>
          )}
        </div>
      ) : null}

      </section>

      <section hidden={hasActiveExtractionRun && sourceView !== 'requirements'} aria-label="Requirement library">
      <div className="mb-4"><HierarchyDepthSelect levels={hierarchyDepth.levels} maxLevels={Math.max(1, ...allRequirements.map(({ depth }) => depth + 1))} onChange={hierarchyDepth.changeLevels} /></div>
      {!isLoading && flattenedRequirements.length > 0 && visibleRequirements.length === 0 && <p role="status" className="mb-4 text-sm text-muted">No requirements at this depth. <button type="button" className="text-accent underline" onClick={() => hierarchyDepth.changeLevels('all')}>Show all levels</button></p>}
      {isLoading ? (
        <div className="text-center py-8">Loading...</div>
      ) : (
        <div className="bg-surface shadow rounded-lg overflow-hidden">
          <div data-testid="requirements-view-mobile-cards" className="space-y-3 p-3 lg:hidden">
            {visibleRequirements.map(({ item, depth }) => {
              const extraction = item.source_extraction_id
                ? extractionById.get(item.source_extraction_id)
                : null
              const isFlagged = !!extraction?.needs_review
              return (
                <div
                  key={item.id}
                  className={`rounded-lg border p-3 ${
                    isFlagged
                      ? 'border-warning-line bg-warning-soft/30'
                      : item.requirement_type === 'informational' ||
                          item.requirement_type === 'not_applicable'
                        ? 'border-line bg-canvas'
                        : 'border-line bg-surface'
                  }`}
                >
                  <div style={{ marginLeft: `${Math.min(depth * 12, 32)}px` }}>
                    <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink break-words">
                      <span>{item.reference_id}</span>
                      {isFlagged ? (
                        <span className="rounded bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning">
                          Flagged
                        </span>
                      ) : null}
                    </div>
                    {item.title && item.title !== stripHtml(item.text || '') && (
                      <div className="mt-1 text-xs text-muted break-words">{item.title}</div>
                    )}
                  </div>
                  {isFlagged ? (
                    <div className="mt-2 rounded border border-warning-line bg-warning-soft px-2 py-1 text-[11px] text-warning">
                      Extraction review flag: {extraction?.review_reason || 'needs_review'}
                    </div>
                  ) : null}
                  <div
                    className="mt-2 text-sm text-ink space-y-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1"
                    dangerouslySetInnerHTML={{ __html: normalizeRichText(item.text) }}
                 />
                  <div className="mt-3 space-y-2 text-xs">
                    <div className="text-muted break-words">
                      Type: <span className="text-ink">{item.requirement_type}</span>
                    </div>
                    <Link
                      to={`/requirements/${item.id}`}
                      className="inline-flex rounded border border-info-line px-2 py-1 text-xs text-info hover:bg-info-soft"
                    >
                      Open
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="hidden lg:block">
            <table className="min-w-full divide-y divide-line">
              <thead className="bg-canvas">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">
                    Reference
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">
                    Requirement
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-surface divide-y divide-line">
                {visibleRequirements.map(({ item, depth }) => {
                  const extraction = item.source_extraction_id
                    ? extractionById.get(item.source_extraction_id)
                    : null
                  const isFlagged = !!extraction?.needs_review
                  return (
                    <tr
                      key={item.id}
                      className={
                        isFlagged
                          ? 'bg-warning-soft/30'
                          : item.requirement_type === 'informational' ||
                              item.requirement_type === 'not_applicable'
                            ? 'bg-canvas'
                            : ''
                      }
                    >
                    <td className="px-6 py-4 text-sm font-medium text-ink">
                      <div style={{ paddingLeft: `${depth * 16}px` }}>
                        <div className="flex flex-wrap items-center gap-2 break-words">
                          <span>{item.reference_id}</span>
                          {isFlagged ? (
                            <span className="rounded bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning">
                              Flagged
                            </span>
                          ) : null}
                        </div>
                        {item.title && item.title !== stripHtml(item.text || '') && (
                          <div className="text-xs text-muted break-words">{item.title}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-ink">
                      <div
                        className="max-w-2xl text-sm text-ink space-y-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1"
                        dangerouslySetInnerHTML={{
                          __html: normalizeRichText(item.text),
                        }}
                    />
                    </td>
                    <td className="px-6 py-4 text-sm text-muted break-words">
                      {item.requirement_type}
                      {isFlagged ? (
                        <div className="mt-1 text-xs text-warning">
                          {extraction?.review_reason || 'needs_review'}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-6 py-4 text-sm text-muted">
                      <Link to={`/requirements/${item.id}`} className="text-xs text-info hover:underline">
                        Open
                      </Link>
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {data && flattenedRequirements.length === 0 && (
            <div className="text-center py-10 text-muted space-y-3">
              <div>No requirements found</div>
              {isAdminOrManager && isArchivedSet && (
                <button
                  type="button"
                  onClick={() => restoreMutation.mutate()}
                  disabled={restoreMutation.isPending}
                  className="inline-flex rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-ink hover:bg-canvas disabled:opacity-50"
                >
                  Restore archived set
                </button>
              )}
            </div>
          )}
        </div>
      )}

      </section>

      <Modal
        open={editingExtraction !== null}
        title="Edit extracted requirement"
        description="Update extracted row values before import or approval."
        onClose={() => {
          if (updateExtractionMutation.isPending || feedbackMutation.isPending) return
          setEditingExtraction(null)
          setExtractionEditError(null)
        }}
        size="lg"
      >
        {editingExtraction ? (
          <div className="space-y-4">
            {editingExtraction.needs_review ? (
              <div className="rounded-md border border-warning-line bg-warning-soft px-3 py-2 text-xs text-warning">
                This row is flagged ({editingExtraction.review_reason || 'needs_review'}). Saving edits
                clears it from the review queue.
              </div>
            ) : null}

            {extractionEditError ? (
              <div className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
                {extractionEditError}
              </div>
            ) : null}

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-ink">Reference</label>
                <input
                  type="text"
                  value={editingExtraction.reference_id}
                  onChange={(event) => {
                    setExtractionEditError(null)
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, reference_id: event.target.value } : prev
                    )
                  }}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm"
               />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-ink">Title</label>
                <input
                  type="text"
                  value={editingExtraction.title}
                  onChange={(event) => {
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, title: event.target.value } : prev
                    )
                  }}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm"
               />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-ink">Requirement Type</label>
                <select
                  value={editingExtraction.requirement_type}
                  onChange={(event) => {
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, requirement_type: event.target.value } : prev
                    )
                  }}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm"
                >
                  <option value="mandatory">Mandatory</option>
                  <option value="informational">Informational</option>
                  <option value="technical">Technical</option>
                  <option value="process">Process</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-ink">Status</label>
                <select
                  value={editingExtraction.status}
                  onChange={(event) => {
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, status: event.target.value } : prev
                    )
                  }}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm"
                >
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-ink">Text</label>
              <textarea
                value={editingExtraction.text}
                onChange={(event) => {
                  setExtractionEditError(null)
                  setEditingExtraction((prev) => (prev ? { ...prev, text: event.target.value } : prev))
                }}
                className="h-40 w-full rounded-md border border-line-strong px-3 py-2 text-sm"
             />
            </div>

            <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-3">
              <button
                type="button"
                onClick={() => {
                  setEditingExtraction(null)
                  setExtractionEditError(null)
                }}
                disabled={updateExtractionMutation.isPending || feedbackMutation.isPending}
                className="rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-ink hover:bg-canvas disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitExtractionEdit}
                disabled={updateExtractionMutation.isPending || feedbackMutation.isPending}
                className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50"
              >
                {updateExtractionMutation.isPending || feedbackMutation.isPending
                  ? 'Saving...'
                  : 'Save changes'}
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <DecisionModal
        open={decisionAction !== null}
        title={decisionAction === 'approve' ? 'Approve requirement set' : 'Reject requirement set'}
        description={
          decisionAction === 'approve'
            ? 'Optionally include an approval comment.'
            : 'A rejection comment is required.'
        }
        confirmLabel={decisionAction === 'approve' ? 'Approve' : 'Reject'}
        confirmVariant={decisionAction === 'approve' ? 'primary' : 'destructive'}
        rationaleMode={decisionAction === 'approve' ? 'optional' : 'required'}
        rationaleLabel={decisionAction === 'approve' ? 'Approval comment' : 'Rejection comment'}
        rationalePlaceholder={
          decisionAction === 'approve'
            ? 'Optional approval comment'
            : 'Required rejection comment'
        }
        rationaleValue={decisionComment}
        onRationaleChange={(value) => {
          setDecisionComment(value)
          setDecisionCommentError(null)
        }}
        rationaleError={decisionCommentError}
        onConfirm={handleDecisionConfirm}
        onClose={() => {
          setDecisionAction(null)
          setDecisionComment('')
          setDecisionCommentError(null)
        }}
        isWorking={approveMutation.isPending || rejectMutation.isPending}
      />

      <DecisionModal
        open={showDeleteSetModal}
        title="Delete requirement set"
        description="This action cannot be undone."
        confirmLabel="Delete set"
        confirmVariant="destructive"
        dangerDetails={[
          'Removes the requirement set and all requirements.',
          'Removes linked review items, evidence, extracted data, and uploaded files.',
        ]}
        onConfirm={() => {
          deleteMutation.mutate()
          setShowDeleteSetModal(false)
        }}
        onClose={() => setShowDeleteSetModal(false)}
        isWorking={deleteMutation.isPending}
      />
      <DecisionModal
        open={pendingExtractionDelete !== null}
        title="Delete extracted requirement"
        description="This will soft delete the extracted row by setting it to rejected."
        confirmLabel="Delete"
        confirmVariant="destructive"
        dangerDetails={[
          'The row is hidden by default after deletion.',
          'Review flags are cleared for this row.',
        ]}
        onConfirm={confirmPendingExtractionDelete}
        onClose={() => setPendingExtractionDelete(null)}
        isWorking={softDeleteExtractionMutation.isPending}
      />
    </div>
  )
}
