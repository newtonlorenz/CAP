import { formatDate, formatDateTime } from '../utils/dateFormat'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import LoadError from '../components/ui/LoadError'
import RequirementQualityPanel from '../components/requirements/RequirementQualityPanel'
import { useCapabilities } from '../hooks/useCapabilities'
import { getApiErrorMessage } from '../api/errors'
import { useEffect, useRef, useState } from 'react'
import { normalizeRichText } from '../utils/richText'
import type {
  Document,
  ExtractionRun,
  ExtractedRequirement,
  ExtractionBatchDistributionItem,
  ExtractionFeedbackBatchRequest,
  ExtractionFeedbackBatchResponse,
  ExtractionSectionPrefixOption,
  ExtractionReorderRequest,
  ExtractionReorderResponse,
  PaginatedResponse,
} from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import DecisionModal from '../components/ui/DecisionModal'
import Modal from '../components/ui/Modal'
import ImportStepper from './requirements-import/ImportStepper'
import BulkTriagePanel from './requirements-import/BulkTriagePanel'
import ReviewQueueKpiPanel from './requirements-import/ReviewQueueKpiPanel'
import RecoveryPanel from './requirements-import/RecoveryPanel'
import type { RecoveryDecision } from './requirements-import/RecoveryPanel'
import {
  buildHierarchyReferenceLookup,
  getHierarchyMismatch,
} from '../utils/referenceHierarchy'

type ExtractionEvent = {
  timestamp?: string
  page_number?: number | null
  stage?: string
  message?: string
  level?: string
  duration_ms?: number | null
}

type ExtractionEditDraft = {
  id: string
  reference_id: string
  title: string
  text: string
  original_text: string
  source_excerpt?: string | null
  page_number?: number | null
  parser_strategy?: string
  requirement_type: string
  status: string
  needs_review: boolean
  review_reason: string | null
}

type ImportStepId = 'metadata' | 'qa' | 'approval'

type BulkUndoSnapshot = {
  rows: Array<{
    id: string
    requirement_type: string
    status: string
    needs_review: boolean
    review_reason: string | null
  }>
}

const sectionPrefixFromReference = (referenceId: string | null | undefined): string => {
  const normalized = (referenceId || '').trim().toLowerCase()
  if (!normalized) return 'unknown'
  const firstToken = normalized.split(/\s+/)[0] || ''
  if (!firstToken) return 'unknown'
  if (firstToken.includes('.')) {
    const [prefix] = firstToken.split('.', 1)
    return prefix || 'unknown'
  }
  return firstToken
}

const toDistribution = (values: string[]): ExtractionBatchDistributionItem[] => {
  const counts = new Map<string, number>()
  values.forEach((value) => {
    const key = value || 'unknown'
    counts.set(key, (counts.get(key) || 0) + 1)
  })
  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, total]) => ({ key, total }))
}

type PendingExtractionDelete = {
  id: string
  reference_id: string
  title: string | null
}

const isRecoveryCandidate = (row: ExtractedRequirement): boolean => row.status !== 'rejected' && (
  row.reference_id.startsWith('unresolved-') ||
  /duplicate_reference|malformed_table_marker|missing_numbered_section|orphan_continuation|ambiguous_unnumbered_table_row|malformed_heading_reference|missing_immediate_parent|missing immediate parent/i.test(row.review_reason || '')
)

