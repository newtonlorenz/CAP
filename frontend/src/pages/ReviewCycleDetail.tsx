import './workflow-pages.css'
import DraftSaveStatus from '../components/ui/DraftSaveStatus'
import CopyButton from '../components/ui/CopyButton'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import Button from '../components/ui/Button'
import IconButton from '../components/ui/IconButton'
import { useCapabilities } from '../hooks/useCapabilities'
import ReviewCompletion from '../components/ReviewCompletion'
import DropdownMenu from '../components/ui/DropdownMenu'
import { formatDate, formatDateTime } from '../utils/dateFormat'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import api from '../api/client'
import { getApiErrorDetail, getApiErrorMessage } from '../api/errors'
import type {
  ReviewCycleWithItems,
  ReviewItemBulkMutationRequest,
  ReviewItemBulkMutationResponse,
  ReviewItemWithRequirement,
  PaginatedResponse,
  RequirementSetSummary,
  User,
  UserMention,
} from '../types'
import { normalizeRichText, stripHtml } from '../utils/richText'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import ReviewEvidenceEditor from '../components/review/ReviewEvidenceEditor'
import ReviewBaselineMigration from '../components/review/ReviewBaselineMigration'
import { useReviewEvidenceFiles } from '../hooks/review/useReviewEvidenceFiles'
import { useReviewItemDrafts } from '../hooks/review/useReviewItemDrafts'
import { useReviewFocus } from '../hooks/review/useReviewFocus'
import ReviewCycleReportOptions from '../components/ReviewCycleReportOptions'
import ReviewGapExport from '../components/ReviewGapExport'
import RequirementsOutline from '../components/RequirementsOutline'
import { useHierarchyDepth } from '../hooks/useHierarchyDepth'
import ResizableSplitView from '../components/ResizableSplitView'
import DecisionModal from '../components/ui/DecisionModal'
import { buildOutlineTree, type FlattenedNavItem, type OutlineNode } from '../utils/requirementsOutline'
import {
  buildHierarchyTree,
  flattenHierarchyTree,
  withHierarchyContext,
  type HierarchyNode,
} from '../utils/requirementHierarchy'
import { notifyApiError } from '../utils/notify'
import { useReviewLocation } from '../hooks/useReviewLocation'

type MentionState = {
  active: boolean
  query: string
  start: number
  end: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getFirstFailureDetail(err: unknown): string | null {
  if (!axios.isAxiosError(err)) return null
  const data: unknown = err.response?.data
  if (!isRecord(data)) return null

  const detail = data.detail
  if (!isRecord(detail)) return null

  const failures = detail.failures
  if (!Array.isArray(failures) || failures.length === 0) return null
  const first = failures[0]
  if (!isRecord(first)) return null

  return typeof first.error === 'string' ? first.error : null
}

const renderCommentMentions = (value: string, offset: number): Array<string | JSX.Element> => {
  const parts: Array<string | JSX.Element> = []
  const pattern = /@([A-Za-z0-9._-]+(?:\s+[A-Za-z0-9._-]+)*)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = pattern.exec(value)) !== null) {
    if (match.index > lastIndex) {
      parts.push(value.slice(lastIndex, match.index))
    }
    parts.push(
      <span key={`mention-${offset + match.index}`} className="font-medium text-info">
        {match[0]}
      </span>
    )
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < value.length) {
    parts.push(value.slice(lastIndex))
  }
  return parts
}