export default function RequirementsSetImport() {
  const { data: capabilities } = useCapabilities()
  const [allowExternalAI, setAllowExternalAI] = useState(false)
  const [useJev, setUseJev] = useState(true)
  const { documentId } = useParams<{ documentId: string }>()
  useEffect(() => setAllowExternalAI(false), [documentId, capabilities?.ai?.provider, capabilities?.ai?.model, capabilities?.pdf_structure?.engine, capabilities?.jev?.revision, useJev])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [currentStepId, setCurrentStepId] = useState<ImportStepId | null>(null)
  const [reviewQueueSearch, setReviewQueueSearch] = useState('')
  const [reviewQueuePage, setReviewQueuePage] = useState(0)
  const [extractionSearch, setExtractionSearch] = useState('')
  const [extractionType, setExtractionType] = useState('')
  const prevCurrentRunId = useRef<string | null>(null)
  const [metadataForm, setMetadataForm] = useState({ name: '', testing_frequency: '' })
  const [eventLog, setEventLog] = useState<ExtractionEvent[]>([])
  const [showAllEvents, setShowAllEvents] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [previewBatchResult, setPreviewBatchResult] = useState<ExtractionFeedbackBatchResponse | null>(null)
  const [applyBatchResult, setApplyBatchResult] = useState<ExtractionFeedbackBatchResponse | null>(null)
  const [resolvedInSession, setResolvedInSession] = useState(0)
  const [lastBulkUndoSnapshot, setLastBulkUndoSnapshot] = useState<BulkUndoSnapshot | null>(null)
  const [undoUnavailableReason, setUndoUnavailableReason] = useState<string | null>(null)
  const [decisionDialog, setDecisionDialog] = useState<'approve' | 'reject' | null>(null)
  const [decisionComment, setDecisionComment] = useState('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [editingExtraction, setEditingExtraction] = useState<ExtractionEditDraft | null>(null)
  const [pendingExtractionDelete, setPendingExtractionDelete] = useState<PendingExtractionDelete | null>(null)
  const [showRejected, setShowRejected] = useState(false)
  const [draggingExtractionId, setDraggingExtractionId] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const { data: document, isLoading, isError: documentError, refetch: retryDocument } = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const response = await api.get<Document>(`/documents/${documentId}`)
      return response.data
    },
    refetchInterval: (query) => {
      const doc = query.state.data
      // Poll every 2s while extracting
      if (doc && ['extracting', 'pending_extraction'].includes(doc.status)) {
        return 2000
      }
      return false
    },
  })

  const { data: extractionHistory } = useQuery({
    queryKey: ['document-extraction-runs', documentId],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<ExtractionRun>>(
        `/documents/${documentId}/extraction-runs`
      )
      return response.data
    },
  })

  // A fast worker can finish between polls. Refresh the dependent views once
  // the document reaches a terminal state, before polling stops.
  useEffect(() => {
    if (!document?.current_extraction_id || !['extracted', 'extraction_failed', 'extraction_cancelled'].includes(document.status)) return
    queryClient.invalidateQueries({ queryKey: ['document-extraction-runs', documentId] })
    queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
  }, [document?.current_extraction_id, document?.status, documentId, queryClient])

  useEffect(() => {
    const currentId = document?.current_extraction?.id ?? null
    const prevId = prevCurrentRunId.current
    const shouldFollowCurrent = !selectedRunId || selectedRunId === prevId

    if (currentId && shouldFollowCurrent && selectedRunId !== currentId) {
      setSelectedRunId(currentId)
      prevCurrentRunId.current = currentId
      return
    }

    if (!selectedRunId && extractionHistory?.items?.length) {
      setSelectedRunId(extractionHistory.items[0].id)
      prevCurrentRunId.current = currentId
      return
    }

    prevCurrentRunId.current = currentId
  }, [document?.current_extraction?.id, extractionHistory?.items, selectedRunId])

  const metadataName = document?.name ?? ''
  const metadataTestingFrequency = document?.testing_frequency ?? ''

  useEffect(() => {
    setMetadataForm({
      name: metadataName,
      testing_frequency: metadataTestingFrequency,
    })
  }, [metadataName, metadataTestingFrequency])

  useEffect(() => {
    if (!document?.jurisdiction_id) return
    if (jurisdictionId && document.jurisdiction_id !== jurisdictionId) {
      setJurisdictionId(document.jurisdiction_id)
    }
  }, [document?.jurisdiction_id, jurisdictionId, setJurisdictionId])

  useEffect(() => {
    setEventLog([])
    setShowAllEvents(false)
  }, [document?.current_extraction?.id])

  useEffect(() => {
    setActionError(null)
    setPreviewBatchResult(null)
    setApplyBatchResult(null)
    setResolvedInSession(0)
    setLastBulkUndoSnapshot(null)
    setUndoUnavailableReason(null)
    setCurrentStepId(null)
    setShowRejected(false)
    setPendingExtractionDelete(null)
    setDraggingExtractionId(null)
  }, [documentId])

  useEffect(() => {
    if (!document?.current_extraction?.id) {
      eventSourceRef.current?.close()
      eventSourceRef.current = null
      return
    }

    if (!['extracting', 'pending_extraction'].includes(document.status)) {
      eventSourceRef.current?.close()
      eventSourceRef.current = null
      return
    }

    const url = `${api.defaults.baseURL}/documents/${documentId}/extraction-runs/${document.current_extraction.id}/events/stream`
    const source = new EventSource(url)
    eventSourceRef.current = source

    source.onmessage = (event) => {
      if (!event.data) return
      try {
        const payload = JSON.parse(event.data) as ExtractionEvent
        setEventLog((prev) => {
          const next = [...prev, payload]
          return next.slice(-200)
        })
      } catch {
        return
      }
    }

    source.onerror = () => {
      return
    }

    return () => {
      source.close()
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null
      }
    }
  }, [document?.status, document?.current_extraction?.id, documentId])

  const { data: extractionResults } = useQuery({
    queryKey: ['document-extractions', documentId, selectedRunId],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (selectedRunId) params.append('run_id', selectedRunId)
      params.append('limit', '10000')
      const response = await api.get<PaginatedResponse<ExtractedRequirement>>(
        `/documents/${documentId}/extractions?${params.toString()}`
      )
      return response.data
    },
    enabled: !!selectedRunId,
    refetchInterval: () => {
      const doc = queryClient.getQueryData<Document>(['document', documentId])
      if (!doc?.current_extraction?.id) return false
      const isExtracting = ['extracting', 'pending_extraction'].includes(doc.status)
      if (isExtracting && selectedRunId === doc.current_extraction.id) {
        return 2000
      }
      return false
    },
  })

  const extractMutation = useMutation({
    mutationFn: async () => {
      if (!document?.filename) throw new Error('No PDF attached')
      if (isLocalStructuredExtraction && !pdfStructure?.available) throw new Error('The structured PDF extraction engine is unavailable')
      const response = await api.post(
        `/documents/${documentId}/extract`,
        null,
        capabilities?.jev?.enabled && useJev
          ? { params: { allow_external_ai: allowExternalAI, use_jev: true, jev_settings_revision: capabilities.jev.revision } }
          : isLocalStructuredExtraction ? undefined : { params: { allow_external_ai: allowExternalAI } }
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['document-extraction-runs', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirement-quality-runs', documentId] })
    },
    onMutate: () => setActionError(null),
    onError: (error: unknown) => {
      const message = getApiErrorMessage(error, 'Unable to start extraction. Please try again.')
      setActionError(message.includes('No AI provider configured') ? 'PDF extraction is not configured. Ask your administrator to enable a document extraction provider, then try again. Your uploaded PDF is saved.' : message)
    },
  })

  const submitMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post(`/documents/${documentId}/submit`)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
    onMutate: () => setActionError(null),
    onError: (error: unknown) => {
      const message = getApiErrorMessage(error, 'Unable to submit for approval. Please try again.')
      setActionError(message.includes('No AI provider configured') ? 'PDF extraction is not configured. Ask your administrator to enable a document extraction provider, then try again. Your uploaded PDF is saved.' : message)
    },
  })

  const approveMutation = useMutation({
    mutationFn: async (comment?: string) => {
      const response = await api.post(`/documents/${documentId}/approve`, null, {
        params: comment ? { comment } : undefined,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const updateMetadataMutation = useMutation({
    mutationFn: async (data: { name: string | null; testing_frequency: string | null }) => {
      const response = await api.put(`/documents/${documentId}`, data)
      return response.data
    },
    onSuccess: () => {
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Update failed'))
    },
  })

  const rejectMutation = useMutation({
    mutationFn: async (comment: string) => {
      const response = await api.post(`/documents/${documentId}/reject`, null, {
        params: { comment },
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: async (runId: string) => {
      const response = await api.post(
        `/documents/${documentId}/extraction-runs/${runId}/cancel`
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({
        queryKey: ['document-extraction-runs', documentId],
      })
    },
    onMutate: () => setActionError(null),
    onError: (error: unknown) => {
      const message = getApiErrorMessage(error, 'Unable to cancel extraction. Please try again.')
      setActionError(message.includes('No AI provider configured') ? 'PDF extraction is not configured. Ask your administrator to enable a document extraction provider, then try again. Your uploaded PDF is saved.' : message)
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
        sync_parent_from_reference?: boolean
      }
    }) => {
      const response = await api.put(
        `/documents/${documentId}/extractions/${payload.extractionId}`,
        payload.data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      setActionError(null)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to update extracted requirement'))
    },
  })

  const recoveryMutation = useMutation({
    mutationFn: async (payload: { extractionId: string; decision: RecoveryDecision }) => {
      const response = await api.post(
        `/requirements/sets/${documentId}/import-recovery/${payload.extractionId}`,
        payload.decision
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      setActionError(null)
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error, 'Could not resolve the source candidate.')),
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
      const pendingCountBefore = extractionResults?.items.filter((item) => item.needs_review).length || 0
      if (pendingCountBefore > 0) {
        setResolvedInSession((prev) => prev + 1)
      }
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      setActionError(null)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to submit review feedback'))
    },
  })

  const previewFeedbackBatchMutation = useMutation({
    mutationFn: async (payload: ExtractionFeedbackBatchRequest) => {
      const response = await api.post<ExtractionFeedbackBatchResponse>(
        `/documents/${documentId}/extractions/feedback-batch`,
        payload
      )
      return response.data
    },
    onSuccess: (result) => {
      setPreviewBatchResult(result)
      setActionError(null)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to preview bulk triage action'))
    },
  })

  const applyFeedbackBatchMutation = useMutation({
    mutationFn: async (payload: {
      request: ExtractionFeedbackBatchRequest
      preRows: Record<
        string,
        {
          requirement_type: string
          status: string
          needs_review: boolean
          review_reason: string | null
        }
      >
    }) => {
      const response = await api.post<ExtractionFeedbackBatchResponse>(
        `/documents/${documentId}/extractions/feedback-batch`,
        payload.request
      )
      return {
        result: response.data,
        preRows: payload.preRows,
      }
    },
    onSuccess: ({ result, preRows }) => {
      const undoRows = result.affected_ids
        .map((id) => {
          const previous = preRows[id]
          if (!previous) return null
          return {
            id,
            requirement_type: previous.requirement_type,
            status: previous.status,
            needs_review: previous.needs_review,
            review_reason: previous.review_reason,
          }
        })
        .filter((row): row is BulkUndoSnapshot['rows'][number] => row !== null)

      if (result.affected_ids_truncated) {
        setLastBulkUndoSnapshot(null)
        setUndoUnavailableReason('Undo unavailable because more than 500 rows were affected.')
      } else if (undoRows.length > 0) {
        setLastBulkUndoSnapshot({ rows: undoRows })
        setUndoUnavailableReason(null)
      } else {
        setLastBulkUndoSnapshot(null)
      }

      const resolvedNow = undoRows.filter((row) => row.needs_review).length
      setResolvedInSession((prev) => prev + resolvedNow)
      setApplyBatchResult(result)
      setPreviewBatchResult(null)
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to apply bulk triage action'))
    },
  })

  const undoBulkMutation = useMutation({
    mutationFn: async (snapshot: BulkUndoSnapshot) => {
      const chunkSize = 25
      for (let index = 0; index < snapshot.rows.length; index += chunkSize) {
        const chunk = snapshot.rows.slice(index, index + chunkSize)
        await Promise.all(
          chunk.map((row) =>
            api.put(`/documents/${documentId}/extractions/${row.id}`, {
              requirement_type: row.requirement_type,
              status: row.status,
              needs_review: row.needs_review,
              review_reason: row.review_reason,
            })
          )
        )
      }
      return snapshot.rows
    },
    onSuccess: (rows) => {
      const restoredReviewItems = rows.filter((row) => row.needs_review).length
      setResolvedInSession((prev) => Math.max(0, prev - restoredReviewItems))
      setLastBulkUndoSnapshot(null)
      setUndoUnavailableReason(null)
      setApplyBatchResult(null)
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to undo bulk triage action'))
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
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      setPendingExtractionDelete(null)
      setActionError(null)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to delete extracted requirement'))
    },
  })

  const reorderExtractionMutation = useMutation({
    mutationFn: async (orderedIds: string[]) => {
      if (!selectedRunId) {
        throw new Error('Select an extraction run before reordering')
      }
      const payload: ExtractionReorderRequest = {
        run_id: selectedRunId,
        ordered_ids: orderedIds,
      }
      const response = await api.post<ExtractionReorderResponse>(
        `/documents/${documentId}/extractions/reorder`,
        payload
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId, selectedRunId] })
      setDraggingExtractionId(null)
      setActionError(null)
    },
    onError: (error: unknown) => {
      setDraggingExtractionId(null)
      setActionError(getApiErrorMessage(error, 'Failed to reorder extracted requirements'))
    },
  })

  const statusColors: Record<string, string> = {
    draft: 'bg-subtle text-ink',
    uploaded: 'bg-subtle text-ink',
    pending_extraction: 'bg-warning-soft text-warning',
    extracting: 'bg-warning-soft text-warning',
    extracted: 'bg-info-soft text-info',
    extraction_failed: 'bg-danger-soft text-danger',
    extraction_cancelled: 'bg-subtle text-ink',
    pending_approval: 'bg-violet-soft text-violet',
    approved: 'bg-success-soft text-success',
    changes_requested: 'bg-danger-soft text-danger',
    archived: 'bg-line text-ink',
  }

  const extractionStatusColors: Record<string, string> = {
    pending: 'bg-subtle text-ink',
    running: 'bg-warning-soft text-warning',
    completed: 'bg-success-soft text-success',
    failed: 'bg-danger-soft text-danger',
    cancelled: 'bg-subtle text-ink',
    timed_out: 'bg-danger-soft text-danger',
  }

  if (documentError) return <LoadError subject="This PDF import" onRetry={() => retryDocument()} />

  if (isLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!document) {
    return <div className="text-center py-8">Requirement set not found</div>
  }

  const isAdminOrManager = user?.role === 'admin' || user?.role === 'manager'
  const isArchived = document.status === 'archived' || !!document.archived_at
  const isExtracting = ['extracting', 'pending_extraction'].includes(document.status)
  const unresolvedReviewCount =
    extractionResults?.items.filter((item) => item.needs_review && item.status !== 'rejected').length || 0
  const canExtract =
    isAdminOrManager &&
    !isArchived &&
    ['uploaded', 'extraction_failed', 'extraction_cancelled', 'extracted'].includes(document.status)
  const canSubmitByStatus =
    isAdminOrManager &&
    !isArchived &&
    ['draft', 'extracted', 'reviewed', 'changes_requested'].includes(document.status)
  const canApprove =
    !isArchived &&
    document.status === 'pending_approval' &&
    (user?.role === 'admin' || user?.role === 'manager' || user?.role === 'approver')
  const canOpenRequirementSet = ['draft', 'changes_requested', 'pending_approval', 'approved'].includes(
    document.status
  )
  const canEditRequirementSet =
    isAdminOrManager &&
    ['draft', 'changes_requested', 'extracted', 'reviewed', 'pending_approval', 'approved'].includes(
      document.status
    )
  const canEditExtractedRequirements =
    isAdminOrManager &&
    !isArchived &&
    ['draft', 'extracted', 'reviewed', 'changes_requested', 'pending_approval'].includes(
      document.status
    )
  const extraction = document.current_extraction
  const metadataComplete =
    !!document.name?.trim() && !!document.testing_frequency?.trim()
  const visibleEvents = showAllEvents ? eventLog : eventLog.slice(-25)
  const latestProgressEvent = [...eventLog].reverse().find(event => event.timestamp)
  const lastProgressAt = extraction?.last_progress_at || latestProgressEvent?.timestamp
  const stoppedExtraction = extraction && ['failed', 'timed_out', 'cancelled'].includes(extraction.status)

  const progressPercent =
    extraction && extraction.total_pages
      ? Math.round((extraction.current_page / extraction.total_pages) * 100)
      : 0

  const formatDuration = (start: string | null, end: string | null): string => {
    if (!start) return '-'
    const startDate = new Date(start)
    const endDate = end ? new Date(end) : new Date()
    const seconds = Math.round((endDate.getTime() - startDate.getTime()) / 1000)
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}m ${remainingSeconds}s`
  }

  const selectedRun =
    (extraction?.id === selectedRunId ? extraction : null) ||
    extractionHistory?.items.find((run) => run.id === selectedRunId)
  const allExtractionItems = extractionResults?.items || []
  const recoveryRows = selectedRunId === document.current_extraction_id && selectedRun?.pipeline_version === 'opendataloader_v1'
    ? allExtractionItems.filter(isRecoveryCandidate)
    : []
  const extractionReferenceLookup = buildHierarchyReferenceLookup(allExtractionItems)
  const extractionHierarchyMismatchById = new Map(
    allExtractionItems.map((item) => [item.id, getHierarchyMismatch(item, extractionReferenceLookup)])
  )
  const hasExtractionFilters = !!extractionSearch.trim() || !!extractionType
  const visibleExtractionItems = allExtractionItems.filter((item) =>
    (showRejected || item.status !== 'rejected') &&
    (!extractionType || item.requirement_type === extractionType) &&
    `${item.reference_id} ${item.title || ''} ${item.text}`.toLowerCase().includes(extractionSearch.trim().toLowerCase())
  )
  const totalRejectedCount = allExtractionItems.filter((item) => item.status === 'rejected').length
  const hiddenRejectedCount = showRejected ? 0 : totalRejectedCount
  const reviewQueueItems =
    extractionResults?.items.filter((item) => item.needs_review && item.status !== 'rejected' && !isRecoveryCandidate(item)) || []
  const hasExtractionRun = !!document.current_extraction_id || !!selectedRunId
  const qaStepUnlocked = metadataComplete
  const qaStepComplete = hasExtractionRun && (selectedRun?.status === 'completed' || ['reviewed', 'pending_approval', 'approved'].includes(document.status)) && allExtractionItems.some(item => item.status !== 'rejected') && unresolvedReviewCount === 0 && recoveryRows.length === 0
  const approvalStepUnlocked = metadataComplete && qaStepComplete
  const approvalStepComplete = document.status === 'approved'
  const queueMatches = reviewQueueItems.filter(row => `${row.reference_id} ${row.title || ''} ${row.text}`.toLowerCase().includes(reviewQueueSearch.toLowerCase()))
  const queuePages = Math.max(1, Math.ceil(queueMatches.length / 10))
  const queuePage = Math.min(reviewQueuePage, queuePages - 1)
  const visibleQueueItems = queueMatches.slice(queuePage * 10, (queuePage + 1) * 10)


  const requestedStep = currentStepId || (['pending_approval', 'approved'].includes(document.status) ? 'approval' : metadataComplete ? 'qa' : 'metadata')
  const effectiveCurrentStepId: ImportStepId =
    requestedStep === 'approval' && !approvalStepUnlocked
      ? qaStepUnlocked
        ? 'qa'
        : 'metadata'
      : requestedStep === 'qa' && !qaStepUnlocked
        ? 'metadata'
        : requestedStep

  const stepDefinitions = [
    {
      id: 'metadata' as const,
      title: 'Metadata',
      description: 'Set requirement set name and testing frequency.',
      complete: metadataComplete,
      locked: false,
    },
    {
      id: 'qa' as const,
      title: 'Extraction QA',
      description: 'Resolve flagged extraction items and quality checks.',
      complete: qaStepComplete,
      locked: !qaStepUnlocked,
    },
    {
      id: 'approval' as const,
      title: 'Approval',
      description: 'Submit, approve, and move into the lifecycle.',
      complete: approvalStepComplete,
      locked: !approvalStepUnlocked,
    },
  ]

  const requirementTypeOptions = (() => {
    const values = new Set<string>()
    extractionResults?.items.forEach((item) => {
      if (item.requirement_type) values.add(item.requirement_type)
    })
    return Array.from(values).sort((a, b) => a.localeCompare(b))
  })()

  const sectionOptions: ExtractionSectionPrefixOption[] = (() => {
    const values = new Set<string>()
    extractionResults?.items.forEach((item) => {
      values.add(sectionPrefixFromReference(item.reference_id))
    })
    return Array.from(values)
      .sort((a, b) => a.localeCompare(b))
      .map((value) => ({
        value,
        label: value,
      }))
  })()

  const reviewReasonOptions = (() => {
    const values = new Set<string>()
    reviewQueueItems.forEach((item) => {
      values.add((item.review_reason || 'none').toLowerCase())
    })
    return Array.from(values).sort((a, b) => a.localeCompare(b))
  })()

  const reviewReasonDistribution = toDistribution(
    reviewQueueItems.map((item) => (item.review_reason || 'none').toLowerCase())
  )

  const sectionDistribution = toDistribution(
    reviewQueueItems.map((item) => sectionPrefixFromReference(item.reference_id))
  )

  const bulkReadyCount = reviewQueueItems.filter((item) => item.confidence_score < 0.75).length
  const manualQueueCount = Math.max(0, unresolvedReviewCount - bulkReadyCount)

  const reorderExtraction = (movingId: string, targetId: string, placement: 'before' | 'after') => {
    if (reorderExtractionMutation.isPending || !selectedRunId) return
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

    const targetId = direction === 'up' ? visibleIds[currentIndex - 1] : visibleIds[currentIndex + 1]
    if (!targetId) return
    reorderExtraction(extractionId, targetId, direction === 'up' ? 'before' : 'after')
  }

  const openDecisionDialog = (mode: 'approve' | 'reject') => {
    setActionError(null)
    setDecisionComment('')
    setDecisionDialog(mode)
  }

  const openExtractionEditor = (req: ExtractedRequirement) => {
    setActionError(null)
    setEditingExtraction({
      id: req.id,
      reference_id: req.reference_id || '',
      title: req.title || '',
      text: req.text || '',
      original_text: req.original_text ?? req.text ?? '',
      source_excerpt: req.source_excerpt,
      page_number: req.page_number,
      parser_strategy: req.parser_strategy,
      requirement_type: req.requirement_type || 'mandatory',
      status: req.status || 'pending',
      needs_review: !!req.needs_review,
      review_reason: req.review_reason || null,
    })
  }

  const handlePreviewBulkAction = (payload: ExtractionFeedbackBatchRequest) => {
    setApplyBatchResult(null)
    previewFeedbackBatchMutation.mutate(payload)
  }

  const handleApplyBulkAction = (payload: ExtractionFeedbackBatchRequest) => {
    const preRows: Record<
      string,
      {
        requirement_type: string
        status: string
        needs_review: boolean
        review_reason: string | null
      }
    > = {}
    extractionResults?.items.forEach((item) => {
      preRows[item.id] = {
        requirement_type: item.requirement_type,
        status: item.status,
        needs_review: !!item.needs_review,
        review_reason: item.review_reason || null,
      }
    })
    applyFeedbackBatchMutation.mutate({
      request: payload,
      preRows,
    })
  }

  const handleUndoBulkAction = () => {
    if (!lastBulkUndoSnapshot || lastBulkUndoSnapshot.rows.length === 0) return
    undoBulkMutation.mutate(lastBulkUndoSnapshot)
  }

  const requestExtractionDelete = (req: Pick<ExtractedRequirement, 'id' | 'reference_id' | 'title'>) => {
    setActionError(null)
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
    const draft = editingExtraction
    const referenceId = editingExtraction.reference_id.trim()
    const text = editingExtraction.text.trim()
    if (!referenceId) {
      setActionError('Reference is required when editing extracted requirements.')
      return
    }
    if (!text) {
      setActionError('Text is required when editing extracted requirements.')
      return
    }
    updateExtractionMutation.mutate({
      extractionId: draft.id,
      data: {
        reference_id: referenceId,
        title: draft.title.trim() || null,
        text,
        requirement_type: draft.requirement_type,
        status: draft.status,
      },
    }, {
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
    })
  }

  const fixExtractionHierarchy = (extractionId: string) => {
    updateExtractionMutation.mutate({
      extractionId,
      data: {
        sync_parent_from_reference: true,
      },
    })
  }

  const submitDecision = () => {
    if (decisionDialog === 'approve') {
      approveMutation.mutate(decisionComment.trim() || undefined, {
        onError: (error: unknown) => {
          setActionError(getApiErrorMessage(error, 'Approve failed'))
        },
      })
      setDecisionDialog(null)
      return
    }
    if (!decisionComment.trim()) {
      setActionError('Rejection comment is required.')
      return
    }
    rejectMutation.mutate(decisionComment.trim(), {
      onError: (error: unknown) => {
        setActionError(getApiErrorMessage(error, 'Reject failed'))
      },
    })
    setDecisionDialog(null)
  }

  const handleDeleteRequirementSet = async () => {
    try {
      await api.delete(`/requirements/sets/${document.id}`)
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      setDeleteDialogOpen(false)
      navigate('/requirements')
    } catch (error: unknown) {
      setActionError(getApiErrorMessage(error, 'Delete failed'))
      setDeleteDialogOpen(false)
    }
  }

  const hasPdf = document.has_source ?? Boolean(document.filename)
  const pdfStructure = capabilities?.pdf_structure
  const isLocalStructuredExtraction = Boolean(
    pdfStructure?.engine === 'opendataloader' &&
    pdfStructure.local_only
  )
  const structuredEngineUnavailable = isLocalStructuredExtraction && !pdfStructure?.available

  return (
    <div className="min-w-0">
      <div className="mb-6">
        <button
          onClick={() => navigate('/requirements')}
          className="text-info hover:text-info text-sm"
        >
          &larr; Back to Requirements
        </button>
      </div>

      {actionError ? (
        <div role="alert" className="mb-4 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
          {actionError}
        </div>
      ) : null}



      <div className="mb-4 rounded-lg border border-line bg-surface p-4 sm:p-5">
        <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-ink">
              {document.name || document.filename || 'Untitled requirement set'}
            </h1>
            <p className="mt-1 break-words text-muted">
              {document.document_type.replace(/_/g, ' ')} &middot; Created{' '}
              {formatDate(document.created_at)}
            </p>
            {document.name && document.filename && (
              <p className="mt-1 break-all text-xs text-muted">Filename: {document.filename}</p>
            )}
          </div>
          <span
            className={`shrink-0 rounded px-3 py-1 text-sm font-medium ${
              statusColors[document.status] || 'bg-subtle text-ink'
            }`}
          >
            {document.status.replace(/_/g, ' ')}
          </span>
        </div>

        <details className="mt-2 text-sm"><summary className="cursor-pointer text-muted">Source details · {document.version ? `v${document.version}` : 'Version not set'}</summary>
	        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
	          <div>
	            <span className="text-muted">Jurisdiction:</span>{' '}
	            <span className="text-ink">
	              {jurisdictionById[document.jurisdiction_id]?.name || document.jurisdiction_id}
	            </span>
	          </div>
	          <div>
	            <span className="text-muted">Testing Frequency:</span>{' '}
	            <span className="text-ink">
	              {document.testing_frequency
                ? document.testing_frequency.replace('_', ' ')
                : '-'}
            </span>
          </div>
          <div>
            <span className="text-muted">Version:</span>{' '}
            <span className="text-ink">{document.version || '-'}</span>
          </div>
          <div>
            <span className="text-muted">Effective Date:</span>{' '}
            <span className="text-ink">
              {document.effective_date
                ? formatDate(document.effective_date)
                : '-'}
            </span>
          </div>
        </div>

        </details>

        {isArchived && (
          <div className="mt-4 rounded-md border border-warning-line bg-warning-soft p-3 text-sm text-warning">
            This requirement set is archived. Requirements remain available, but set actions are
            disabled.
          </div>
        )}

        {!metadataComplete && !isArchived && (
          <div className="mt-4 rounded-md border border-warning-line bg-warning-soft p-3 text-sm text-warning">
            Requirement set name and testing frequency are required before approval.
          </div>
        )}

      {isLocalStructuredExtraction ? (
        <p className={`mb-4 rounded-lg border p-3 text-sm ${structuredEngineUnavailable ? 'border-warning-line bg-warning-soft text-warning' : 'border-line bg-canvas text-muted'}`} role={structuredEngineUnavailable ? 'status' : undefined}>
          {structuredEngineUnavailable
            ? `${pdfStructure?.engine === 'opendataloader' ? 'OpenDataLoader' : 'Structured PDF extraction engine'} is unavailable. Install the optional PDF package and Java before extracting this PDF.`
            : `Local structured extraction · ${pdfStructure?.engine === 'opendataloader' ? 'OpenDataLoader' : pdfStructure?.engine}. PDF reading is local${capabilities?.jev?.enabled && useJev ? '; the selected Jev check sends source text externally.' : '; external AI consent is not needed.'}`}
        </p>
      ) : null}
      {capabilities?.jev?.enabled && <label className="mb-3 flex items-start gap-2 text-sm">
        <input type="checkbox" checked={useJev} onChange={event => setUseJev(event.target.checked)} />
        <span>Enhance the extracted draft with Jev source checks and confident repairs. Changes remain for human review.</span>
      </label>}
      {((!isLocalStructuredExtraction && capabilities?.ai?.external_processing) || (capabilities?.jev?.enabled && useJev)) && (
        <label className="mb-4 flex items-start gap-2 rounded-lg border border-line p-3 text-sm">
          <input type="checkbox" checked={allowExternalAI} onChange={event => setAllowExternalAI(event.target.checked)} />
          <span>{!isLocalStructuredExtraction && capabilities?.ai?.external_processing
            ? `Allow document text and page images to be sent to ${capabilities.ai.provider}${capabilities?.jev?.enabled && useJev ? ', and source text to Jev,' : ''} for this extraction.`
            : 'Allow source text to be sent to Jev for this extraction check.'}</span>
        </label>
      )}
      {capabilities?.ai?.enabled === false && <p className="mb-4 text-sm text-muted">The extraction provider is disabled. PDF extraction is local; draft requirements still need source review{capabilities?.jev?.enabled && useJev ? ' after the optional Jev check.' : '.'}</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          {hasPdf ? (
            <a className="rounded-md border border-line-strong px-4 py-2 text-sm text-ink" href={`${api.defaults.baseURL}/documents/${documentId}/source`} target="_blank" rel="noopener noreferrer">View source PDF</a>
          ) : (
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-canvas px-3 py-2 text-sm">
              <span className="text-muted">No PDF attached</span>
              <Link to={`/requirements/sets/${document.id}/edit`} className="text-accent underline">Open draft editor</Link>
            </div>
          )}
          {canExtract && effectiveCurrentStepId === 'qa' && (
            <button
              onClick={() => extractMutation.mutate()}
              disabled={extractMutation.isPending || !hasPdf || structuredEngineUnavailable || !!(capabilities?.jev?.enabled && useJev && !allowExternalAI)}
              className={`w-full rounded-md px-4 py-2 text-sm disabled:opacity-50 sm:w-auto ${document.status === 'extracted' ? 'border border-line-strong text-ink hover:bg-subtle' : 'bg-brand text-white hover:bg-brand-hover'}`}
            >
              {structuredEngineUnavailable
                ? `${pdfStructure?.engine === 'opendataloader' ? 'OpenDataLoader' : 'Structured engine'} unavailable`
                : !hasPdf
                ? 'No PDF attached'
                : extractMutation.isPending
                ? 'Starting...'
                : document.status === 'extracted'
                  ? 'Re-extract'
                  : 'Extract Requirements'}
            </button>
          )}
          {canSubmitByStatus && effectiveCurrentStepId === 'approval' && (
            <button
              onClick={() => submitMutation.mutate()}
              disabled={
                submitMutation.isPending ||
                unresolvedReviewCount > 0 ||
                !approvalStepUnlocked ||
                effectiveCurrentStepId !== 'approval'
              }
              className="w-full rounded-md bg-purple-600 px-4 py-2 text-white hover:bg-purple-700 disabled:opacity-50 sm:w-auto"
            >
              {submitMutation.isPending
                ? 'Submitting...'
                : !approvalStepUnlocked
                  ? 'Complete QA to Unlock Approval'
                  : effectiveCurrentStepId !== 'approval'
                    ? 'Open Approval Step to Submit'
                    : unresolvedReviewCount > 0
                      ? `Resolve ${unresolvedReviewCount} Review Items`
                      : 'Submit for Approval'}
            </button>
          )}
          {canApprove && effectiveCurrentStepId === 'approval' && (
            <>
              <button
                onClick={() => openDecisionDialog('approve')}
                disabled={approveMutation.isPending || !metadataComplete || effectiveCurrentStepId !== 'approval'}
                className="w-full rounded-md bg-green-600 px-4 py-2 text-white hover:bg-green-700 disabled:opacity-50 sm:w-auto"
              >
                {approveMutation.isPending ? 'Approving...' : 'Approve'}
              </button>
              <button
                onClick={() => openDecisionDialog('reject')}
                disabled={rejectMutation.isPending || effectiveCurrentStepId !== 'approval'}
                className="w-full rounded-md bg-red-600 px-4 py-2 text-white hover:bg-red-700 disabled:opacity-50 sm:w-auto"
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
              </button>
            </>
          )}
          {isAdminOrManager && isExtracting && extraction?.id && (
            <button
              onClick={() => cancelMutation.mutate(extraction.id)}
              disabled={cancelMutation.isPending}
              className="w-full rounded-md bg-subtle px-4 py-2 text-ink hover:bg-line disabled:opacity-50 sm:w-auto"
            >
              {cancelMutation.isPending ? 'Cancelling...' : 'Cancel Extraction'}
            </button>
          )}
          {isAdminOrManager && effectiveCurrentStepId === 'metadata' && (
            <button
              onClick={() => setDeleteDialogOpen(true)}
              className="w-full rounded-md border border-danger-line px-4 py-2 text-danger hover:bg-danger-soft sm:w-auto"
            >
              Delete Requirements Set
            </button>
          )}
          {canOpenRequirementSet && (
            <Link
              to={`/requirements/sets/${document.id}`}
              className="w-full rounded-md border border-line-strong px-4 py-2 text-center text-ink hover:bg-canvas sm:w-auto"
            >
              Open Requirement Set
            </Link>
          )}
          {canEditRequirementSet && recoveryRows.length === 0 && (
            <Link
              to={`/requirements/sets/${document.id}/edit`}
              className="w-full rounded-md bg-strong px-4 py-2 text-center text-white hover:bg-strong sm:w-auto"
            >
              Edit Requirement Set
            </Link>
          )}
          {canEditRequirementSet && recoveryRows.length > 0 && <span className="text-sm text-warning">Resolve source structure before editing the set.</span>}
        </div>
        {effectiveCurrentStepId === 'qa' ? (
          <p className="mt-3 text-xs text-muted">
            {document.status === 'approved' ? 'This source is approved. You can inspect its extraction and published requirement set.' : 'Check the source text and resolve flagged items, then continue to approval.'}
          </p>
        ) : null}
      </div>

      {isExtracting && extraction && <section aria-label="Import status" className="mb-4 rounded-lg border border-info-line bg-info-soft p-4 text-sm text-ink">
        <p className="font-semibold">{extraction.status === 'pending' ? 'Import queued' : 'Import in progress'}{extraction.total_pages ? ` · Page ${extraction.current_page} of ${extraction.total_pages}` : ''}</p>
        <p className="mt-1 text-muted">{lastProgressAt ? `Last reported activity: ${new Date(lastProgressAt).toLocaleString()}` : extraction.started_at ? `Started: ${new Date(extraction.started_at).toLocaleString()}. Waiting for the next progress update.` : `Queued: ${new Date(extraction.created_at).toLocaleString()}. Waiting for a worker to start.`}</p>
        <p className="mt-1 text-muted">You can leave this page and return to check progress.{isAdminOrManager ? ' If progress stops, cancel this run before starting again.' : ' If progress stops, ask a manager to check the import.'}</p>
        {effectiveCurrentStepId !== 'qa' && qaStepUnlocked && <button type="button" className="mt-2 font-semibold text-accent underline" onClick={() => setCurrentStepId('qa')}>View import activity</button>}
      </section>}
      {stoppedExtraction && <section role="status" className="mb-4 rounded-lg border border-warning-line bg-warning-soft p-4 text-sm text-ink">
        <p className="font-semibold">{extraction.status === 'timed_out' ? 'Import timed out' : extraction.status === 'cancelled' ? 'Import cancelled' : 'Import failed'}</p>
        <p className="mt-1">{extraction.error_message || 'This run stopped before completing.'}</p>
        <p className="mt-1 text-muted">{isAdminOrManager ? 'Check the source and extraction settings, then start a new run from Extraction QA.' : 'Ask a manager to review the source and restart the import.'}</p>
        {effectiveCurrentStepId !== 'qa' && qaStepUnlocked && <button type="button" className="mt-2 font-semibold text-accent underline" onClick={() => setCurrentStepId('qa')}>Open extraction QA</button>}
      </section>}

      {capabilities?.jev && <RequirementQualityPanel
        documentId={document.id} hasSource={hasPdf} archived={isArchived}
        enabled={capabilities.jev.enabled} revision={capabilities.jev.revision}
        canManage={isAdminOrManager} documentStatus={document.status}
        currentExtractionId={document.current_extraction?.status === 'completed' ? document.current_extraction.id : null}
      />}

      <ImportStepper
        steps={stepDefinitions}
        currentStepId={effectiveCurrentStepId}
        onStepChange={(stepId) => {
          const target = stepDefinitions.find((step) => step.id === stepId)
          if (!target || target.locked) return
          setCurrentStepId(stepId)
        }}
      />

      {effectiveCurrentStepId === 'metadata' && (user?.role === 'admin' || user?.role === 'manager' || user?.role === 'approver') && (
        <div className="bg-surface shadow rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-ink mb-4">Requirement Set Metadata</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              updateMetadataMutation.mutate({
                name: metadataForm.name.trim() ? metadataForm.name.trim() : null,
                testing_frequency: metadataForm.testing_frequency || null,
              })
            }}
            className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end"
          >
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Requirement Set Name
              </label>
              <input
                type="text"
                aria-label="Requirement Set Name"
                value={metadataForm.name}
                onChange={(e) =>
                  setMetadataForm({ ...metadataForm, name: e.target.value })
                }
                placeholder="Requirement set name"
                className="w-full px-3 py-2 border border-line-strong rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Testing Frequency
              </label>
              <select
                aria-label="Testing Frequency"
                value={metadataForm.testing_frequency}
                onChange={(e) =>
                  setMetadataForm({ ...metadataForm, testing_frequency: e.target.value })
                }
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
              <button
                type="submit"
                disabled={updateMetadataMutation.isPending}
                className="px-4 py-2 bg-brand text-white rounded-md hover:bg-brand-hover disabled:opacity-50"
              >
                {updateMetadataMutation.isPending ? 'Saving...' : 'Save Metadata'}
              </button>
            </div>
          </form>
        </div>
      )}

      {effectiveCurrentStepId === 'metadata' && metadataComplete && <div className="mb-6 flex justify-end"><button type="button" onClick={() => setCurrentStepId('qa')} className="rounded-md bg-brand px-4 py-2 text-white">Continue to extraction QA</button></div>}
      {effectiveCurrentStepId === 'approval' && <section className="mb-6 space-y-4 rounded-xl border border-line bg-surface p-5" aria-label="Approval summary">
        <h2 className="text-lg font-semibold">{document.status === 'approved' ? 'Requirement set approved' : document.status === 'pending_approval' ? 'Awaiting approval' : 'Ready for approval'}</h2>
        <p className="text-sm text-muted">{allExtractionItems.filter((item) => item.status !== 'rejected').length} extracted sections · {unresolvedReviewCount} flagged items unresolved · {metadataForm.testing_frequency.replace(/_/g, ' ')}</p>
        <p className="max-w-prose text-sm text-muted">{document.status === 'approved' ? 'The published requirement set is ready to include in a certification project or review.' : 'Confirm the requirement text, hierarchy and mandatory or informational classifications before publishing this set.'}</p>
        <div className="flex flex-wrap gap-3"><button type="button" className="text-sm text-accent underline" onClick={() => setCurrentStepId('qa')}>Review extracted requirements</button>{document.status === 'approved' && <Link className="text-sm text-accent underline" to="/certification-projects">Continue to certification projects</Link>}</div>
      </section>}
      {effectiveCurrentStepId === 'qa' && qaStepUnlocked ? (
        <>
          {qaStepComplete && document.status !== 'approved' && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-success-line bg-success-soft p-4"><p className="text-sm text-success">All flagged items are resolved. Check the extracted requirements, then continue.</p><button type="button" onClick={() => setCurrentStepId('approval')} className="rounded-md bg-brand px-4 py-2 text-sm text-white">Continue to approval</button></div>}
          <details className="mb-4 rounded-lg border border-line bg-surface p-4"><summary className="cursor-pointer text-sm font-semibold">Quality summary and bulk actions · {unresolvedReviewCount} items to check</summary><div className="mt-4">
          <ReviewQueueKpiPanel
            unresolvedCount={unresolvedReviewCount}
            resolvedInSession={resolvedInSession}
            reviewReasonDistribution={reviewReasonDistribution}
            sectionDistribution={sectionDistribution}
            bulkReadyCount={bulkReadyCount}
            manualQueueCount={manualQueueCount}
          />

          <BulkTriagePanel
            runId={selectedRunId}
            disabled={!reviewQueueItems.length}
            requirementTypes={requirementTypeOptions}
            sectionOptions={sectionOptions}
            reviewReasons={reviewReasonOptions}
            previewResult={previewBatchResult}
            lastApplyResult={applyBatchResult}
            isPreviewing={previewFeedbackBatchMutation.isPending}
            isApplying={applyFeedbackBatchMutation.isPending}
            onPreview={handlePreviewBulkAction}
            onApply={handleApplyBulkAction}
            canUndo={!!lastBulkUndoSnapshot}
            undoDisabled={undoBulkMutation.isPending}
            undoUnavailableReason={undoUnavailableReason}
            onUndo={handleUndoBulkAction}
          />
          </div></details>

      {extraction?.ai_provider === 'local' && <div role="note" className="mb-6 rounded-lg border border-warning-line bg-warning-soft p-4 text-sm text-ink"><h2 className="font-semibold">Source review required</h2><p className="mt-1">This is a local draft extraction. Compare each requirement with the PDF, including wording, mandatory or informational classification, and parent sections. Every row starts flagged for review. Resolve the flags before submitting for approval.</p></div>}

      {/* Extraction Progress Panel */}
      {isExtracting && extraction && (
        <div className="bg-surface shadow rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-ink mb-4">Extraction Progress</h2>

          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="animate-spin h-5 w-5 border-2 border-info border-t-transparent rounded-full" />
              <span className="text-ink">
                {extraction.status === 'pending' ? 'Waiting to start...' : 'Processing...'}
              </span>
            </div>

            {extraction.total_pages && (
              <>
                <div className="w-full bg-line rounded-full h-3">
                  <div
                    className="bg-brand h-3 rounded-full transition-all duration-300"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
                  <span>
                    Page {extraction.current_page} of {extraction.total_pages}
                  </span>
                  <span>{extraction.requirements_found} requirements found</span>
                </div>
              </>
            )}

            <div className="text-sm text-muted">
              Using {extraction.ai_provider} ({extraction.ai_model})
              {extraction.pipeline_version ? ` • ${extraction.pipeline_version}` : ''}
              {typeof extraction.warning_count === 'number' && extraction.warning_count > 0
                ? ` • ${extraction.warning_count} warning(s)`
                : ''}
            </div>

            <div className="border-t pt-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">Extraction activity</h3>
                {eventLog.length > 25 && (
                  <button
                    type="button"
                    onClick={() => setShowAllEvents((prev) => !prev)}
                    className="text-xs text-info hover:text-info"
                  >
                    {showAllEvents ? 'Show less' : 'Show more'}
                  </button>
                )}
              </div>
              <div className="mt-2 max-h-64 overflow-y-auto rounded border bg-canvas text-xs font-mono">
                {visibleEvents.length ? (
                  visibleEvents.map((event, idx) => {
                    const time = event.timestamp
                      ? new Date(event.timestamp).toLocaleTimeString()
                      : '--:--:--'
                    const page = event.page_number ? `p${event.page_number}` : ''
                    const stage = event.stage || 'event'
                    const message = event.message || ''
                    const duration = event.duration_ms ? ` ${event.duration_ms}ms` : ''
                    const levelClass =
                      event.level === 'error'
                        ? 'text-danger'
                        : event.level === 'warn'
                          ? 'text-warning'
                          : 'text-ink'
                    return (
                      <div key={`${event.timestamp}-${idx}`} className={`px-3 py-1 ${levelClass}`}>
                        <span className="text-muted">{time}</span>{' '}
                        {page && <span className="text-muted">{page}</span>}{' '}
                        <span className="font-semibold">{stage}</span>{' '}
                        <span>{message}</span>
                        {duration && <span className="text-muted">{duration}</span>}
                      </div>
                    )
                  })
                ) : (
                  <div className="px-3 py-2 text-muted">No events yet.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error Display */}
      {document.status === 'extraction_failed' && extraction?.error_message && (
        <div className="bg-danger-soft border border-danger-line rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-danger mb-2">Extraction Failed</h2>
          <p className="text-danger">{extraction.error_message}</p>
          {extraction.error_page && (
            <p className="text-danger text-sm mt-2">Failed on page {extraction.error_page}</p>
          )}
        </div>
      )}

      {recoveryRows.length > 0 && <RecoveryPanel
        rows={recoveryRows}
        allRows={allExtractionItems}
        sourceUrl={`${api.defaults.baseURL}/documents/${documentId}/source`}
        working={recoveryMutation.isPending}
        onResolve={(extractionId, decision) => recoveryMutation.mutate({ extractionId, decision })}
      />}

      {reviewQueueItems.length > 0 && (
        <div className="bg-surface shadow rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-ink mb-2">Review Queue</h2>
          <div className="mb-4 flex flex-wrap items-end gap-3"><label className="min-w-0 flex-1 text-sm text-muted">Find a flagged requirement<input className="mt-1 block w-full px-3 py-2" value={reviewQueueSearch} onChange={e => { setReviewQueueSearch(e.target.value); setReviewQueuePage(0) }} placeholder="Reference or source text" /></label><div className="flex items-center gap-3 text-sm"><button className="rounded border border-line px-3 py-2" disabled={queuePage === 0} onClick={() => setReviewQueuePage(queuePage - 1)}>Previous flags</button><span aria-live="polite">Page {queuePage + 1} of {queuePages} · {queueMatches.length} flagged</span><button className="rounded border border-line px-3 py-2" disabled={queuePage + 1 >= queuePages} onClick={() => setReviewQueuePage(queuePage + 1)}>Next flags</button></div></div>
          <p className="text-sm text-muted mb-4">
            Confirm flagged extractions before submission.
          </p>
          <div className="max-h-[60vh] space-y-3 overflow-y-auto">
            {visibleQueueItems.map((req) => (
              <div key={req.id} className="rounded-md border border-warning-line bg-warning-soft p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs uppercase tracking-wide text-warning">
                      {req.review_reason?.startsWith('Local draft extraction') ? 'Verify source wording and classification' : req.review_reason || 'Needs source review'}
                    </div>
                    <div className="text-sm font-medium text-ink break-words">
                      {req.reference_id || 'Unassigned reference'} · {req.requirement_type.replace(/_/g, ' ')} · {hasPdf ? <a className="text-accent underline" href={`${api.defaults.baseURL}/documents/${documentId}/source#page=${req.page_number}`} target="_blank" rel="noopener noreferrer">Source page {req.page_number}</a> : <span>Page {req.page_number}</span>}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        feedbackMutation.mutate({
                          extractionId: req.id,
                          action: 'accept',
                        })
                      }
                      className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                      disabled={feedbackMutation.isPending}
                    >
                      Accept
                    </button>
                    <button
                      type="button"
                      onClick={() => openExtractionEditor(req)}
                      className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas"
                    >
                      Edit + Accept
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        feedbackMutation.mutate({
                          extractionId: req.id,
                          action: 'reject',
                        })
                      }
                      className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                      disabled={feedbackMutation.isPending}
                    >
                      Reject
                    </button>
                  </div>
                </div>
                <p className="mt-2 text-sm text-ink whitespace-pre-line break-words">{req.text}</p>
                {req.text !== (req.original_text ?? req.text) ? <span className="mt-1 inline-block rounded bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">Modified</span> : null}
                {req.source_excerpt ? (
                  <p className="mt-2 text-xs text-muted break-words">
                    Source excerpt: {req.source_excerpt}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extraction Results */}
      <div className="bg-surface shadow rounded-lg p-6 mb-6">
        <div className="mb-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <h2 className="text-lg font-semibold text-ink">Extraction Results</h2>
          {extractionHistory?.items?.length ? (
            <select
              aria-label="Extraction run"
              value={selectedRunId || ''}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="w-full rounded-md border border-line-strong px-3 py-2 text-sm sm:w-auto"
            >
              {extractionHistory.items.map((run) => (
                <option key={run.id} value={run.id}>
                  {formatDateTime(run.created_at)} • {run.status}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-sm text-muted">No extraction runs yet</span>
          )}
        </div>

        {selectedRun ? (
          <details className="mb-4 text-sm"><summary className="mb-3 cursor-pointer text-muted">Extraction details and diagnostics</summary>
            <div className="mb-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-6">
              <div>
                <span className="text-muted">Status:</span>{' '}
                <span className="text-ink">{selectedRun.status}</span>
              </div>
              <div>
                <span className="text-muted">Pages:</span>{' '}
                <span className="text-ink">
                  {selectedRun.total_pages ? `${selectedRun.current_page}/${selectedRun.total_pages}` : '-'}
                </span>
              </div>
              <div>
                <span className="text-muted">Requirements:</span>{' '}
                <span className="text-ink">{selectedRun.requirements_found}</span>
              </div>
              <div>
                <span className="text-muted">Duration:</span>{' '}
                <span className="text-ink">
                  {formatDuration(selectedRun.started_at, selectedRun.completed_at)}
                </span>
              </div>
              <div>
                <span className="text-muted">OCR:</span>{' '}
                <span className="text-ink">
                  {selectedRun.ocr_applied ? `yes (${selectedRun.ocr_pages || 0} image pages)` : 'no'}
                </span>
              </div>
              <div>
                <span className="text-muted">Parseability:</span>{' '}
                <span className="text-ink">
                  {typeof selectedRun.parseability_score === 'number'
                    ? selectedRun.parseability_score.toFixed(2)
                    : '-'}
                </span>
              </div>
            </div>

            <div className="mb-4 space-y-1 text-xs text-muted">
              {selectedRun.fallback_trigger_reason ? (
                <div>
                  <span className="font-medium text-ink">Fallback:</span>{' '}
                  {selectedRun.fallback_trigger_reason}
                </div>
              ) : (
                <div>
                  <span className="font-medium text-ink">Fallback:</span> Not required
                </div>
              )}
              {selectedRun.strategy_counts ? (
                <div>
                  <span className="font-medium text-ink">Strategies:</span>{' '}
                  rule={selectedRun.strategy_counts.rule || 0}, table={selectedRun.strategy_counts.table || 0},
                  vision={selectedRun.strategy_counts.vision || 0}
                </div>
              ) : null}
            </div>
          </details>
        ) : null}

        {selectedRun?.error_message ? (
          <div className="mb-4 rounded-md border border-danger-line bg-danger-soft p-3 text-sm text-danger">
            {selectedRun.error_message}
            {selectedRun.error_page ? ` (page ${selectedRun.error_page})` : ''}
          </div>
        ) : null}

        {unresolvedReviewCount > 0 ? (
          <div className="mb-4 rounded-md border border-warning-line bg-warning-soft p-3 text-sm text-warning">
            {unresolvedReviewCount} extracted item(s) need review before submit.
          </div>
        ) : null}

        {extractionResults ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-3">
              <label className="min-w-0 flex-1 text-sm text-muted">Find a requirement<input aria-label="Reference, title or source text" value={extractionSearch} onChange={(e) => setExtractionSearch(e.target.value)} placeholder="Reference, title or source text" className="mt-1 block w-full px-3 py-2" /></label>
              <label className="text-sm text-muted">Requirement type<select value={extractionType} onChange={(e) => setExtractionType(e.target.value)} className="mt-1 block px-3 py-2"><option value="">All types</option>{requirementTypeOptions.map((value) => <option key={value} value={value}>{value.replace(/_/g, ' ')}</option>)}</select></label>
              {hasExtractionFilters && <button type="button" onClick={() => { setExtractionSearch(''); setExtractionType('') }} className="self-end px-3 py-2 text-sm text-accent underline">Clear search</button>}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
              <span>
                Showing {visibleExtractionItems.length} of {extractionResults.total} requirements
              </span>
              {totalRejectedCount > 0 ? (
                <label className="inline-flex items-center gap-2 text-xs text-ink">
                  <input
                    type="checkbox"
                    data-testid="show-rejected-toggle"
                    checked={showRejected}
                    onChange={(event) => setShowRejected(event.target.checked)}
                    className="h-4 w-4 rounded border-line-strong"
                  />
                  Show rejected ({totalRejectedCount})
                </label>
              ) : null}
            </div>
            {!showRejected && hiddenRejectedCount > 0 ? (
              <div className="rounded-md border border-line bg-canvas px-3 py-2 text-xs text-ink">
                {hiddenRejectedCount} rejected item(s) hidden from this view.
              </div>
            ) : null}
            {canEditExtractedRequirements ? (
              <div className="text-xs text-info">
                Edit extracted requirements here before final approval. Drag rows to reorder on desktop,
                or use Move up/down on mobile.
              </div>
            ) : null}
            {visibleExtractionItems.length ? (
              <div className="space-y-3">
                <div data-testid="document-extraction-results-mobile-cards" className="max-h-[65vh] space-y-3 overflow-y-auto lg:hidden">
                  {visibleExtractionItems.map((req, visibleIndex) => {
                    const canMoveUp = !hasExtractionFilters && visibleIndex > 0
                    const canMoveDown = !hasExtractionFilters && visibleIndex < visibleExtractionItems.length - 1
                    const isRejected = req.status === 'rejected'
                    const hierarchyMismatch = extractionHierarchyMismatchById.get(req.id)
                    return (
                      <div
                        key={req.id}
                        className={`rounded-lg border p-3 ${
                          isRejected ? 'border-danger-line bg-danger-soft' : 'border-line'
                        }`}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                              Reference
                            </p>
                            <p className="break-words text-sm text-ink">{req.reference_id || '-'}</p>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded bg-subtle px-2 py-1 text-xs text-ink">
                              Page {req.page_number}
                            </span>
                            {isRejected ? (
                              <span className="rounded bg-danger-soft px-2 py-1 text-xs font-medium text-danger">
                                Rejected
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <div className="mt-2 text-xs text-muted">
                          Type: <span className="text-ink">{req.requirement_type}</span>
                        </div>
                        {req.needs_review ? (
                          <div className="text-xs text-warning">
                            Review: {req.review_reason?.startsWith('Local draft extraction') ? 'Verify source wording and classification' : req.review_reason || 'Needs source review'}
                          </div>
                        ) : null}
                        {hierarchyMismatch?.isMismatch ? (
                          <div className="mt-2 rounded-md border border-info-line bg-info-soft px-3 py-2 text-xs text-info">
                            Hierarchy mismatch. Reference implies{' '}
                            {hierarchyMismatch.parentReferenceId
                              ? `parent ${hierarchyMismatch.parentReferenceId}`
                              : 'a top-level item'}
                            .
                          </div>
                        ) : null}
                        <div className="text-xs text-muted">
                          Confidence: <span className="text-ink">{req.confidence_score.toFixed(2)}</span>
                        </div>
                        <div className="mt-2">
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Title</p>
                          <p className="break-words text-sm text-ink">
                            {req.title && req.title !== req.text ? req.title : '-'}
                          </p>
                        </div>
                        <div className="mt-2">
                          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Text</p>
                          {req.text !== (req.original_text ?? req.text) ? <span className="mb-1 inline-block rounded bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">Modified</span> : null}
                          <p className="whitespace-pre-line break-words text-sm text-ink">{req.text}</p>
                        </div>
                        {canEditExtractedRequirements ? (
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => openExtractionEditor(req)}
                              className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas"
                            >
                              Edit
                            </button>
                            {!isRejected ? (
                              <button
                                type="button"
                                onClick={() => requestExtractionDelete(req)}
                                disabled={softDeleteExtractionMutation.isPending}
                                data-testid={`delete-extraction-${req.id}`}
                                className="rounded-md border border-danger-line px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                              >
                                Delete
                              </button>
                            ) : null}
                            {hierarchyMismatch?.isMismatch ? (
                              <button
                                type="button"
                                onClick={() => fixExtractionHierarchy(req.id)}
                                disabled={updateExtractionMutation.isPending}
                                data-testid={`fix-extraction-hierarchy-${req.id}`}
                                className="rounded-md border border-info-line px-3 py-1.5 text-xs font-medium text-info hover:bg-info-soft disabled:opacity-50"
                              >
                                Fix hierarchy
                              </button>
                            ) : null}
                            <button
                              type="button"
                              onClick={() => moveVisibleExtraction(req.id, 'up')}
                              disabled={!canMoveUp || reorderExtractionMutation.isPending}
                              data-testid={`move-up-${req.id}`}
                              className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                            >
                              Move up
                            </button>
                            <button
                              type="button"
                              onClick={() => moveVisibleExtraction(req.id, 'down')}
                              disabled={!canMoveDown || reorderExtractionMutation.isPending}
                              data-testid={`move-down-${req.id}`}
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

                <div className="hidden max-h-[65vh] overflow-auto lg:block">
                  <table data-testid="document-extraction-results-table" className="min-w-full divide-y divide-line text-sm">
                    <thead className="sticky top-0 z-10 bg-canvas">
                      <tr>
                        {canEditExtractedRequirements ? (
                          <th className="w-12 px-2 py-2 text-left text-xs font-medium uppercase text-muted">
                            Order
                          </th>
                        ) : null}
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Reference
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Title
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Type
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Page
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Confidence
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                          Text
                        </th>
                        {canEditExtractedRequirements ? (
                          <th className="px-4 py-2 text-left text-xs font-medium text-muted uppercase">
                            Actions
                          </th>
                        ) : null}
                      </tr>
                    </thead>
                    <tbody className="bg-surface divide-y divide-line">
                      {visibleExtractionItems.map((req) => {
                        const isRejected = req.status === 'rejected'
                        const isDragging = draggingExtractionId === req.id
                        const hierarchyMismatch = extractionHierarchyMismatchById.get(req.id)
                        const rowClass = isRejected
                          ? 'bg-danger-soft/70'
                          : isDragging
                            ? 'bg-info-soft'
                            : ''
                        return (
                          <tr
                            key={req.id}
                            className={rowClass}
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
                                  draggable={!hasExtractionFilters && !reorderExtractionMutation.isPending}
                                  disabled={reorderExtractionMutation.isPending}
                                  onDragStart={(event) => {
                                    event.dataTransfer.effectAllowed = 'move'
                                    event.dataTransfer.setData('text/plain', req.id)
                                    setDraggingExtractionId(req.id)
                                  }}
                                  onDragEnd={() => setDraggingExtractionId(null)}
                                  data-testid={`drag-reorder-handle-${req.id}`}
                                  className="rounded border border-line-strong px-2 py-1 text-xs text-muted hover:bg-canvas disabled:opacity-50"
                                  aria-label={`Drag to reorder ${req.reference_id || req.id}`}
                                >
                                  &#8942;&#8942;
                                </button>
                              </td>
                            ) : null}
                            <td className="px-4 py-2 text-ink break-words">{req.reference_id || '-'}</td>
                            <td className="px-4 py-2 text-ink break-words">
                              {req.title && req.title !== req.text ? req.title : '-'}
                            </td>
                            <td className="px-4 py-2 text-ink">
                              {req.requirement_type}
                              {req.needs_review ? (
                                <span className="ml-2 rounded bg-warning-soft px-2 py-0.5 text-xs text-warning">
                                  flagged
                                </span>
                              ) : null}
                              {isRejected ? (
                                <span className="ml-2 rounded bg-danger-soft px-2 py-0.5 text-xs text-danger">
                                  rejected
                                </span>
                              ) : null}
                              {hierarchyMismatch?.isMismatch ? (
                                <div className="mt-1 text-xs text-info">Hierarchy mismatch</div>
                              ) : null}
                            </td>
                            <td className="px-4 py-2 text-ink">{req.page_number}</td>
                            <td className="px-4 py-2 text-ink">{req.confidence_score.toFixed(2)}</td>
                            <td className="px-4 py-2 text-ink">
                              {req.text !== (req.original_text ?? req.text) ? <span className="mb-1 inline-block rounded bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">Modified</span> : null}
                              <div className="whitespace-pre-line break-words">{req.text}</div>
                            </td>
                            {canEditExtractedRequirements ? (
                              <td className="px-4 py-2">
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    onClick={() => openExtractionEditor(req)}
                                    className="rounded-md border border-line-strong px-3 py-1.5 text-xs font-medium text-ink hover:bg-canvas"
                                  >
                                    Edit
                                  </button>
                                  {!isRejected ? (
                                    <button
                                      type="button"
                                      onClick={() => requestExtractionDelete(req)}
                                      disabled={softDeleteExtractionMutation.isPending}
                                      data-testid={`delete-extraction-${req.id}`}
                                      className="rounded-md border border-danger-line px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                                    >
                                      Delete
                                    </button>
                                  ) : null}
                                  {hierarchyMismatch?.isMismatch ? (
                                    <button
                                      type="button"
                                      onClick={() => fixExtractionHierarchy(req.id)}
                                      disabled={updateExtractionMutation.isPending}
                                      data-testid={`fix-extraction-hierarchy-${req.id}`}
                                      className="rounded-md border border-info-line px-3 py-1.5 text-xs font-medium text-info hover:bg-info-soft disabled:opacity-50"
                                    >
                                      Fix hierarchy
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
                  ? 'No requirements match this view. Clear the search or include rejected items.'
                  : 'No requirements extracted yet.'}
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted">Select a run to view extracted requirements.</p>
        )}
      </div>

      {/* Extraction History */}
      <details className="rounded-lg border border-line bg-surface p-4">
        <summary className="cursor-pointer text-sm font-semibold">Extraction History</summary><div className="mt-4">

        {extractionHistory && extractionHistory.items.length > 0 ? (
          <div className="space-y-3">
            <div data-testid="document-extraction-history-mobile-cards" className="space-y-3 lg:hidden">
              {extractionHistory.items.map((run) => (
                <div key={run.id} className="rounded-lg border border-line p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="break-words text-ink">{formatDateTime(run.created_at)}</div>
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded ${
                        extractionStatusColors[run.status] || 'bg-subtle text-ink'
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="mt-2 space-y-1 text-xs text-muted">
                    <div>
                      Pages:{' '}
                      <span className="text-ink">
                        {run.status === 'completed' || run.status === 'failed'
                          ? `${run.current_page}/${run.total_pages || '?'}`
                          : run.total_pages
                            ? `${run.current_page}/${run.total_pages}`
                            : '-'}
                      </span>
                    </div>
                    <div>
                      Requirements: <span className="text-ink">{run.requirements_found}</span>
                    </div>
                    <div>
                      Duration:{' '}
                      <span className="text-ink">
                        {formatDuration(run.started_at, run.completed_at)}
                      </span>
                    </div>
                    <div>
                      Provider: <span className="break-words text-ink">{run.ai_provider}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="hidden lg:block">
              <table className="min-w-full divide-y divide-line">
                <thead className="bg-canvas">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Pages
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Requirements
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Duration
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted uppercase">
                      Provider
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-surface divide-y divide-line">
                  {extractionHistory.items.map((run) => (
                    <tr key={run.id} className="hover:bg-canvas">
                      <td className="px-4 py-3 text-sm text-ink break-words">
                        {formatDateTime(run.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 text-xs font-medium rounded ${
                            extractionStatusColors[run.status] || 'bg-subtle text-ink'
                          }`}
                        >
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted">
                        {run.status === 'completed' || run.status === 'failed'
                          ? `${run.current_page}/${run.total_pages || '?'}`
                          : run.total_pages
                            ? `${run.current_page}/${run.total_pages}`
                            : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted">{run.requirements_found}</td>
                      <td className="px-4 py-3 text-sm text-muted">
                        {formatDuration(run.started_at, run.completed_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted break-words">{run.ai_provider}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-muted text-sm">No extraction runs yet.</p>
        )}

        {/* Show error details for failed runs */}
        {extractionHistory?.items.some((r) => r.status === 'failed' && r.error_message) && (
          <div className="mt-4 space-y-2">
            {extractionHistory.items
              .filter((r) => r.status === 'failed' && r.error_message)
              .map((run) => (
                <div key={run.id} className="bg-danger-soft border border-danger-line rounded p-3 text-sm">
                  <span className="font-medium text-danger">
                    {formatDateTime(run.created_at)}:
                  </span>{' '}
                  <span className="text-danger">{run.error_message}</span>
                  {run.error_page && (
                    <span className="text-danger"> (page {run.error_page})</span>
                  )}
                </div>
              ))}
          </div>
        )}
      </div></details>
        </>
      ) : null}

      <Modal
        open={editingExtraction !== null}
        title="Edit extracted requirement"
        description="Adjust extracted fields before approving this requirement set."
        onClose={() => setEditingExtraction(null)}
        size="lg"
      >
        {editingExtraction ? (
          <div className="space-y-4">
            {editingExtraction.needs_review ? (
              <div className="rounded-md border border-warning-line bg-warning-soft px-3 py-2 text-xs text-warning">
                This item is in the review queue ({editingExtraction.review_reason || 'needs_review'}).
                Saving edits will mark it accepted.
              </div>
            ) : null}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                  Reference
                </label>
                <input aria-label="Reference"
                  type="text"
                  value={editingExtraction.reference_id}
                  onChange={(event) =>
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, reference_id: event.target.value } : prev
                    )
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                  Title
                </label>
                <input aria-label="Title"
                  type="text"
                  value={editingExtraction.title}
                  onChange={(event) =>
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, title: event.target.value } : prev
                    )
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                  Requirement Type
                </label>
                <select aria-label="Requirement Type"
                  value={editingExtraction.requirement_type}
                  onChange={(event) =>
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, requirement_type: event.target.value } : prev
                    )
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                >
                  <option value="mandatory">mandatory</option>
                  <option value="recommended">recommended</option>
                  <option value="informational">informational</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                  Status
                </label>
                <select aria-label="Status"
                  value={editingExtraction.status}
                  onChange={(event) =>
                    setEditingExtraction((prev) =>
                      prev ? { ...prev, status: event.target.value } : prev
                    )
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                >
                  <option value="pending">pending</option>
                  <option value="accepted">accepted</option>
                  <option value="rejected">rejected</option>
                </select>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                Text
              </label>
              <textarea aria-label="Text"
                rows={8}
                value={editingExtraction.text}
                onChange={(event) =>
                  setEditingExtraction((prev) => (prev ? { ...prev, text: event.target.value } : prev))
                }
                className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
              />
            </div>
            <details className="rounded-md border border-line p-3 text-sm">
              <summary className="cursor-pointer font-medium text-ink">Compare extracted and current wording</summary>
              <div className="mt-3 space-y-3">
                <section aria-label="Original extracted wording">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Original extracted wording</h3>
                  <div className="mt-1 whitespace-pre-wrap break-words text-ink" dangerouslySetInnerHTML={{ __html: normalizeRichText(editingExtraction.original_text) }} />
                </section>
                <section aria-label="Current editable text">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Current editable text</h3>
                  <div className="mt-1 whitespace-pre-wrap break-words text-ink" dangerouslySetInnerHTML={{ __html: normalizeRichText(editingExtraction.text) }} />
                </section>
                {editingExtraction.source_excerpt ? (
                  <section aria-label="Source excerpt">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Source excerpt</h3>
                    <p className="mt-1 whitespace-pre-wrap break-words text-ink">{editingExtraction.source_excerpt}</p>
                  </section>
                ) : null}
                <p className="text-xs text-muted">
                  {hasPdf && editingExtraction.page_number ? (
                    <a className="text-accent underline" href={`${api.defaults.baseURL}/documents/${documentId}/source#page=${editingExtraction.page_number}`} target="_blank" rel="noopener noreferrer">Source PDF, page {editingExtraction.page_number}</a>
                  ) : editingExtraction.page_number ? `Source page ${editingExtraction.page_number}` : null}
                  {editingExtraction.parser_strategy ? ` · Extraction method: ${editingExtraction.parser_strategy}` : ''}
                </p>
              </div>
            </details>
            <div className="flex flex-wrap items-center justify-between gap-2">
              {editingExtraction.status !== 'rejected' ? (
                <button
                  type="button"
                  onClick={() =>
                    requestExtractionDelete({
                      id: editingExtraction.id,
                      reference_id: editingExtraction.reference_id,
                      title: editingExtraction.title || null,
                    })
                  }
                  disabled={softDeleteExtractionMutation.isPending}
                  className="rounded-md border border-danger-line px-4 py-2 text-sm text-danger hover:bg-danger-soft disabled:opacity-50"
                >
                  Delete
                </button>
              ) : (
                <span />
              )}
              <div className="flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditingExtraction(null)}
                  className="rounded-md border border-line-strong px-4 py-2 text-sm text-ink hover:bg-canvas"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={submitExtractionEdit}
                  disabled={updateExtractionMutation.isPending || feedbackMutation.isPending}
                  className="rounded-md bg-brand px-4 py-2 text-sm text-white hover:bg-brand-hover disabled:opacity-50"
                >
                  {updateExtractionMutation.isPending || feedbackMutation.isPending
                    ? 'Saving...'
                    : editingExtraction.needs_review
                      ? 'Save + Accept'
                      : 'Save changes'}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </Modal>

      <DecisionModal
        open={decisionDialog !== null}
        title={decisionDialog === 'approve' ? 'Approve requirement set' : 'Reject requirement set'}
        description={
          decisionDialog === 'approve'
            ? 'Add an optional approval comment for the audit trail.'
            : 'Provide a rejection reason for the audit trail.'
        }
        confirmLabel={decisionDialog === 'approve' ? 'Approve' : 'Reject'}
        confirmVariant={decisionDialog === 'approve' ? 'primary' : 'destructive'}
        rationaleMode={decisionDialog === 'approve' ? 'optional' : 'required'}
        rationaleLabel={decisionDialog === 'approve' ? 'Approval comment' : 'Rejection comment'}
        rationalePlaceholder={
          decisionDialog === 'approve'
            ? 'Optional approval comment...'
            : 'Rejection comment (required)...'
        }
        rationaleValue={decisionComment}
        onRationaleChange={setDecisionComment}
        onConfirm={submitDecision}
        onClose={() => setDecisionDialog(null)}
        isWorking={approveMutation.isPending || rejectMutation.isPending}
      />

      <DecisionModal
        open={deleteDialogOpen}
        title="Delete requirement set"
        description="This action permanently deletes the requirement set and linked artifacts."
        confirmLabel="Delete"
        confirmVariant="destructive"
        dangerDetails={[
          'Delete requirements and associated evidence references.',
          'Delete extraction records and uploaded files.',
          'Remove linked review items for this set.',
        ]}
        onConfirm={handleDeleteRequirementSet}
        onClose={() => setDeleteDialogOpen(false)}
      />
      <DecisionModal
        open={pendingExtractionDelete !== null}
        title="Delete extracted requirement"
        description="This will soft delete the extracted row by setting it to rejected."
        confirmLabel="Delete"
        confirmVariant="destructive"
        dangerDetails={[
          'The row will be hidden from default results view.',
          'Review flags will be cleared for this row.',
        ]}
        onConfirm={confirmPendingExtractionDelete}
        onClose={() => setPendingExtractionDelete(null)}
        isWorking={softDeleteExtractionMutation.isPending}
      />
    </div>
  )
}