const renderCommentBody = (value: string): Array<string | JSX.Element> => {
  const parts: Array<string | JSX.Element> = []
  const pattern = /\b(?:https?:\/\/|www\.)[^\s<>"']+/gi
  let lastIndex = 0
  for (const match of value.matchAll(pattern)) {
    const start = match.index!
    parts.push(...renderCommentMentions(value.slice(lastIndex, start), lastIndex))

    // Leave sentence punctuation and unmatched closing brackets outside the link.
    let label = match[0]
    const openingBrackets: Record<string, string> = { ')': '(', ']': '[', '}': '{' }
    while (label) {
      const last = label[label.length - 1]
      const opening = openingBrackets[last]
      if (/[.,;:!?]/.test(last)
        || (opening && label.split(last).length > label.split(opening).length)) {
        label = label.slice(0, -1)
      } else {
        break
      }
    }

    const href = /^www\./i.test(label) ? `https://${label}` : label
    let valid = false
    try {
      const url = new URL(href)
      valid = url.protocol === 'http:' || url.protocol === 'https:'
    } catch {
      // Incomplete or malformed addresses remain plain text.
    }
    if (valid) {
      parts.push(
        <a key={`link-${start}`} href={href} target="_blank" rel="noopener noreferrer"
          className="break-all text-info underline hover:text-ink">
          {label}
        </a>
      )
      parts.push(match[0].slice(label.length))
    } else {
      parts.push(...renderCommentMentions(match[0], start))
    }
    lastIndex = start + match[0].length
  }
  parts.push(...renderCommentMentions(value.slice(lastIndex), lastIndex))
  return parts
}

export default function ReviewCycleDetail() {
  const { data: capabilities } = useCapabilities()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const isAdmin = user?.role === 'admin'
  const isAdminOrManager = user?.role === 'admin' || user?.role === 'manager'
  const isAssignedReviewer = user?.role === 'assigned_reviewer'
  const canEditJira = user?.role === 'admin' || user?.role === 'manager' || user?.role === 'contributor'
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return true
    if (typeof window.matchMedia !== 'function') return window.innerWidth >= 1024
    return window.matchMedia('(min-width: 1024px)').matches
  })
  const { params: locationParams, update: updateLocation } = useReviewLocation()
  const search = locationParams.get('q') || ''
  const setSearch = (value: string) => updateLocation({ q: value, item: null })
  const reviewStatusFilter = locationParams.get('review_status') || 'all'
  const setReviewStatusFilter = (value: string) => updateLocation({ review_status: value, item: null })
  const requirementStatusFilter = locationParams.get('requirement_status') || 'all'
  const setRequirementStatusFilter = (value: string) => updateLocation({ requirement_status: value, item: null })
  const responsibleUserFilter = locationParams.get('owner') || 'all'
  const setResponsibleUserFilter = (value: string) => updateLocation({ owner: value, item: null })
  const assignedReviewerFilter = locationParams.get('reviewer') || 'all'
  const setAssignedReviewerFilter = (value: string) => updateLocation({ reviewer: value, item: null })
  const pendingOnly = locationParams.get('pending') === '1'
  const setPendingOnly = (value: boolean) => updateLocation({ pending: value ? '1' : null, item: null })
  const attentionOnly = locationParams.get('attention') === '1'
  const noEvidenceOnly = locationParams.get('no_evidence') === '1'
  const hideInformational = locationParams.get('hide_info') === '1'
  const hierarchyDepth = useHierarchyDepth()
  const focused = locationParams.get('mode') === 'focus'
  const requestedItemId = locationParams.get('item')
  const clearFilters = () => updateLocation({ q: null, pending: null, attention: null, no_evidence: null, hide_info: null, review_status: null, requirement_status: null, owner: null, reviewer: null, item: null })
  const hasFilters = Boolean(search || pendingOnly || attentionOnly || noEvidenceOnly || hideInformational || reviewStatusFilter !== 'all' || requirementStatusFilter !== 'all' || responsibleUserFilter !== 'all' || assignedReviewerFilter !== 'all')
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false)
  const [selectedItemIds, setSelectedItemIds] = useState<Record<string, boolean>>({})
  const [bulkReviewStatus, setBulkReviewStatus] = useState('no_change')
  const [bulkAssignedReviewerId, setBulkAssignedReviewerId] = useState('no_change')
  const [bulkResponsibleUserId, setBulkResponsibleUserId] = useState('no_change')
  const [showReminderModal, setShowReminderModal] = useState(false)
  const [reminderStatuses, setReminderStatuses] = useState<string[]>(['pending'])
  const [commentFiles, setCommentFiles] = useState<Record<string, File[]>>({})
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({})
  const [editingComment, setEditingComment] = useState<{
    itemId: string
    commentId: string
  } | null>(null)
  const [editingCommentBody, setEditingCommentBody] = useState('')
  const [postingCommentItemId, setPostingCommentItemId] = useState<string | null>(null)
  const [savingCommentId, setSavingCommentId] = useState<string | null>(null)
  const [mentionStates, setMentionStates] = useState<Record<string, MentionState>>({})
  const [editMentionState, setEditMentionState] = useState<MentionState | null>(null)
  const commentInputRefs = useRef<Record<string, HTMLTextAreaElement | null>>({})
  const editTextareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [jiraKeyDrafts, setJiraKeyDrafts] = useState<Record<string, string>>({})
  const [savingJiraItemId, setSavingJiraItemId] = useState<string | null>(null)
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (typeof window.matchMedia === 'function') {
      const mql = window.matchMedia('(min-width: 1024px)')
      const onChange = () => setIsDesktop(mql.matches)
      onChange()
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    }

    const onResize = () => setIsDesktop(window.innerWidth >= 1024)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const [reportOptionsOpen, setReportOptionsOpen] = useState(false)
  const [gapExportOpen, setGapExportOpen] = useState(false)
  const [reviewerDisplay, setReviewerDisplay] = useState<'both' | 'names' | 'emails'>(
    'both'
  )
  const [isArchiving, setIsArchiving] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showArchiveModal, setShowArchiveModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const headingTags = ['h2', 'h3', 'h4', 'h5', 'h6'] as const
  const headingSizes = ['text-2xl', 'text-xl', 'text-lg', 'text-base', 'text-sm'] as const

  const { data: cycle, isLoading, error: cycleError, refetch: retryCycle } = useQuery({
    queryKey: ['review-cycle', id],
    queryFn: async () => {
      const response = await api.get<ReviewCycleWithItems>(`/review-cycles/${id}`)
      return response.data
    },
  })
  const { getDraft, changeStatus, changeEvidence, saveEvidence, retryItem, itemNeedsSave, saveStatusByItem, hasUnsavedChanges } = useReviewItemDrafts(id, cycle?.items, () => {
    void queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
    void queryClient.invalidateQueries({ queryKey: ['requirements'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  })
  const hasCommentDrafts = Object.values(commentDrafts).some(value => value.trim())
    || Object.values(commentFiles).some(files => files.length > 0)
    || Boolean(editingComment)
  useDraftNavigationGuard(hasUnsavedChanges || hasCommentDrafts)
  const evidenceFiles = useReviewEvidenceFiles(id, cycle?.status === 'active')
  const showJiraUi = Boolean(cycle?.jira_integration_configured)
  const restoredCycleStatusLabel =
    cycle && (cycle.closed_at || cycle.closed_by || cycle.snapshot_id) ? 'closed' : 'active'

  useEffect(() => {
    if (!cycle?.jurisdiction_id) return
    if (jurisdictionId && cycle.jurisdiction_id !== jurisdictionId) {
      setJurisdictionId(cycle.jurisdiction_id)
    }
  }, [cycle?.jurisdiction_id, jurisdictionId, setJurisdictionId])

  const { data: requirementSets } = useQuery({
    queryKey: ['requirements-sets', 'all', cycle?.jurisdiction_id],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      params.set('include_archived_documents', 'true')
      if (cycle?.jurisdiction_id) params.set('jurisdiction_id', cycle.jurisdiction_id)
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data
    },
    enabled: !!cycle?.jurisdiction_id,
  })

  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<User>>('/users?limit=1000')
      return response.data
    },
    enabled: isAdmin,
  })

  const { data: mentionUsers } = useQuery({
    queryKey: ['mention-users'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<UserMention>>(
        '/users/mentions?limit=1000'
      )
      return response.data
    },
    enabled: !!user,
  })

  useEffect(() => {
    if (!cycle) return
    setJiraKeyDrafts((prev) => {
      const next: Record<string, string> = {}
      cycle.items.forEach((item) => {
        next[item.id] = prev[item.id] ?? item.jira_issue_key ?? ''
      })
      return next
    })
  }, [cycle])

  const assignMutation = useMutation({
    mutationFn: async (payload: {
      itemId: string
      assigned_reviewer_id?: string | null
      responsible_user_id?: string | null
    }) => {
      await api.put(`/review-cycles/${id}/items/${payload.itemId}/assign`, {
        assigned_reviewer_id: payload.assigned_reviewer_id,
        responsible_user_id: payload.responsible_user_id,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Assignment failed')
    },
  })

  const bulkMutation = useMutation({
    mutationFn: async (payload: ReviewItemBulkMutationRequest) => {
      const response = await api.patch<ReviewItemBulkMutationResponse>(
        `/review-cycles/${id}/items/bulk`,
        payload
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setSelectedItemIds({})
      if (data.failed_count > 0) {
        toast.info(`Updated ${data.updated_count}; ${data.failed_count} failed`)
      } else {
        toast.success(`Updated ${data.updated_count} review items`)
      }
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Bulk update failed')
    },
  })

  const updateJiraMutation = useMutation({
    mutationFn: async ({
      itemId,
      jira_issue_key,
    }: {
      itemId: string
      jira_issue_key: string | null
    }) => {
      await api.put(`/review-cycles/${id}/items/${itemId}/jira`, { jira_issue_key })
    },
    onMutate: ({ itemId }) => {
      setSavingJiraItemId(itemId)
    },
    onSettled: () => {
      setSavingJiraItemId(null)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Jira update failed')
    },
  })

  const syncJiraMutation = useMutation({
    mutationFn: async (force: boolean) => {
      const response = await api.post(`/review-cycles/${id}/jira-sync`, { force })
      return response.data as {
        integration_configured: boolean
        refreshed_items: number
        skipped_fresh_items: number
        failed_items: number
      }
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      if (!data.integration_configured) {
        toast.info('Jira is not configured or is disabled.')
        return
      }
      toast.success(
        `Jira refreshed: ${data.refreshed_items} updated, ${data.skipped_fresh_items} fresh, ${data.failed_items} failed.`
      )
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Jira refresh failed')
    },
  })

  const remindMutation = useMutation({
    mutationFn: async (statuses: string[]) => {
      const response = await api.post(`/review-cycles/${id}/remind-assigned`, {
        review_statuses: statuses,
      })
      return response.data
    },
    onSuccess: (data) => {
      setShowReminderModal(false)
      toast.success(
        `Emails sent to ${data.reviewers_emailed} reviewers covering ${data.items_included} items.`
      )
    },
    onError: (error: unknown) => {
      const message = getApiErrorDetail(error) || getApiErrorMessage(error, 'Reminder failed')
      const firstFailure = getFirstFailureDetail(error)
      toast.error([message, firstFailure].filter(Boolean).join(' '))
    },
  })

  const archiveCycleMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/review-cycles/${id}/archive`)
    },
    onMutate: () => {
      setIsArchiving(true)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      toast.success('Review archived')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to archive review')
    },
    onSettled: () => {
      setIsArchiving(false)
    },
  })

  const restoreCycleMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/review-cycles/${id}/restore`)
    },
    onMutate: () => {
      setIsRestoring(true)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      toast.success('Review unarchived')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to unarchive review')
    },
    onSettled: () => {
      setIsRestoring(false)
    },
  })

  const deleteCycleMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/review-cycles/${id}`)
    },
    onMutate: () => {
      setIsDeleting(true)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      queryClient.removeQueries({ queryKey: ['review-cycle', id] })
      navigate('/review-cycles')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to delete review')
    },
    onSettled: () => {
      setIsDeleting(false)
    },
  })

  const createCommentMutation = useMutation({
    mutationFn: async ({ itemId, body, files }: { itemId: string; body: string; files: File[] }) => {
      if (files.length) {
        const form = new FormData()
        form.append('body', body)
        files.forEach(file => form.append('files', file))
        await api.post(`/review-cycles/${id}/items/${itemId}/comments/attachments`, form)
      } else {
        await api.post(`/review-cycles/${id}/items/${itemId}/comments`, { body })
      }
    },
    onMutate: ({ itemId }) => {
      setPostingCommentItemId(itemId)
    },
    onSettled: () => {
      setPostingCommentItemId(null)
    },
    onSuccess: (_data, variables) => {
      setCommentDrafts((prev) => ({ ...prev, [variables.itemId]: '' }))
      setCommentFiles((prev) => ({ ...prev, [variables.itemId]: [] }))
      setMentionStates((prev) => {
        const next = { ...prev }
        delete next[variables.itemId]
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Comment failed')
    },
  })

  const editCommentMutation = useMutation({
    mutationFn: async ({
      itemId,
      commentId,
      body,
    }: {
      itemId: string
      commentId: string
      body: string
    }) => {
      await api.put(`/review-cycles/${id}/items/${itemId}/comments/${commentId}`, { body })
    },
    onMutate: ({ commentId }) => {
      setSavingCommentId(commentId)
    },
    onSettled: () => {
      setSavingCommentId(null)
    },
    onSuccess: () => {
      setEditingComment(null)
      setEditingCommentBody('')
      setEditMentionState(null)
      queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Comment update failed')
    },
  })

  const docMap = useMemo(() => {
    const map = new Map<string, string>()
    requirementSets?.items.forEach((set) => {
      map.set(set.document_id, set.name || set.filename || 'Requirement set')
    })
    return map
  }, [requirementSets?.items])

  const mentionableUsers = useMemo(() => mentionUsers?.items || [], [mentionUsers?.items])

  const assignableUsers = useMemo(
    () => (users?.items || []).filter((u) => u.active),
    [users?.items]
  )

  const responsibleOptions = useMemo(
    () => (isAdmin ? assignableUsers : mentionableUsers),
    [assignableUsers, isAdmin, mentionableUsers]
  )

  const itemsByDocument = useMemo(() => {
    const map = new Map<string, ReviewItemWithRequirement[]>()
    cycle?.items.forEach((item) => {
      const docId = item.requirement.document_id || 'Unassigned document'
      if (!map.has(docId)) {
        map.set(docId, [])
      }
      map.get(docId)!.push(item)
    })
    return map
  }, [cycle])

  const reviewStatuses = ['pending', 'confirmed', 'updated', 'escalated']
  const requirementStatuses = [
    'not_started',
    'in_progress',
    'blocked',
    'evidenced',
    'not_applicable',
  ]
  const isNonActionableType = (value: string) =>
    value === 'informational'
  const progressPercent =
    cycle && cycle.progress.total > 0
      ? Math.round((cycle.progress.completed / cycle.progress.total) * 100)
      : 0

  const formatLabel = (value: string) =>
    value
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')

  const queueViews = [
    { key: 'attention', label: 'Needs attention', active: attentionOnly, changes: { attention: attentionOnly ? null : '1', no_evidence: null, pending: null, review_status: null } },
    { key: 'no_evidence', label: 'No evidence recorded', active: noEvidenceOnly, changes: { no_evidence: noEvidenceOnly ? null : '1', attention: null, pending: null, review_status: null } },
    { key: 'my_pending', label: 'My pending', active: pendingOnly && (isAssignedReviewer ? assignedReviewerFilter : responsibleUserFilter) === user?.id,
      changes: { pending: '1', attention: null, no_evidence: null, review_status: null, [isAssignedReviewer ? 'reviewer' : 'owner']: user?.id || null } },
    { key: 'unassigned', label: 'Unassigned', active: responsibleUserFilter === 'unassigned' && assignedReviewerFilter === 'unassigned', changes: { owner: 'unassigned', reviewer: 'unassigned' } },
    { key: 'escalated', label: 'Escalated', active: reviewStatusFilter === 'escalated', changes: { review_status: 'escalated', pending: null, attention: null, no_evidence: null } },
  ]
  const toggleQueueView = (view: typeof queueViews[number]) => {
    const changes: Record<string, string | null> = { item: null }
    Object.entries(view.changes).forEach(([key, value]) => { changes[key] = view.active ? null : value ?? null })
    updateLocation(changes)
  }
  const attentionReasons = new Map(cycle?.readiness?.blockers.map(blocker => [blocker.item_id, blocker.reasons]) || [])
  const noEvidenceRecordedFor = (
    item: ReviewItemWithRequirement,
    evidence = item.review_evidence || '',
    status = item.requirement_current_status,
  ) =>
    !isNonActionableType(item.requirement.requirement_type)
    && item.requirement.requirement_type !== 'not_applicable'
    && status !== 'not_applicable'
    && !stripHtml(evidence).trim()
    && !item.evidence_files?.length
  const needsAttentionFor = (item: ReviewItemWithRequirement) => {
    if (isNonActionableType(item.requirement.requirement_type)) return false
    // Readiness is computed by the same assessment rules used for completion and exports.
    if (cycle?.readiness) return attentionReasons.has(item.id)
    return item.review_status === 'pending' || item.review_status === 'escalated'
      || !['evidenced', 'not_applicable'].includes(item.requirement_current_status || 'not_started')
      || (item.requirement_current_status === 'not_applicable' && !stripHtml(item.review_evidence || '').trim())
  }
  const matchesUserFilter = (
    filterValue: string,
    userId: string | null | undefined
  ) => {
    if (filterValue === 'all') return true
    if (filterValue === 'unassigned') return !userId
    return userId === filterValue
  }
  const normalize = (value: string) => value.toLowerCase().trim()
  const downloadReport = async (
    endpoint: string,
    filename: string,
    params?: URLSearchParams
  ) => {
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
      notifyApiError(toast, error, 'Report download failed. Please try again.')
    }
  }
  const confirmReviewCycleReport = () => {
    if (!id) return
    const params = new URLSearchParams()
    params.set('review_cycle_id', id)
    params.set('reviewer_display', reviewerDisplay)
    downloadReport('/reports/review-cycle-report', 'review-cycle-report.pdf', params)
    setReportOptionsOpen(false)
  }
  const handleArchiveCycle = () => {
    if (!cycle) return
    setShowArchiveModal(true)
  }
  const handleDeleteCycle = () => {
    if (!cycle) return
    setShowDeleteModal(true)
  }
  const getMentionState = (value: string, cursor: number | null): MentionState | null => {
    const position = cursor ?? value.length
    const upToCursor = value.slice(0, position)
    const match = /(^|\s)@([A-Za-z0-9._-]*)$/.exec(upToCursor)
    if (!match) return null
    const query = match[2] ?? ''
    const start = Math.max(0, position - query.length - 1)
    return { active: true, query, start, end: position }
  }
  const getMentionSuggestions = (query: string) => {
    if (!mentionableUsers.length) return []
    const normalizedQuery = query.toLowerCase().trim()
    const filtered = normalizedQuery
      ? mentionableUsers.filter((u) => {
          const name = u.full_name.toLowerCase()
          const email = u.email.toLowerCase()
          return name.includes(normalizedQuery) || email.includes(normalizedQuery)
        })
      : mentionableUsers
    return filtered.slice(0, 6)
  }
  const applyMentionToDraft = (itemId: string, userMention: UserMention) => {
    const state = mentionStates[itemId]
    if (!state) return
    const currentValue = commentDrafts[itemId] || ''
    const mentionText = `@${userMention.full_name || userMention.email}`
    const nextValue =
      currentValue.slice(0, state.start) +
      mentionText +
      ' ' +
      currentValue.slice(state.end)
    setCommentDrafts((prev) => ({ ...prev, [itemId]: nextValue }))
    setMentionStates((prev) => ({ ...prev, [itemId]: { ...state, active: false } }))
    requestAnimationFrame(() => {
      const el = commentInputRefs.current[itemId]
      if (el) {
        const pos = state.start + mentionText.length + 1
        el.focus()
        el.setSelectionRange(pos, pos)
      }
    })
  }
  const applyMentionToEdit = (userMention: UserMention) => {
    if (!editMentionState) return
    const mentionText = `@${userMention.full_name || userMention.email}`
    const nextValue =
      editingCommentBody.slice(0, editMentionState.start) +
      mentionText +
      ' ' +
      editingCommentBody.slice(editMentionState.end)
    setEditingCommentBody(nextValue)
    setEditMentionState({ ...editMentionState, active: false })
    requestAnimationFrame(() => {
      if (editTextareaRef.current) {
        const pos = editMentionState.start + mentionText.length + 1
        editTextareaRef.current.focus()
        editTextareaRef.current.setSelectionRange(pos, pos)
      }
    })
  }

  const getHierarchyLevel = (referenceId: string, depth: number) => {
    const match = /^(\d+(?:\.\d+)*)\.?$/.exec(referenceId.trim())
    if (match) {
      const segments = match[1].split('.')
      return Math.max(segments.length, 1)
    }
    return Math.max(depth + 1, 1)
  }

  const getHeadingIndex = (referenceId: string, depth: number) => {
    const level = getHierarchyLevel(referenceId, depth)
    return Math.min(Math.max(level - 1, 0), headingTags.length - 1)
  }

  const getIndentPx = (referenceId: string, depth: number) => {
    const level = getHierarchyLevel(referenceId, depth)
    const raw = (level - 1) * 16
    return Math.min(Math.max(raw, 0), 48)
  }

  const matchesFilters = (item: ReviewItemWithRequirement, draft: {
    review_status: string
    requirement_status: string
    review_evidence: string
  }) => {
    if (attentionOnly && !needsAttentionFor(item)) return false
    if (noEvidenceOnly && !noEvidenceRecordedFor(item, draft.review_evidence, draft.requirement_status)) return false
    if (pendingOnly && draft.review_status !== 'pending') return false
    if (reviewStatusFilter !== 'all' && draft.review_status !== reviewStatusFilter) {
      return false
    }
    if (
      requirementStatusFilter !== 'all' &&
      draft.requirement_status !== requirementStatusFilter
    ) {
      return false
    }
    if (!matchesUserFilter(responsibleUserFilter, item.responsible_user_id)) return false
    if (!matchesUserFilter(assignedReviewerFilter, item.assigned_reviewer_id)) return false
    if (search.trim()) {
      const haystack = [
        item.requirement.reference_id,
        item.requirement.title || '',
        stripHtml(item.requirement.text || ''),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(normalize(search))
    }
    return true
  }

  const matchesSearch = (item: ReviewItemWithRequirement) => {
    if (!search.trim()) return true
    const haystack = [
      item.requirement.reference_id,
      item.requirement.title || '',
      stripHtml(item.requirement.text || ''),
    ]
      .join(' ')
      .toLowerCase()
    return haystack.includes(normalize(search))
  }

  const buildFilteredHierarchy = (roots: HierarchyNode<ReviewItemWithRequirement>[]) => {
    const filterNode = (
      node: HierarchyNode<ReviewItemWithRequirement>
    ): HierarchyNode<ReviewItemWithRequirement>[] => {
      const initialReviewStatus = node.item.review_status
      const initialRequirementStatus =
        node.item.requirement_current_status || 'not_started'
      const initialEvidence = node.item.review_evidence || ''
      const draft =
        getDraft(node.item) || {
          review_status: initialReviewStatus,
          requirement_status: initialRequirementStatus,
          review_evidence: initialEvidence,
        }

      const filteredChildren = node.children
        .flatMap((child) => filterNode(child))

      if (isNonActionableType(node.item.requirement.requirement_type)) {
        if (hideInformational) return filteredChildren
        const assignmentMatches =
          matchesUserFilter(responsibleUserFilter, node.item.responsible_user_id) &&
          matchesUserFilter(assignedReviewerFilter, node.item.assigned_reviewer_id)
        const informationalMatches = !attentionOnly && !noEvidenceOnly && !pendingOnly && reviewStatusFilter === 'all' && requirementStatusFilter === 'all' && assignmentMatches && matchesSearch(node.item)
        return filteredChildren.length || informationalMatches
          ? [{ ...node, children: filteredChildren }]
          : []
      }

      if (matchesFilters(node.item, draft) || (focused && requestedItemId === node.item.id && itemNeedsSave(node.item))) {
        return [{ ...node, children: filteredChildren }]
      }

      return filteredChildren
    }

    return flattenHierarchyTree(
      roots.flatMap((root) => filterNode(root))
    )
  }

  const docSections = Array.from(itemsByDocument.entries()).map(
    ([docId, items]) => {
      const roots = buildHierarchyTree(items, {
        getId: (item) => item.requirement.id,
        getReferenceId: (item) => item.requirement.reference_id,
        getParentId: (item) => item.requirement.parent_id,
        getSortOrder: (item) => item.requirement.sort_order,
      })
      const allRows = flattenHierarchyTree(roots)
      const matchingIds = new Set(buildFilteredHierarchy(roots).map(({ item }) => item.id))
      const flattened = allRows.filter(({ item }) => matchingIds.has(item.id))
      const totalForDoc = items.filter((item) =>
        !isNonActionableType(item.requirement.requirement_type)
        && (getDraft(item)).requirement_status !== 'not_applicable'
      ).length
      const pendingForDoc = items.filter((item) => {
        if (isNonActionableType(item.requirement.requirement_type)) return false
        const draft =
          getDraft(item) || {
            review_status: item.review_status,
            requirement_status: item.requirement_current_status || 'not_started',
            review_evidence: item.review_evidence || '',
          }
        return draft.review_status === 'pending' && draft.requirement_status !== 'not_applicable'
      }).length

      const outlineItems: FlattenedNavItem[] = withHierarchyContext(allRows, (item) => matchingIds.has(item.id))
        .map(({ item, depth, isContext }) => ({
          isContext,
          key: item.id,
          targetId: `review-item-${item.id}`,
          referenceId: item.requirement.reference_id,
          title: item.requirement.title || null,
          // Use the same hierarchy used in the review list. Deriving depth purely from
          // numeric segments (e.g., "12.1") can create phantom parents when "12" doesn't exist.
          depth,
        }))
      const maxOutlineDepth = outlineItems.reduce(
        (max, item) => Math.max(max, item.depth),
        0
      )

      const hiddenOutlineIds = new Set(allRows.filter(({ item }) => isNonActionableType(item.requirement.requirement_type)).map(({ item }) => item.id))
      const hideOutlineHeadings = (nodes: OutlineNode[]): OutlineNode[] => nodes.flatMap((node) => {
        const children = hideOutlineHeadings(node.children)
        return hiddenOutlineIds.has(node.key) ? children : [{ ...node, children }]
      })
      const outlineNodes = buildOutlineTree(outlineItems, maxOutlineDepth)

      return {
        docId,
        items,
        allRows,
        flattened,
        totalForDoc,
        pendingForDoc,
        outlineNodes: hideInformational ? hideOutlineHeadings(outlineNodes) : outlineNodes,
      }
    }
  )

  const visibleRows = docSections.flatMap((section) => section.flattened)
  const pendingRows = visibleRows.filter(({ item }) => needsAttentionFor(item))
  const focus = useReviewFocus({
    cycleId: id, userId: user?.id, focused, requestedItemId,
    items: cycle?.items || [], visibleItems: visibleRows.map(({ item }) => item),
    pendingItems: pendingRows.map(({ item }) => item), itemNeedsSave, updateLocation,
  })
  const selectedRow = visibleRows.find(({ item }) => item.id === focus.selected?.id)
  const selectedIndex = focus.selectedIndex
  const nextPending = visibleRows.find(({ item }) => item.id === focus.nextPending?.id)
  const selectRequirement = focus.select
  const navigationNotice = focus.notice
  const displayedSections = focused
    ? docSections.map((section) => ({ ...section,
        flattened: section.flattened.filter(({ item }) => item.id === selectedRow?.item.id),
      })).filter((section) => section.flattened.length)
    : docSections.map((section) => ({ ...section, flattened: section.flattened.filter(({ depth }) => hierarchyDepth.levels === 'all' || depth < hierarchyDepth.levels) }))

  const visibleActionItemIds = docSections.flatMap((section) =>
    section.flattened
      .filter(({ depth }) => hierarchyDepth.levels === 'all' || depth < hierarchyDepth.levels)
      .map(({ item }) => item)
      .filter((item) => !isNonActionableType(item.requirement.requirement_type))
      .map((item) => item.id)
  )
  const selectedItemIdsList = Object.entries(selectedItemIds)
    .filter(([itemId, selected]) => selected && visibleActionItemIds.includes(itemId))
    .map(([itemId]) => itemId)
  const allVisibleSelected =
    visibleActionItemIds.length > 0 &&
    visibleActionItemIds.every((itemId) => selectedItemIds[itemId])

  const setAllVisibleSelected = (selected: boolean) => {
    setSelectedItemIds((current) => {
      const next = { ...current }
      visibleActionItemIds.forEach((itemId) => {
        if (selected) {
          next[itemId] = true
        } else {
          delete next[itemId]
        }
      })
      return next
    })
  }

  const runBulkMutation = () => {
    if (!selectedItemIdsList.length) {
      toast.error('Select at least one review item.')
      return
    }
    const payload: ReviewItemBulkMutationRequest = {
      item_ids: selectedItemIdsList,
    }
    if (bulkReviewStatus !== 'no_change') {
      payload.review_status = bulkReviewStatus
    }
    if (isAdminOrManager && bulkAssignedReviewerId !== 'no_change') {
      payload.assigned_reviewer_id = bulkAssignedReviewerId || null
    }
    if ((isAdminOrManager || isAssignedReviewer) && bulkResponsibleUserId !== 'no_change') {
      payload.responsible_user_id = bulkResponsibleUserId || null
    }
    if (Object.keys(payload).length === 1) {
      toast.error('Choose a bulk action.')
      return
    }
    bulkMutation.mutate(payload)
  }

  const outlineGroups = docSections.map((section) => ({
    key: section.docId,
    title: docMap.get(section.docId) || 'Requirement set',
    nodes: section.outlineNodes,
  }))


  if (isLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!cycle) {
    return <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-4 text-danger"><p>{getApiErrorMessage(cycleError, 'This assessment could not be loaded.')}</p><Button className="mt-3" onClick={() => retryCycle()}>Try again</Button><Link className="ml-4 underline" to="/review-cycles">Back to assessments</Link></div>
  }

  const contextPath = cycle.change_entry_id ? `/change-management?change=${cycle.change_entry_id}&tab=changes` : cycle.certification_project_id ? `/certification-projects?project=${cycle.certification_project_id}&section=review` : '/review-cycles'
  const contextLabel = cycle.change_entry_id ? 'Back to change' : cycle.certification_project_id ? 'Back to certification project' : 'All requirement assessments'
  return (
    <div data-tour="assessment-detail" className={`workflow-page assessment-detail-page review-document ${focused ? 'review-document-focus' : ''}`}>
      <div className="w-full">
        <div className="review-page-shell bg-surface rounded-xl border border-line px-4 sm:px-5 py-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
            <Link
              to={contextPath}
              className="text-sm text-muted hover:text-ink"
            >
              {contextLabel}
            </Link>
            {focused && <h1 className="mt-1 break-words text-xl font-semibold text-ink">{cycle.name}</h1>}
            </div>
            <div className="lg:hidden"><DropdownMenu ariaLabel="Assessment actions" items={[
              { key: 'gap', label: 'Export gap analysis', onSelect: () => setGapExportOpen(true) },
              ...(isAdminOrManager || user?.role === 'approver' ? [{ key: 'report', label: 'Download report', onSelect: () => setReportOptionsOpen(true) }] : []),
              ...(isAdminOrManager ? [
                { key: 'reminder', label: 'Send reminder', onSelect: () => setShowReminderModal(true), disabled: cycle.status !== 'active' || capabilities?.email?.enabled === false },
                { key: 'archive', label: cycle.status === 'archived' ? 'Unarchive assessment' : 'Archive assessment', onSelect: handleArchiveCycle, disabled: isArchiving || isRestoring || isDeleting },
                ...(!cycle.closed_at && !cycle.snapshot_id && cycle.status !== 'closed' ? [{ key: 'delete', label: 'Delete assessment', onSelect: handleDeleteCycle, disabled: isDeleting || isArchiving || isRestoring, tone: 'destructive' as const }] : []),
              ] : []),
              ...(showJiraUi ? [{ key: 'jira', label: 'Refresh Jira', onSelect: () => syncJiraMutation.mutate(true), disabled: cycle.status !== 'active' || syncJiraMutation.isPending }] : []),
            ]} /></div>
            <div className="hidden flex-wrap items-center gap-2 lg:flex">
              <Button onClick={() => setGapExportOpen(true)}>Export gap analysis</Button>
              {(isAdminOrManager || user?.role === 'approver') && <button
                onClick={() => setReportOptionsOpen(true)}
                className="w-full rounded-md border border-line-strong px-3 py-1 text-sm font-medium text-ink hover:bg-subtle sm:w-auto"
              >
                Download Report
              </button>}
              {isAdminOrManager && (
                <DropdownMenu ariaLabel="Assessment administration" items={[
                  { key: 'reminder', label: capabilities?.email?.enabled === false ? 'Email reminders unavailable' : 'Send Reminder', onSelect: () => setShowReminderModal(true), disabled: cycle.status !== 'active' || capabilities?.email?.enabled === false },
                  { key: 'archive', label: cycle.status === 'archived' ? 'Unarchive assessment' : 'Archive assessment', onSelect: handleArchiveCycle, disabled: isArchiving || isRestoring || isDeleting },
                  ...(!cycle.closed_at && !cycle.snapshot_id && cycle.status !== 'closed' ? [{ key: 'delete', label: 'Delete assessment', onSelect: handleDeleteCycle, disabled: isDeleting || isArchiving || isRestoring, tone: 'destructive' as const }] : []),
                ]} />
              )}
              {showJiraUi && (
                <button
                  onClick={() => syncJiraMutation.mutate(true)}
                  disabled={cycle.status !== 'active' || syncJiraMutation.isPending}
                  className="w-full rounded-md border border-line-strong px-3 py-1 text-sm font-medium text-ink hover:bg-subtle disabled:opacity-50 sm:w-auto"
                >
                  {syncJiraMutation.isPending ? 'Refreshing Jira...' : 'Refresh Jira'}
                </button>
              )}

            </div>
          </div>

          {focused && <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <p className="text-muted">{cycle.progress.completed} of {cycle.progress.total} reviewer decisions complete{cycle.deadline ? ` · Due ${formatDate(cycle.deadline)}` : ''}</p>
            <Button size="sm" onClick={() => updateLocation({ mode: null, item: null })}>Assessment overview</Button>
          </div>}

          <section className="border-b border-line pb-3" hidden={focused}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="mt-1 text-2xl font-semibold text-ink break-words">
                  {cycle.name}
                </h1>
                <p className="mt-1 text-sm text-muted lg:hidden">Evidence drafts save automatically.</p>
                {(cycle.certification_project_id || cycle.change_entry_id) && <p className="mt-2 flex flex-wrap gap-3 text-sm">{cycle.certification_project_id && <Link className="text-accent underline" to={`/certification-projects?project=${cycle.certification_project_id}&section=review`}>Certification project</Link>}{cycle.change_entry_id && <Link className="text-accent underline" to={`/change-management?change=${cycle.change_entry_id}&tab=changes`}>Related change</Link>}<Link className="text-accent underline" to="/review-cycles">All assessments</Link></p>}
                {cycle.description && (
                  <p className="mt-3 max-w-3xl break-words text-muted">
                    {cycle.description}
                  </p>
                )}
                {isAssignedReviewer && (
                  <p className="mt-3 text-sm text-muted">
                    Showing assigned items only.
                  </p>
                )}
              </div>
              <span
                className={`px-3 py-1 text-xs uppercase tracking-wide rounded-full ${
                  cycle.status === 'active'
                    ? 'bg-success-soft text-success'
                    : 'bg-subtle text-ink'
                }`}
              >
                {cycle.status}
              </span>
            </div>

<details open={isDesktop} className="assessment-summary">
              <summary className="mt-3 cursor-pointer text-sm font-semibold text-ink lg:hidden">Assessment status and baseline · {cycle.progress.pending} pending</summary>
              <div className="hidden lg:block"><p className="mt-1 text-sm text-muted">Evidence drafts save automatically. Reviewer decisions and assessment completion remain explicit. Internal submission package approval is a separate decision.</p></div>
	            <div className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm text-muted">
	              <span>
	                <span className="text-faint mr-2 uppercase tracking-wide text-xs">
	                  Jurisdiction
	                </span>
	                {jurisdictionById[cycle.jurisdiction_id]?.name || cycle.jurisdiction_id}
	              </span>
	              <span>
	                <span className="text-faint mr-2 uppercase tracking-wide text-xs">
	                  Scope
	                </span>
                {cycle.scope === 'documents' ? 'Selected requirement sets' : cycle.scope === 'all' ? 'All approved sets' : formatLabel(cycle.scope)}
              </span>
              <span>
                <span className="text-faint mr-2 uppercase tracking-wide text-xs">
                  Deadline
                </span>
                {cycle.deadline ? formatDate(cycle.deadline) : '-'}
              </span>
            </div>

            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-muted">
                <span>Reviewer decisions · {cycle.progress.pending} pending</span>
                <span>
                  {progressPercent}% ({cycle.progress.completed}/{cycle.progress.total})
                </span>
              </div>
              <div className="mt-2 h-1.5 rounded-full bg-line">
                <div
                  className="h-1.5 rounded-full bg-strong transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

      <div hidden={focused}><ReviewCompletion cycle={cycle} canComplete={isAdminOrManager} hasUnsavedChanges={hasUnsavedChanges || hasCommentDrafts || bulkMutation.isPending} onChanged={() => queryClient.invalidateQueries({ queryKey: ['review-cycle', id] })} /></div>
            <ReviewBaselineMigration key={cycle.id} cycle={cycle} docMap={docMap} isAdminOrManager={isAdminOrManager} hidden={focused} hasUnsavedChanges={hasUnsavedChanges || hasCommentDrafts} />
            </details>
          </section>

          <button type="button" className="flex min-h-11 items-center gap-2 text-sm font-semibold text-accent lg:hidden" aria-expanded={mobileFiltersOpen} aria-controls="assessment-tools" onClick={() => setMobileFiltersOpen(value => !value)}>
            {mobileFiltersOpen ? 'Hide filters and view options' : 'Filters and view options'}{hasFilters ? ' · Active filters' : ''}
          </button>
          <div id="assessment-tools" className={mobileFiltersOpen ? '' : 'hidden lg:block'}>
          <div className="review-view-controls review-mode-toolbar border-b border-line py-3">
              <div className="flex flex-wrap gap-2" aria-label="Review view">
                <button type="button" aria-pressed={!focused} onClick={() => updateLocation({ mode: null, item: null })} className={`rounded-md border px-3 py-2 text-sm ${!focused ? 'bg-strong text-white' : 'bg-surface text-ink'}`}>Document view</button>
                <button type="button" aria-pressed={focused} onClick={() => updateLocation({ mode: 'focus', item: requestedItemId })} className={`rounded-md border px-3 py-2 text-sm ${focused ? 'bg-strong text-white' : 'bg-surface text-ink'}`}>Focus on one requirement</button>
              </div>
          </div>
          <section data-tour="assessment-filters" aria-label="Review filters" className="assessment-filter-toolbar space-y-3 border-y border-line py-3">
            <div className="flex flex-wrap items-center gap-2">
              {queueViews.map(view => <button key={view.key} type="button" aria-pressed={view.active}
                onClick={() => toggleQueueView(view)}
                className={`rounded-md border px-3 py-2 text-sm font-medium ${view.active ? 'border-brand bg-brand text-white' : 'border-line-strong bg-surface text-ink hover:bg-subtle'}`}>
                {view.label}
              </button>)}
              <label className="flex items-center gap-2 px-2 py-2 text-sm text-ink">
                <input type="checkbox" checked={hideInformational} onChange={e => updateLocation({ hide_info: e.target.checked ? '1' : null, item: null })} />
                Hide informational
              </label>
              {hasFilters && <button type="button" onClick={clearFilters} className="ml-auto rounded-md px-3 py-2 text-sm font-medium text-accent underline underline-offset-4">Clear filters</button>}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted" aria-live="polite">
              <span>{visibleRows.filter(({ item }) => !isNonActionableType(item.requirement.requirement_type)).length} matching requirements · {visibleRows.filter(({ item }) => isNonActionableType(item.requirement.requirement_type)).length} informational sections · {displayedSections.reduce((total, section) => total + section.flattened.length, 0)} shown</span>
              {attentionOnly && <span>Shows everything still needed to complete this review.</span>}
              {noEvidenceOnly && <span>Shows applicable requirements without a recorded reference or file.</span>}
              {[
                ['owner', responsibleUserFilter, 'Owner'], ['reviewer', assignedReviewerFilter, 'Reviewer'],
                ['review_status', reviewStatusFilter, 'Decision'], ['requirement_status', requirementStatusFilter, 'Status'],
                ['q', search, 'Search'], ['pending', pendingOnly ? 'Pending' : '', 'Decision'], ['no_evidence', noEvidenceOnly ? 'Yes' : '', 'No evidence recorded'],
              ].filter(([, value]) => value && value !== 'all').map(([key, value, label]) => <button key={key} type="button"
                aria-label={`Remove ${label.toLowerCase()} filter`} onClick={() => updateLocation({ [key]: null, item: null })}
                className="rounded-md border border-line px-2 py-1 text-ink hover:bg-subtle">
                {label}: {responsibleOptions.find(u => u.id === value)?.full_name || formatLabel(value)} <span aria-hidden="true">×</span>
              </button>)}
            </div>
          </section>
          <details className="border-b border-line py-2">
            <summary className="cursor-pointer text-sm font-medium text-ink">More filters{!focused && ' and bulk actions'}</summary>
          <section>
            <h2 className="sr-only">Filters</h2>
            <div
              className={`mt-4 grid grid-cols-1 gap-4 rounded-xl border border-line/70 bg-canvas/70 p-4 ${
                isAdminOrManager ? 'md:grid-cols-2 xl:grid-cols-6' : 'md:grid-cols-2 xl:grid-cols-4'
              }`}
            >
          <div>
            <label
              htmlFor="review-cycle-filter-search"
              className="block text-xs uppercase tracking-wide text-muted mb-1"
            >
              Search
            </label>
            <input
              id="review-cycle-filter-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search reference, title, text..."
              className="w-full px-3 py-2 border border-line-strong rounded-md bg-surface focus:outline-none focus:ring-2 focus:ring-line-strong"
            />
          </div>
          <div>
            <label
              htmlFor="review-cycle-filter-review-status"
              className="block text-xs uppercase tracking-wide text-muted mb-1"
            >
              Review Status
            </label>
            <select
              id="review-cycle-filter-review-status"
              value={reviewStatusFilter}
              onChange={(e) => setReviewStatusFilter(e.target.value)}
              className="w-full px-3 py-2 border border-line-strong rounded-md bg-surface focus:outline-none focus:ring-2 focus:ring-line-strong"
            >
              <option value="all">All</option>
              {reviewStatuses.map((status) => (
                <option key={status} value={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="review-cycle-filter-requirement-status"
              className="block text-xs uppercase tracking-wide text-muted mb-1"
            >
              Requirement Status
            </label>
            <select
              id="review-cycle-filter-requirement-status"
              value={requirementStatusFilter}
              onChange={(e) => setRequirementStatusFilter(e.target.value)}
              className="w-full px-3 py-2 border border-line-strong rounded-md bg-surface focus:outline-none focus:ring-2 focus:ring-line-strong"
            >
              <option value="all">All</option>
              {requirementStatuses.map((status) => (
                <option key={status} value={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </div>
          {isAdminOrManager && (
            <div>
              <label
                htmlFor="review-cycle-filter-responsible-user"
                className="block text-xs uppercase tracking-wide text-muted mb-1"
              >
                Responsible for Requirement
              </label>
              <select
                id="review-cycle-filter-responsible-user"
                value={responsibleUserFilter}
                onChange={(e) => setResponsibleUserFilter(e.target.value)}
                className="w-full px-3 py-2 border border-line-strong rounded-md bg-surface focus:outline-none focus:ring-2 focus:ring-line-strong"
              >
                <option value="all">All</option>
                <option value="unassigned">Unassigned</option>
                {responsibleOptions.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
            </div>
          )}
          {isAdminOrManager && (
            <div>
              <label
                htmlFor="review-cycle-filter-assigned-reviewer"
                className="block text-xs uppercase tracking-wide text-muted mb-1"
              >
                Assigned Reviewer
              </label>
              <select
                id="review-cycle-filter-assigned-reviewer"
                value={assignedReviewerFilter}
                onChange={(e) => setAssignedReviewerFilter(e.target.value)}
                className="w-full px-3 py-2 border border-line-strong rounded-md bg-surface focus:outline-none focus:ring-2 focus:ring-line-strong"
              >
                <option value="all">All</option>
                <option value="unassigned">Unassigned</option>
                {responsibleOptions.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex items-end">
            <label
              htmlFor="review-cycle-filter-pending-only"
              className="flex items-center gap-2 text-sm text-ink"
            >
              <input
                id="review-cycle-filter-pending-only"
                type="checkbox"
                checked={pendingOnly}
                onChange={(e) => setPendingOnly(e.target.checked)}
              />
              Show pending only
            </label>
          </div>
        </div>
      </section>

      <section className="border-t border-line py-4" hidden={focused}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink">
              Bulk actions
            </h3>
            <p className="mt-1 text-sm text-muted">
              {selectedItemIdsList.length} selected of {visibleActionItemIds.length} visible
            </p>
          </div>

        </div>
        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-5">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              disabled={visibleActionItemIds.length === 0}
              onChange={(event) => setAllVisibleSelected(event.target.checked)}
            />
            Select visible
          </label>
          <select
            aria-label="Bulk review status"
            value={bulkReviewStatus}
            onChange={(event) => setBulkReviewStatus(event.target.value)}
            className="rounded-md border border-line-strong px-3 py-2 text-sm"
          >
            <option value="no_change">Keep review status</option>
            {reviewStatuses.map((status) => (
              <option key={status} value={status}>
                {formatLabel(status)}
              </option>
            ))}
          </select>
          {isAdminOrManager ? (
            <select
              value={bulkAssignedReviewerId}
              onChange={(event) => setBulkAssignedReviewerId(event.target.value)}
              className="rounded-md border border-line-strong px-3 py-2 text-sm"
            >
              <option value="no_change">Keep reviewer</option>
              <option value="">Unassign reviewer</option>
              {responsibleOptions.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
          ) : null}
          {isAdminOrManager || isAssignedReviewer ? (
            <select
              value={bulkResponsibleUserId}
              onChange={(event) => setBulkResponsibleUserId(event.target.value)}
              className="rounded-md border border-line-strong px-3 py-2 text-sm"
            >
              <option value="no_change">Keep owner</option>
              <option value="">Unassign owner</option>
              {responsibleOptions.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
          ) : null}
          <button
            type="button"
            disabled={cycle.status !== 'active' || bulkMutation.isPending || selectedItemIdsList.length === 0}
            onClick={runBulkMutation}
            className="rounded-md bg-strong px-3 py-2 text-sm font-medium text-white hover:bg-strong disabled:opacity-50"
          >
            {bulkMutation.isPending ? 'Applying...' : 'Apply bulk action'}
          </button>
        </div>
      </section>

          </details>
          </div>
          {docSections.length > 0 && visibleRows.length === 0 && <p role="status" className="py-4 text-sm text-muted">No requirements match these filters. <button type="button" className="underline" onClick={clearFilters}>Clear filters</button></p>}
          {cycle.status !== 'active' && <p role="status" className="rounded-md border border-line-strong bg-canvas p-3 text-sm text-ink">This {cycle.status} review is read-only. Its recorded work remains available below.</p>}
          <div id="review-workspace" className="scroll-mt-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
              {focused && selectedRow && <div className="flex flex-wrap items-center gap-2">
                <span role="status" className="text-sm text-muted">{selectedIndex + 1} of {visibleRows.length}</span>
                <Button type="button" title="Alt+Left Arrow" disabled={selectedIndex <= 0} onClick={() => selectRequirement(visibleRows[selectedIndex - 1].item.id)} className="rounded-md border px-3 py-2 text-sm disabled:opacity-50">Previous</Button>
                <Button type="button" title="Alt+Right Arrow" disabled={selectedIndex >= visibleRows.length - 1} onClick={() => selectRequirement(visibleRows[selectedIndex + 1].item.id)} className="rounded-md border px-3 py-2 text-sm disabled:opacity-50">Next</Button>
              </div>}
              <Button variant="primary" type="button" title="Alt+N" disabled={!nextPending} onClick={() => nextPending && selectRequirement(nextPending.item.id)} className="shrink-0">Next needing attention</Button>
            </div>
            {focused && requestedItemId && !visibleRows.some(({ item }) => item.id === requestedItemId) && <p role="status" className="mt-2 text-sm text-warning">That requirement is unavailable in this view. Showing the next available requirement. <button type="button" className="underline" onClick={clearFilters}>Clear filters</button></p>}
            {!focused && visibleRows.length > 0 && displayedSections.every((section) => section.flattened.length === 0) && <p role="status" className="mt-2 text-sm text-muted">No requirements at this depth. <button type="button" className="text-accent underline" onClick={() => hierarchyDepth.changeLevels('all')}>Show all levels</button></p>}
            {navigationNotice && <p role="alert" className="mt-2 text-sm text-danger">{navigationNotice}</p>}
          </div>

		          {docSections.length === 0 && (
		            <div className="text-center py-8 text-muted">No assessment items found.</div>
		          )}

	          {docSections.length > 0 &&
	            (() => {
	              const sidebar = (
	                <div className="sticky top-36 max-h-[calc(100dvh-10rem)] overflow-auto">
	                  <RequirementsOutline
	                    groups={outlineGroups}
                        levels={hierarchyDepth.levels}
                        onLevelsChange={hierarchyDepth.changeLevels}
                        maxLevels={Math.max(1, ...docSections.flatMap((section) => section.allRows.map(({ depth }) => depth + 1)))}
                        selectedTargetId={focused && selectedRow ? `review-item-${selectedRow.item.id}` : undefined}
	                    onNavigate={(targetId) => {
                          if (focused) { selectRequirement(targetId.replace('review-item-', '')); return }
                        const target = visibleRows.find(({ item }) => `review-item-${item.id}` === targetId)
                        if (target && hierarchyDepth.levels !== 'all' && target.depth >= hierarchyDepth.levels) {
                          hierarchyDepth.changeLevels(target.depth + 1)
                          requestAnimationFrame(() => document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
                          return
                        }
	                      document.getElementById(targetId)?.scrollIntoView({
	                        behavior: 'smooth',
	                        block: 'start',
	                      })
	                    }}
	                  />
	                </div>
	              )

	              const main = (
	                <div className="min-w-0">
	                  {displayedSections.map((section, docIndex) => {
	                    const isLast = docIndex === docSections.length - 1
	                    return (
	                      <section
	                        key={section.docId}
	                        className={`pb-10 ${isLast ? '' : 'border-b border-line/70'}`}
	                      >
	                        <div className="flex flex-wrap items-start justify-between gap-3">
	                          <div>

	                            {focused ? (
	                              <p className="text-sm font-medium text-muted">{docMap.get(section.docId) || 'Requirement set'}</p>
	                            ) : (
	                              <h2 className="mt-2 text-2xl font-semibold text-ink">{docMap.get(section.docId) || 'Requirement set'}</h2>
	                            )}
	                            {!focused && <p className="mt-1 text-sm text-muted">
	                              {section.pendingForDoc} pending of {section.totalForDoc} applicable requirements
	                            </p>}
	                          </div>
	                          {!focused && <div className="text-xs text-faint uppercase tracking-wide">
	                            Showing {section.flattened.length} {section.flattened.length === 1 ? 'section' : 'sections'}
	                          </div>}
	                        </div>

	                        {section.flattened.length === 0 ? (
	                          <div className="text-sm text-muted">
	                            No matching requirements.
	                          </div>
	                        ) : (
	                          <div className="review-items">
	                            {section.flattened.map(({ item, depth }) => {
	                  const textPlain = stripHtml(item.requirement.text || '')
	                  const baseHeadingText = [item.requirement.reference_id, item.requirement.title]
	                    .filter(Boolean)
	                    .join(' ')
	                    .trim()
                  const showBody =
                    textPlain &&
                    (!item.requirement.title || item.requirement.title !== textPlain)
                  const headingIndex = getHeadingIndex(item.requirement.reference_id, depth)
                  const indentPx = focused ? 0 : getIndentPx(item.requirement.reference_id, depth)
                  const HeadingTag = headingTags[headingIndex]
                  const headingClass = `${headingSizes[headingIndex]} font-semibold text-ink leading-snug tracking-tight`
                  const AssessmentContainer = 'section'
                  const AssessmentHeading = 'h3'

	                  if (isNonActionableType(item.requirement.requirement_type)) {
	                    const informationalHeadingText = baseHeadingText
	                    const informationalShowBody = showBody
	                    return (
	                      <div
	                        key={item.id}
	                        id={`review-item-${item.id}`}
	                        className="review-section-heading"
	                        style={{ paddingLeft: indentPx }}
	                      >
                        <HeadingTag className={headingClass}>
                          {informationalHeadingText}

                        </HeadingTag>
                        {informationalShowBody && (
                          <div
                            className="mt-2 text-sm text-muted leading-relaxed space-y-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1"
                            dangerouslySetInnerHTML={{
                              __html: normalizeRichText(item.requirement.text || ''),
                            }}
                          />
                        )}
                      </div>
                    )
                  }

                  const draft = getDraft(item)
                  const jiraKeyDraft = jiraKeyDrafts[item.id] ?? item.jira_issue_key ?? ''
                  const commentDraft = commentDrafts[item.id] || ''
                  const saveStatus = saveStatusByItem[item.id]
                  const commentCount = item.comments?.length || 0
                  const hasLinkedJira = Boolean((item.jira_issue_key || '').trim())
                  const hasJiraData = Boolean(
                    item.jira_issue_url ||
                      item.jira_status ||
                      item.jira_summary ||
                      item.jira_assignee ||
                      item.jira_priority ||
                      item.jira_updated_at ||
                      item.jira_synced_at ||
                      item.jira_sync_error
                  )
                  const canAssignReviewer = isAdminOrManager
                  const canAssignResponsible = isAdminOrManager || isAssignedReviewer
                  const needsAttention = needsAttentionFor(item)
                  const saveIndicator = saveStatus || itemNeedsSave(item) ? (
                    <DraftSaveStatus state={saveStatus === 'error' || saveStatus === 'saving' ? saveStatus : itemNeedsSave(item) ? 'dirty' : 'saved'} onRetry={() => retryItem(item)} />
                  ) : null
                  const requirementStatusSelect = (
                    <select
                      data-testid={`requirement-status-select-${item.id}`}
                      aria-label={`Requirement status for ${item.requirement.reference_id}`}
                      disabled={cycle.status !== 'active'}
                      value={draft.requirement_status}
                      onChange={(e) => changeStatus(item, 'requirement_status', e.target.value)}
                      className="h-11 w-full rounded-md border border-line-strong px-3 py-2 focus:outline-none focus:ring-2 focus:ring-line-strong"
                    >
                      {requirementStatuses.map((status) => (
                        <option key={status} value={status}>
                          {formatLabel(status)}
                        </option>
                      ))}
                    </select>
                  )

		                  return (
		                    <div
		                      key={item.id}
		                      id={`review-item-${item.id}`}
		                      className="review-record"
		                    >
                      <header className="review-record-header">
                        <HeadingTag className="review-record-title">{baseHeadingText}</HeadingTag>
                        <div className="review-record-statuses">
                          <span className="review-status" data-status={draft.requirement_status}>{formatLabel(draft.requirement_status)}</span>
                          <span className="review-status" data-status={draft.review_status}>{formatLabel(draft.review_status)}</span>
                        </div>
                        {!focused && <label className="review-record-select">
                        <input
                          type="checkbox"
                          checked={Boolean(selectedItemIds[item.id])}
                          onChange={(event) =>
                            setSelectedItemIds((current) => {
                              const next = { ...current }
                              if (event.target.checked) {
                                next[item.id] = true
                              } else {
                                delete next[item.id]
                              }
                              return next
                            })
                          } disabled={cycle.status !== 'active'}
                        />
                        <span>Select for bulk action</span>
                        </label>}
                      </header>
                      <div className="review-item-layout">
                        <div className="review-requirement min-w-0">
                          {showBody && (
                            <div
                              className="text-sm text-ink mt-2 leading-relaxed space-y-2 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-1"
                              dangerouslySetInnerHTML={{
                                __html: normalizeRichText(item.requirement.text || ''),
                              }}
                            />
                          )}
                        </div>

                        <AssessmentContainer className="review-assessment min-w-0" aria-label={`Assessment and evidence for ${item.requirement.reference_id}`}>
                          <AssessmentHeading className="review-assessment-heading" aria-label={`Assessment and evidence for ${item.requirement.reference_id}`}>
                            <span className="font-semibold">Assessment and evidence</span>
                            <span className="ml-2">{saveIndicator}</span>
                            <CopyButton value={`${item.requirement.reference_id}\n${stripHtml(item.requirement.text || '')}\n${draft.review_evidence}`} label="Copy requirement and evidence" />
                          </AssessmentHeading>

		                            <div className="mt-3 space-y-3">
                              {needsAttention && attentionReasons.get(item.id)?.length && <div className="review-attention">
                                <p className="font-semibold">Needs attention</p>
                                <ul>{attentionReasons.get(item.id)?.map(reason => <li key={reason}>{reason}</li>)}</ul>
                              </div>}
                              {noEvidenceRecordedFor(item, draft.review_evidence, draft.requirement_status) && <p className="text-xs text-muted">No evidence recorded in CAP</p>}
                              {item.evidence_changed_since_review && <p className="text-xs text-muted">Evidence changed since the last review; the decision has not been updated.</p>}
		                              <div className={`grid grid-cols-1 gap-3 review-assessment-fields`}>
	                                <div
	                                  className={`min-w-0 space-y-1 ${!canAssignResponsible ? 'sm:col-span-2' : ''}`}
	                                >
	                                  <label className="block review-field-label">
	                                    Requirement status
	                                  </label>
	                                  {requirementStatusSelect}
	                                </div>
	                                {canAssignResponsible && (
	                                  <div className="min-w-0 space-y-1">
	                                    <label className="block review-field-label">
	                                      Responsible owner
	                                    </label>
	                                    <div className="grid grid-cols-[1fr_auto] items-center gap-2">
	                                      <select
	                                        aria-label={`Responsible owner for ${item.requirement.reference_id}`}
                                        value={item.responsible_user_id || ''}
	                                        onChange={(e) =>
	                                          assignMutation.mutate({
	                                            itemId: item.id,
	                                            responsible_user_id: e.target.value || null,
	                                          })
	                                        }
	                                        className="h-11 w-full rounded-md border border-line-strong px-3 py-2 focus:outline-none focus:ring-2 focus:ring-line-strong" disabled={cycle.status !== 'active'}
	                                      >
	                                        <option value="">Unassigned</option>
	                                        {responsibleOptions.map((u) => (
	                                          <option key={u.id} value={u.id}>
	                                            {u.full_name || u.email}
	                                          </option>
	                                        ))}
	                                      </select>
	                                      <IconButton
	                                        type="button"
	                                        title="Assign to me"
	                                        aria-label="Assign to me"
	                                        disabled={cycle.status !== 'active' || (!user ||
	                                          item.responsible_user_id === user.id ||
	                                          assignMutation.isPending ||
	                                          (isAssignedReviewer &&
	                                            item.assigned_reviewer_id !== user?.id))}
	                                        onClick={() => {
	                                          if (!user) return
	                                          assignMutation.mutate({
	                                            itemId: item.id,
	                                            responsible_user_id: user.id,
	                                          })
	                                        }}
	                                        className="h-11 w-11 border-line-strong"
	                                      >
	                                        <svg
	                                          viewBox="0 0 24 24"
	                                          fill="none"
	                                          stroke="currentColor"
	                                          strokeWidth="2"
	                                          strokeLinecap="round"
	                                          strokeLinejoin="round"
	                                          className="h-4 w-4"
	                                          aria-hidden="true"
	                                        >
	                                          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
	                                          <circle cx="9" cy="7" r="4" />
	                                          <path d="M19 8v6" />
	                                          <path d="M22 11h-6" />
	                                        </svg>
	                                      </IconButton>
	                                    </div>
	                                  </div>
	                                )}
	                              </div>
                          <div className={`grid grid-cols-1 gap-3 review-assessment-fields`}>
                            <div
                              className={`min-w-0 space-y-1 ${!canAssignReviewer ? 'sm:col-span-2' : ''}`}
                            >
                              <label className="block review-field-label">
                                Reviewer decision
                              </label>
                              <select
                                aria-label={`Reviewer decision for ${item.requirement.reference_id}`}
                                value={draft.review_status}
                                onChange={(e) => changeStatus(item, 'review_status', e.target.value)}
                                className="h-11 w-full rounded-md border border-line-strong px-3 py-2 focus:outline-none focus:ring-2 focus:ring-line-strong" disabled={cycle.status !== 'active'}
                              >
                                {reviewStatuses.map((status) => (
                                  <option key={status} value={status}>
                                    {formatLabel(status)}
                                  </option>
                                ))}
                              </select>
                            </div>
                            {canAssignReviewer && (
                              <div className="min-w-0 space-y-1">
                                <label className="block review-field-label">
                                  Assigned reviewer
                                </label>
                                <div className="grid grid-cols-[1fr_auto] items-center gap-2">
                                  <select
                                    aria-label={`Assigned reviewer for ${item.requirement.reference_id}`}
                                    value={item.assigned_reviewer_id || ''}
                                    onChange={(e) =>
                                      assignMutation.mutate({
                                        itemId: item.id,
                                        assigned_reviewer_id: e.target.value || null,
                                      })
                                    }
                                    className="h-11 w-full rounded-md border border-line-strong px-3 py-2 focus:outline-none focus:ring-2 focus:ring-line-strong" disabled={cycle.status !== 'active'}
                                  >
                                    <option value="">Unassigned</option>
                                    {responsibleOptions.map((u) => (
                                      <option key={u.id} value={u.id}>
                                        {u.full_name || u.email}
                                      </option>
                                    ))}
                                  </select>
                                  <IconButton
                                    type="button"
                                    title="Assign to me"
                                    aria-label="Assign to me"
                                    disabled={cycle.status !== 'active' || (!user ||
                                      item.assigned_reviewer_id === user.id ||
                                      assignMutation.isPending)}
                                    onClick={() => {
                                      if (!user) return
                                      assignMutation.mutate({
                                        itemId: item.id,
                                        assigned_reviewer_id: user.id,
                                      })
                                    }}
                                    className="h-11 w-11 border-line-strong"
                                  >
                                    <svg
                                      viewBox="0 0 24 24"
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="2"
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      className="h-4 w-4"
                                      aria-hidden="true"
                                    >
                                      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                                      <circle cx="9" cy="7" r="4" />
                                      <path d="M19 8v6" />
                                      <path d="M22 11h-6" />
                                    </svg>
                                  </IconButton>
                                </div>
                              </div>
                            )}
                          </div>
                              <ReviewEvidenceEditor item={item} cycleId={id || ''} active={cycle.status === 'active'} draft={draft} changeEvidence={changeEvidence} saveEvidence={saveEvidence} files={evidenceFiles} />
                          <div className="space-y-3">
                          {showJiraUi && (
                            <div className="space-y-1">
                              <label className="block review-field-label">
                                Jira Issue Key
                              </label>
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="w-full md:max-w-[14rem]">
                                  <input
                                    value={jiraKeyDraft}
                                    onChange={(e) =>
                                      setJiraKeyDrafts((prev) => ({
                                        ...prev,
                                        [item.id]: e.target.value.toUpperCase(),
                                      }))
                                    }
                                    onBlur={() => {
                                      if (!canEditJira) return
                                      const nextKey = jiraKeyDraft.trim().toUpperCase()
                                      const currentKey = (item.jira_issue_key || '')
                                        .trim()
                                        .toUpperCase()
                                      if (nextKey === currentKey) return
                                      updateJiraMutation.mutate({
                                        itemId: item.id,
                                        jira_issue_key: nextKey || null,
                                      })
                                    }}
                                    readOnly={cycle.status !== 'active' || !canEditJira}
                                    className={`h-11 w-full rounded-md border border-line-strong px-3 py-2 font-mono uppercase tracking-wide focus:outline-none focus:ring-2 focus:ring-line-strong ${
                                      canEditJira ? '' : 'bg-subtle text-muted'
                                    }`}
                                    placeholder="PROJ-123" disabled={cycle.status !== 'active'}
                                  />
                                </div>
                                <span
                                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${
                                    !hasLinkedJira
                                      ? 'bg-subtle text-muted'
                                      : item.jira_sync_error
                                        ? 'bg-danger-soft text-danger'
                                        : item.jira_synced_at
                                          ? 'bg-success-soft text-success'
                                          : 'bg-warning-soft text-warning'
                                  }`}
                                >
                                  {!hasLinkedJira
                                    ? 'Not linked'
                                    : item.jira_sync_error
                                      ? 'Sync failed'
                                      : item.jira_synced_at
                                        ? 'Synced'
                                        : 'Not synced'}
                                </span>
                              </div>
                              <div className="flex flex-wrap items-center gap-3 text-xs">
                                {savingJiraItemId === item.id && (
                                  <span className="text-muted">Saving Jira key…</span>
                                )}
                                {item.jira_issue_url && (
                                  <a
                                    href={item.jira_issue_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-info hover:text-info"
                                  >
                                    Open in Jira
                                  </a>
                                )}
                              </div>
                              {hasLinkedJira && hasJiraData && (
                                <div className="space-y-2 rounded-md border border-line bg-surface px-3 py-2">
                                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-muted">
                                    <dt className="font-medium text-ink">Status</dt>
                                    <dd className="break-words">{item.jira_status || '-'}</dd>
                                    <dt className="font-medium text-ink">Summary</dt>
                                    <dd className="break-words">{item.jira_summary || '-'}</dd>
                                    <dt className="font-medium text-ink">Assignee</dt>
                                    <dd className="break-words">{item.jira_assignee || '-'}</dd>
                                    <dt className="font-medium text-ink">Priority</dt>
                                    <dd className="break-words">{item.jira_priority || '-'}</dd>
                                    <dt className="font-medium text-ink">Updated</dt>
                                    <dd className="break-words">
                                      {item.jira_updated_at
                                        ? formatDateTime(item.jira_updated_at)
                                        : '-'}
                                    </dd>
                                    <dt className="font-medium text-ink">Last synced</dt>
                                    <dd className="break-words">
                                      {item.jira_synced_at
                                        ? formatDateTime(item.jira_synced_at)
                                        : '-'}
                                    </dd>
                                  </dl>
                                  {item.jira_sync_error && (
                                    <div className="text-xs text-danger">{item.jira_sync_error}</div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                          <details className="review-discussion">
                            <summary>
                              <span>Comments <span className="review-comment-count">{commentCount}</span></span>
                              <span className="review-discussion-hint">View or add a comment</span>
                            </summary>
                            <div className="review-discussion-body">
                            <div>
                              {item.comments?.length ? (
                                <div className="max-h-36 overflow-y-auto rounded-md border border-line bg-surface">
                                  <div className="divide-y divide-line">
                                    {item.comments.map((comment) => {
                                      const isEditing =
                                        editingComment?.commentId === comment.id
                                      return (
                                        <div key={comment.id} className="px-2.5 py-1.5 text-xs">
                                          <div className="flex flex-wrap items-start justify-between gap-2">
                                            <div className="break-words text-[11px] text-muted">
                                              <span className="font-medium text-ink">
                                                {comment.author_name}
                                              </span>
                                              <span className="mx-1">•</span>
                                              <span>
                                                {formatDateTime(comment.created_at)}
                                              </span>
                                              {comment.updated_at && (
                                                <span className="ml-2 text-faint">
                                                  Edited
                                                </span>
                                              )}
                                            </div>
                                            {comment.can_edit && !isEditing && (
                                              <button
                                                type="button"
                                                onClick={() => {
                                                  setEditingComment({
                                                    itemId: item.id,
                                                    commentId: comment.id,
                                                  })
                                                  setEditingCommentBody(comment.body)
                                                  setEditMentionState(null)
                                                }}
                                                className="text-[11px] text-ink hover:text-ink" disabled={cycle.status !== 'active'}
                                              >
                                                Edit
                                              </button>
                                            )}
                                          </div>
                                          {isEditing ? (
                                            <div className="mt-2 space-y-2">
                                              <textarea
                                                value={editingCommentBody}
                                                onChange={(e) => {
                                                  const value = e.target.value
                                                  setEditingCommentBody(value)
                                                  const state = getMentionState(
                                                    value,
                                                    e.target.selectionStart
                                                  )
                                                  setEditMentionState(state)
                                                }}
                                                ref={editTextareaRef}
                                                rows={2}
                                                className="w-full rounded-md border border-line-strong px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-line-strong" disabled={cycle.status !== 'active'}
                                              />
                                              {editMentionState?.active &&
                                                getMentionSuggestions(editMentionState.query)
                                                  .length > 0 && (
                                                  <div className="rounded-md border border-line bg-surface shadow-sm">
                                                    {getMentionSuggestions(
                                                      editMentionState.query
                                                    ).map((mention) => (
                                                      <button
                                                        key={mention.id}
                                                        type="button"
                                                        onMouseDown={(event) => {
                                                          event.preventDefault()
                                                          applyMentionToEdit(mention)
                                                        }}
                                                        className="w-full px-3 py-2 text-left text-xs hover:bg-canvas" disabled={cycle.status !== 'active'}
                                                      >
                                                        <div className="break-words text-ink">
                                                          {mention.full_name || mention.email}
                                                        </div>
                                                      </button>
                                                    ))}
                                                  </div>
                                                )}
                                              <div className="flex flex-wrap items-center gap-2">
                                                <button
                                                  type="button"
                                                  onClick={() => {
                                                    if (!editingComment) return
                                                    const nextBody =
                                                      editingCommentBody.trim()
                                                    if (!nextBody) return
                                                    editCommentMutation.mutate({
                                                      itemId: editingComment.itemId,
                                                      commentId: editingComment.commentId,
                                                      body: nextBody,
                                                    })
                                                  }}
                                                  disabled={cycle.status !== 'active' || (!editingCommentBody.trim() ||
                                                    savingCommentId === comment.id)}
                                                  className="px-3 py-1.5 bg-strong text-white rounded-md text-xs hover:bg-strong disabled:opacity-50"
                                                >
                                                  {savingCommentId === comment.id
                                                    ? 'Saving...'
                                                    : 'Save'}
                                                </button>
                                                <button
                                                  type="button"
                                                  onClick={() => {
                                                    setEditingComment(null)
                                                    setEditingCommentBody('')
                                                    setEditMentionState(null)
                                                  }}
                                                  className="px-3 py-1.5 text-xs text-muted hover:text-ink" disabled={cycle.status !== 'active'}
                                                >
                                                  Cancel
                                                </button>
                                              </div>
                                            </div>
                                          ) : (
                                            <p className="mt-1 whitespace-pre-wrap text-xs text-ink">
                                              {renderCommentBody(comment.body)}
                                            </p>
                                          )}
                                          {(item.evidence_files || []).filter(file => file.comment_id === comment.id).map(file => (
                                            <button
                                              key={file.id}
                                              type="button"
                                              className="mt-1 block break-all text-left text-xs text-info underline"
                                              onClick={() => {
                                                void evidenceFiles.downloadFile(item.id, file.id, file.filename)
                                                  .catch(error => notifyApiError(toast, error, 'Attachment download failed'))
                                              }}
                                            >
                                              {file.filename}
                                            </button>
                                          ))}
                                        </div>
                                      )
                                    })}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-muted">No comments yet.</p>
                              )}
                            </div>
                            <div>
                              <label className="block review-field-label mb-1">
                                Add a comment
                              </label>
                              <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto] md:items-end">
                                <textarea
                                  value={commentDraft}
                                  onChange={(e) => {
                                    const value = e.target.value
                                    setCommentDrafts((prev) => ({
                                      ...prev,
                                      [item.id]: value,
                                    }))
                                    const state = getMentionState(value, e.target.selectionStart)
                                    setMentionStates((prev) => {
                                      const next = { ...prev }
                                      if (state) {
                                        next[item.id] = state
                                      } else {
                                        delete next[item.id]
                                      }
                                      return next
                                    })
                                  }}
                                  ref={(el) => {
                                    commentInputRefs.current[item.id] = el
                                  }}
                                  rows={1}
                                  className="max-h-24 min-h-[2.5rem] w-full rounded-md border border-line-strong px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-line-strong"
                                  aria-label={`Comment on ${item.requirement.reference_id}`}
                                  placeholder="Write a comment..." disabled={cycle.status !== 'active' || postingCommentItemId === item.id}
                                />
                                <div className="flex justify-end md:justify-start">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const body = commentDraft.trim()
                                      if (!body) return
                                      createCommentMutation.mutate({
                                        itemId: item.id,
                                        body,
                                        files: commentFiles[item.id] || [],
                                      })
                                    }}
                                    disabled={cycle.status !== 'active' || (!commentDraft.trim() ||
                                      postingCommentItemId === item.id)}
                                    className="w-full md:w-auto px-3 py-1.5 bg-strong text-white rounded-md text-xs hover:bg-strong disabled:opacity-50"
                                  >
                                    {postingCommentItemId === item.id
                                      ? 'Posting...'
                                      : 'Post Comment'}
                                  </button>
                                </div>
                              </div>
                              <div className="mt-2 space-y-1">
                                <label className="block text-xs text-muted">
                                  Attach files (JPG, PNG, PDF, DOCX, TXT, MD; up to 10)
                                  <input
                                    type="file"
                                    multiple
                                    accept=".jpg,.jpeg,.png,.pdf,.docx,.txt,.md"
                                    aria-label={`Attach files to comment on ${item.requirement.reference_id}`}
                                    className="mt-1 block w-full text-xs"
                                    disabled={cycle.status !== 'active' || postingCommentItemId === item.id}
                                    onChange={event => {
                                      const selected = Array.from(event.target.files || [])
                                      event.target.value = ''
                                      const next = [...(commentFiles[item.id] || []), ...selected]
                                      if (next.length > 10) {
                                        toast.error('Attach at most 10 files per comment')
                                        return
                                      }
                                      if (selected.some(file => !/\.(jpe?g|png|pdf|docx|txt|md)$/i.test(file.name))) {
                                        toast.error('Supported attachments: JPG, PNG, PDF, DOCX, TXT and MD')
                                        return
                                      }
                                      setCommentFiles(prev => ({ ...prev, [item.id]: next }))
                                    }}
                                  />
                                </label>
                                {(commentFiles[item.id] || []).map((file, index) => (
                                  <div key={`${file.name}-${index}`} className="flex items-center gap-2 text-xs">
                                    <span className="break-all">{file.name}</span>
                                    <button
                                      type="button"
                                      aria-label={`Remove attachment ${file.name}`}
                                      className="text-muted underline"
                                      disabled={postingCommentItemId === item.id}
                                      onClick={() => setCommentFiles(prev => ({
                                        ...prev,
                                        [item.id]: (prev[item.id] || []).filter((_, position) => position !== index),
                                      }))}
                                    >Remove</button>
                                  </div>
                                ))}
                              </div>
                              {mentionStates[item.id]?.active &&
                                getMentionSuggestions(mentionStates[item.id].query).length >
                                  0 && (
                                  <div className="mt-2 rounded-md border border-line bg-surface shadow-sm">
                                    {getMentionSuggestions(
                                      mentionStates[item.id].query
                                    ).map((mention) => (
                                      <button
                                        key={mention.id}
                                        type="button"
                                        onMouseDown={(event) => {
                                          event.preventDefault()
                                          applyMentionToDraft(item.id, mention)
                                        }}
                                        className="w-full px-3 py-2 text-left text-sm hover:bg-canvas" disabled={cycle.status !== 'active'}
                                      >
                                        <div className="break-words text-ink">
                                          {mention.full_name || mention.email}
                                        </div>
                                      </button>
                                    ))}
                                  </div>
                                )}
                              <p className="mt-1 text-xs text-faint">
                                Mention someone with @name to notify them.
                              </p>
                            </div>
                            </div>
                          </details>
	                          <div className="review-audit-note">
	                            {item.reviewer_name ? `Last reviewed by ${item.reviewer_name}: ` : 'Last reviewed: '}
	                            {item.reviewed_at
	                              ? formatDate(item.reviewed_at)
	                              : '—'}
	                          </div>
	                          </div>
	                          </div>

                        </AssessmentContainer>
                      </div>
                    </div>
                  )
	                          })}
	                        </div>
	                      )}
	                    </section>
	                      )
	                    })}
	                  </div>
	                )

	              return (
	                <div className="mt-4">
	                  {isDesktop ? (
	                    <ResizableSplitView
	                      storageKey="review-cycle:outline"
	                      defaultSidebarWidth={220}
	                      minSidebarWidth={220}
	                      maxSidebarWidth={520}
	                      sidebar={sidebar}
	                      main={main}
	                      className="gap-3"
	                      handleClassName="relative cursor-col-resize"
	                      collapseLabel="Collapse outline"
	                      expandLabel="Expand outline"
	                    />
	                  ) : (
                      <div className="space-y-4">
                        <details className="rounded-lg border border-line p-3"><summary className="cursor-pointer text-sm font-medium">Requirement outline</summary>{sidebar}</details>
                        {main}
                      </div>
	                  )}
	                </div>
	              )
	            })()}

      {showReminderModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-lg bg-surface p-4 sm:p-6">
            <h2 className="text-lg font-semibold mb-2">Send assessment reminders</h2>
            <p className="text-sm text-muted mb-4">
              Select which review statuses should be included in the reminder email.
            </p>
            <div className="space-y-2 mb-6">
              {reviewStatuses.map((status) => (
                <label key={status} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={reminderStatuses.includes(status)}
                    onChange={(e) => {
                      setReminderStatuses((prev) =>
                        e.target.checked
                          ? [...prev, status]
                          : prev.filter((value) => value !== status)
                      )
                    }}
                  />
                  {formatLabel(status)}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowReminderModal(false)}
                className="px-4 py-2 text-ink hover:bg-subtle rounded-md"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={reminderStatuses.length === 0 || remindMutation.isPending}
                onClick={() => remindMutation.mutate(reminderStatuses)}
                className="px-4 py-2 bg-strong text-white rounded-md hover:bg-strong disabled:opacity-50"
              >
                {remindMutation.isPending ? 'Sending...' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}

      <DecisionModal
        open={showArchiveModal}
        title={cycle?.status === 'archived' ? 'Unarchive assessment cycle' : 'Archive assessment cycle'}
        description={
          cycle
            ? cycle.status === 'archived'
              ? `Unarchive assessment "${cycle.name}"?`
              : `Archive assessment "${cycle.name}"?`
            : 'Update this assessment?'
        }
        confirmLabel={cycle?.status === 'archived' ? 'Unarchive' : 'Archive'}
        confirmVariant="secondary"
        dangerDetails={
          cycle?.status === 'archived'
            ? [`The assessment will return to ${restoredCycleStatusLabel} status.`]
            : [
                'The assessment will move to archived status.',
                'You can still view history and evidence after archiving.',
              ]
        }
        onConfirm={() => {
          if (cycle?.status === 'archived') {
            restoreCycleMutation.mutate()
          } else {
            archiveCycleMutation.mutate()
          }
          setShowArchiveModal(false)
        }}
        onClose={() => setShowArchiveModal(false)}
        isWorking={archiveCycleMutation.isPending || restoreCycleMutation.isPending}
      />

      <DecisionModal
        open={showDeleteModal}
        title="Delete assessment cycle"
        description={
          cycle
            ? `Delete assessment "${cycle.name}"? This permanently removes review items, comments, and uploaded evidence files.`
            : 'Delete this assessment?'
        }
        confirmLabel="Delete assessment"
        confirmVariant="destructive"
        dangerDetails={[
          'Assessment items, comments, and evidence files are permanently removed.',
          'This action cannot be undone.',
        ]}
        onConfirm={() => {
          deleteCycleMutation.mutate()
          setShowDeleteModal(false)
        }}
        onClose={() => setShowDeleteModal(false)}
        isWorking={deleteCycleMutation.isPending}
      />

      <ReviewGapExport open={gapExportOpen} cycleId={cycle.id} cycleName={cycle.name} onClose={() => setGapExportOpen(false)} />
      <ReviewCycleReportOptions
        open={reportOptionsOpen}
        value={reviewerDisplay}
        onChange={setReviewerDisplay}
        onClose={() => setReportOptionsOpen(false)}
        onConfirm={confirmReviewCycleReport}
      />
        </div>
      </div>
    </div>
  )
}
