import './workflow-pages.css'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import type {
  Document,
  ExtractedRequirement,
  PaginatedResponse,
  RequirementExtractionFlag,
  RequirementSetSummary,
  RequirementWithStatus,
  UserMention,
} from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import RichTextEditor from '../components/RichTextEditor'
import { normalizeRichText, stripHtml } from '../utils/richText'
import RequirementsOutline from '../components/RequirementsOutline'
import { useHierarchyDepth } from '../hooks/useHierarchyDepth'
import ResizableSplitView from '../components/ResizableSplitView'
import DecisionModal from '../components/ui/DecisionModal'
import { buildOutlineTree, type FlattenedNavItem } from '../utils/requirementsOutline'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import LoadError from '../components/ui/LoadError'
import DropdownMenu from '../components/ui/DropdownMenu'
import Button from '../components/ui/Button'
import DraftSaveStatus from '../components/ui/DraftSaveStatus'
import CopyButton from '../components/ui/CopyButton'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import { useSourceDrafts } from '../hooks/source/useSourceDrafts'
import { compareReferenceIds } from '../utils/referenceIds'
import { buildHierarchyTree, flattenHierarchyTree, withHierarchyContext } from '../utils/requirementHierarchy'
import { notifyApiError } from '../utils/notify'
import {
  buildHierarchyReferenceLookup,
  getHierarchyMismatch,
} from '../utils/referenceHierarchy'

type RequirementInsertKind = 'sibling' | 'child'

type RequirementDraft = {
  reference_id: string
  title: string
  text: string
  requirement_type: string
}

type RefUpdate = { id: string; reference_id: string }

type ImportReconciliation = {
  source_fingerprint: string
  draft_fingerprint: string
  missing: { id: string; reference_id: string }[]
  stale: { id: string; reference_id: string }[]
  duplicate: string[]
  differences: { source_id: string; reference_id: string; fields: Record<string, { source: string | null; draft: string | null }> }[]
  reconciled: boolean
}

const parseNumericRefSegments = (referenceId: string) => {
  const cleaned = referenceId.trim().replace(/\.+$/, '')
  if (!cleaned) return null
  if (!/^\d+(?:\.\d+)*$/.test(cleaned)) return null
  const segments = cleaned
    .split('.')
    .filter(Boolean)
    .map((value) => Number(value))
  if (segments.some((value) => Number.isNaN(value))) return null
  return segments
}

const joinNumericRefSegments = (segments: number[]) => segments.join('.')

const refMatchesPrefix = (referenceId: string, prefix: string) =>
  referenceId === prefix || referenceId.startsWith(`${prefix}.`)

const buildChildrenMap = (items: RequirementWithStatus[]) => {
  const map = new Map<string, string[]>()
  items.forEach((item) => {
    const key = item.parent_id || '__root__'
    const current = map.get(key)
    if (current) current.push(item.id)
    else map.set(key, [item.id])
  })
  return map
}

const collectSubtreeIds = (childrenMap: Map<string, string[]>, rootId: string) => {
  const ids: string[] = []
  const queue: string[] = [rootId]
  while (queue.length) {
    const next = queue.shift()
    if (!next) continue
    ids.push(next)
    const children = childrenMap.get(next)
    if (children?.length) queue.push(...children)
  }
  return ids
}

const arrayEqual = (left: number[], right: number[]) =>
  left.length === right.length && left.every((value, idx) => value === right[idx])

const sortIdsByReferenceDesc = (
  ids: string[],
  itemsById: Map<string, RequirementWithStatus>
) => {
  return [...ids].sort((a, b) => {
    const left = itemsById.get(a)?.reference_id || ''
    const right = itemsById.get(b)?.reference_id || ''
    // Prefer deeper refs first, then larger refs first.
    const leftDepth = left.split('.').length
    const rightDepth = right.split('.').length
    if (leftDepth !== rightDepth) return rightDepth - leftDepth
    return compareReferenceIds(right, left)
  })
}

export default function RequirementsSetEdit() {
  const { documentId } = useParams<{ documentId: string }>()
  const { user } = useAuth()
  const isAdminOrManager = user?.role === 'admin' || user?.role === 'manager'
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return true
    if (typeof window.matchMedia !== 'function') return window.innerWidth >= 1024
    return window.matchMedia('(min-width: 1024px)').matches
  })

  const [filters, setFilters] = useState({
    status: '',
    search: '',
  })
  const [searchParams, setSearchParams] = useSearchParams()
  const hierarchyDepth = useHierarchyDepth()
  const showAllEditors = searchParams.get('mode') === 'all'
  const [showAddRequirementModal, setShowAddRequirementModal] = useState(false)
  const [newRequirementDraft, setNewRequirementDraft] = useState({
    reference_id: '',
    title: '',
    text: '',
    requirement_type: 'mandatory',
    default_owner_id: '',
  })
  const [showDeleteSetModal, setShowDeleteSetModal] = useState(false)
  const [pendingSubtreeDelete, setPendingSubtreeDelete] = useState<{
    rootId: string
    rootRef: string
    subtreeCount: number
  } | null>(null)
  const [pendingInsert, setPendingInsert] = useState<{
    kind: RequirementInsertKind
    anchorId: string
  } | null>(null)
  const [decisionAction, setDecisionAction] = useState<'approve' | 'reject' | null>(null)
  const [decisionComment, setDecisionComment] = useState('')
  const [decisionCommentError, setDecisionCommentError] = useState<string | null>(null)

  useEffect(() => {
    setFilters({ status: '', search: '' })
    setShowDeleteSetModal(false)
    setPendingSubtreeDelete(null)
    setPendingInsert(null)
    setDecisionAction(null)
    setDecisionComment('')
    setDecisionCommentError(null)
  }, [documentId])

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

  useEffect(() => {
    if (!isAdminOrManager && documentId) {
      navigate(`/requirements/sets/${documentId}`, { replace: true })
    }
  }, [documentId, isAdminOrManager, navigate])

  const { data: doc } = useQuery({
    queryKey: ['document', documentId],
    queryFn: async () => {
      const response = await api.get<Document>(`/documents/${documentId}`)
      return response.data
    },
    enabled: !!documentId,
  })

  const originalMetadata = {
    name: doc?.name || '',
    document_type: doc?.document_type || '',
    version: doc?.version || '',
    effective_date: doc?.effective_date ? new Date(doc.effective_date).toISOString().slice(0, 10) : '',
    testing_frequency: doc?.testing_frequency || '',
  }
  const metadataAutosave = useSourceDrafts({
    scopeId: documentId,
    originals: doc && documentId ? { [documentId]: originalMetadata } : {},
    normalise: (draft: typeof originalMetadata) => ({ ...draft, name: draft.name.trim(), document_type: draft.document_type.trim(), version: draft.version.trim() }),
    validate: (draft) => !draft.document_type ? 'Document category is required. Enter a category, then retry saving.' : undefined,
    persist: async (savedDocumentId, draft) => {
      await api.put(`/documents/${savedDocumentId}`, {
        name: draft.name || null, document_type: draft.document_type,
        version: draft.version || null,
        effective_date: draft.effective_date ? `${draft.effective_date}T00:00:00Z` : null,
        testing_frequency: draft.testing_frequency || null,
      })
      await queryClient.invalidateQueries({ queryKey: ['document', savedDocumentId] })
      void queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', savedDocumentId] })
      void queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const metadataForm = (documentId && metadataAutosave.drafts[documentId]) || originalMetadata
  const metadataError = documentId ? metadataAutosave.error(documentId) : undefined
  const updateMetadata = (patch: Partial<typeof originalMetadata>) => {
    if (documentId && isAdminOrManager) metadataAutosave.update(documentId, patch)
  }

  const { data: mentionUsers } = useQuery({
    queryKey: ['mention-users'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')
      return response.data
    },
    enabled: showAddRequirementModal,
  })

  const prepareEditQuery = useQuery({
    queryKey: ['requirements-set-edit-prepare', documentId],
    queryFn: async () => {
      await api.post(`/documents/${documentId}/prepare-edit`)
      return true
    },
    enabled: !!documentId && isAdminOrManager,
    retry: false,
  })

  useEffect(() => {
    if (!prepareEditQuery.isSuccess) return
    queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
    queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
  }, [documentId, prepareEditQuery.isSuccess, queryClient])

  useEffect(() => {
    if (!doc?.jurisdiction_id) return
    if (jurisdictionId && doc.jurisdiction_id !== jurisdictionId) {
      setJurisdictionId(doc.jurisdiction_id)
    }
  }, [doc?.jurisdiction_id, jurisdictionId, setJurisdictionId])

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

  const archiveSetMutation = useMutation({
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

  const restoreSetMutation = useMutation({
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

  const deleteSetMutation = useMutation({
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

  const createRequirementMutation = useMutation({
    mutationFn: async (payload: {
      document_id: string
      reference_id: string
      title?: string | null
      text?: string | null
      requirement_type: string
      parent_id?: string | null
      default_owner_id?: string | null
    }) => {
      await api.post('/requirements', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      setShowAddRequirementModal(false)
      setNewRequirementDraft({
        reference_id: '',
        title: '',
        text: '',
        requirement_type: 'mandatory',
        default_owner_id: '',
      })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Add requirement failed')
    },
  })

  const deleteRequirementSubtreeMutation = useMutation({
    mutationFn: async (payload: { rootId: string }) => {
      if (!documentId) return
      const items = data?.items || []
      const childrenMap = buildChildrenMap(items)
      const subtreeIds = collectSubtreeIds(childrenMap, payload.rootId)

      // Deactivate descendants first, then the selected requirement.
      const itemsById = new Map(items.map((item) => [item.id, item]))
      const descendantIds = subtreeIds.filter((id) => id !== payload.rootId)
      const ordered = [...descendantIds, payload.rootId]

      for (const id of ordered) {
        if (!itemsById.has(id)) continue
        await api.put(`/requirements/${id}/deactivate`)
      }
    },
    onSuccess: () => {
      if (!documentId) return
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId, 'edit'] })
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId, 'edit'] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Delete failed')
    },
  })

  const insertRequirementMutation = useMutation({
    mutationFn: async (payload: {
      kind: RequirementInsertKind
      anchorId: string
    }) => {
      if (!documentId) return

      const items = data?.items || []
      const itemsById = new Map(items.map((item) => [item.id, item]))
      const anchor = itemsById.get(payload.anchorId)
      if (!anchor) return

      const childrenMap = buildChildrenMap(items)

      const openManualAdd = () => {
        setNewRequirementDraft((prev) => ({
          ...prev,
          reference_id: '',
          title: '',
          text: '',
          requirement_type: 'mandatory',
        }))
        setShowAddRequirementModal(true)
      }

      const computeShiftUpdates = (args: {
        siblingIds: string[]
        prefixSegments: number[]
        startIndex: number
        segmentDepth: number
      }): RefUpdate[] | null => {
        const { siblingIds, prefixSegments, startIndex, segmentDepth } = args
        const siblingInfo: Array<{
          id: string
          index: number
          ref: string
        }> = []

        for (const id of siblingIds) {
          const sibling = itemsById.get(id)
          if (!sibling) continue
          const segments = parseNumericRefSegments(sibling.reference_id)
          if (!segments) return null
          if (segments.length !== segmentDepth) return null
          if (!arrayEqual(segments.slice(0, -1), prefixSegments)) return null
          siblingInfo.push({
            id,
            index: segments[segments.length - 1],
            ref: sibling.reference_id,
          })
        }

        const shifts = siblingInfo
          .filter((s) => s.index >= startIndex)
          .sort((a, b) => b.index - a.index)

        const allRefs = new Map<string, string>()
        items.forEach((item) => allRefs.set(item.reference_id, item.id))

        const updates: RefUpdate[] = []
        const plannedNewRefs = new Map<string, string>()

        for (const shift of shifts) {
          const oldPrefix = joinNumericRefSegments([...prefixSegments, shift.index])
          const newPrefix = joinNumericRefSegments([...prefixSegments, shift.index + 1])
          const subtreeIds = collectSubtreeIds(childrenMap, shift.id)

          const orderedSubtree = sortIdsByReferenceDesc(subtreeIds, itemsById)
          for (const subtreeId of orderedSubtree) {
            const node = itemsById.get(subtreeId)
            if (!node) continue
            const currentRef = node.reference_id
            if (!refMatchesPrefix(currentRef, oldPrefix)) return null
            const nextRef =
              currentRef === oldPrefix
                ? newPrefix
                : `${newPrefix}${currentRef.slice(oldPrefix.length)}`

            // Collision check: allow collisions only within the planned updates.
            const existingOwner = allRefs.get(nextRef)
            if (existingOwner && existingOwner !== node.id) {
              // If that other id is also planned to move away, it's okay; otherwise abort.
              if (!plannedNewRefs.has(existingOwner)) return null
            }

            plannedNewRefs.set(node.id, nextRef)
            updates.push({ id: node.id, reference_id: nextRef })
          }
        }

        return updates
      }

      const anchorSegments = parseNumericRefSegments(anchor.reference_id)
      if (!anchorSegments) {
        openManualAdd()
        return
      }

      let parentId: string | null = null
      let nextReferenceId: string | null = null
      let refUpdates: RefUpdate[] = []

      if (payload.kind === 'sibling') {
        parentId = anchor.parent_id || null
        const prefixSegments = anchorSegments.slice(0, -1)
        const anchorIndex = anchorSegments[anchorSegments.length - 1]
        const siblingIds = (items || [])
          .filter((item) => (item.parent_id || null) === parentId)
          .map((item) => item.id)

        // Require consistent numeric refs across siblings for safe auto-renumber.
        const siblingSegments = siblingIds
          .map((id) => itemsById.get(id))
          .filter(Boolean)
          .map((item) => parseNumericRefSegments((item as RequirementWithStatus).reference_id))
        if (siblingSegments.some((segments) => segments === null)) {
          openManualAdd()
          return
        }

        const insertIndex = anchorIndex + 1
        const siblingIndices = siblingSegments.map(
          (segments) => (segments as number[])[(segments as number[]).length - 1]
        )
        const nextIndex = siblingIndices
          .filter((idx) => idx > anchorIndex)
          .reduce<number | null>((min, idx) => (min === null ? idx : Math.min(min, idx)), null)

        if (nextIndex !== null && nextIndex === insertIndex) {
          const updates = computeShiftUpdates({
            siblingIds,
            prefixSegments,
            startIndex: insertIndex,
            segmentDepth: anchorSegments.length,
          })
          if (!updates) {
            openManualAdd()
            return
          }
          refUpdates = updates
        }

        nextReferenceId = joinNumericRefSegments([...prefixSegments, insertIndex])
      } else {
        parentId = anchor.id
        const prefixSegments = anchorSegments
        const childIds = (items || [])
          .filter((item) => item.parent_id === anchor.id)
          .map((item) => item.id)

        const childSegments = childIds
          .map((id) => itemsById.get(id))
          .filter(Boolean)
          .map((item) => parseNumericRefSegments((item as RequirementWithStatus).reference_id))
        if (childSegments.some((segments) => segments === null)) {
          openManualAdd()
          return
        }

        const insertIndex = 1
        const hasFirstChild = childSegments.some((segments) => {
          const segs = segments as number[]
          return (
            segs.length === prefixSegments.length + 1 &&
            arrayEqual(segs.slice(0, -1), prefixSegments) &&
            segs[segs.length - 1] === 1
          )
        })

        if (hasFirstChild) {
          const updates = computeShiftUpdates({
            siblingIds: childIds,
            prefixSegments,
            startIndex: insertIndex,
            segmentDepth: prefixSegments.length + 1,
          })
          if (!updates) {
            openManualAdd()
            return
          }
          refUpdates = updates
        }

        nextReferenceId = joinNumericRefSegments([...prefixSegments, insertIndex])
      }

      if (!nextReferenceId) {
        openManualAdd()
        return
      }

      // Apply renumber updates (if any), then create the new requirement.
      for (const update of refUpdates) {
        await api.put(`/requirements/${update.id}`, { reference_id: update.reference_id })
      }

      await api.post('/requirements', {
        document_id: documentId,
        reference_id: nextReferenceId,
        title: null,
        text: '',
        requirement_type: 'mandatory',
        parent_id: parentId,
        default_owner_id: null,
      })
    },
    onSuccess: () => {
      if (!documentId) return
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId, 'edit'] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Insert failed')
    },
  })

  const submitSetMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/documents/${documentId}/submit`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-set-summary', documentId] })
      queryClient.invalidateQueries({ queryKey: ['requirements-sets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Submit failed')
    },
  })

  const approveSetMutation = useMutation({
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
      navigate(`/requirements/sets/${documentId}`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Approve failed')
    },
  })

  const rejectSetMutation = useMutation({
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

  const { data, dataUpdatedAt, isLoading, isError, refetch } = useQuery({
    queryKey: ['requirements', 'set', documentId, 'edit'],
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
    enabled: !!documentId && isAdminOrManager && !prepareEditQuery.isLoading,
  })

  const draftVersionId = data?.items?.find((item) => item.requirement_set_version_id)?.requirement_set_version_id
  const reconciliationQuery = useQuery({
    queryKey: ['import-reconciliation', documentId, draftVersionId, dataUpdatedAt],
    queryFn: async () => {
      const response = await api.get<ImportReconciliation | null>(
        `/requirements/sets/${documentId}/versions/${draftVersionId}/import-reconciliation`
      )
      return response.data
    },
    enabled: !!documentId && !!draftVersionId && !!doc?.current_extraction_id &&
      isAdminOrManager && prepareEditQuery.isSuccess,
    retry: false,
  })
  const reconcileMutation = useMutation({
    mutationFn: async (report: ImportReconciliation) => {
      await api.post(
        `/requirements/sets/${documentId}/versions/${draftVersionId}/import-reconciliation`,
        { source_fingerprint: report.source_fingerprint, draft_fingerprint: report.draft_fingerprint }
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['requirements', 'set', documentId, 'edit'] })
      queryClient.invalidateQueries({ queryKey: ['import-reconciliation', documentId] })
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Reconciliation failed')
      reconciliationQuery.refetch()
    },
  })

  const { data: extractionSourceData } = useQuery({
    queryKey: ['document-extractions', documentId, 'flags'],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.append('limit', '10000')
      const response = await api.get<PaginatedResponse<ExtractedRequirement>>(
        `/documents/${documentId}/extractions?${params.toString()}`
      )
      return response.data
    },
    enabled: !!documentId && isAdminOrManager,
  })

  const sourceAutosave = useSourceDrafts<RequirementDraft>({
    scopeId: documentId,
    originals: Object.fromEntries((data?.items || []).map((item) => [item.id, {
      reference_id: item.reference_id, title: item.title || '', text: item.text, requirement_type: item.requirement_type,
    }])),
    normalise: (draft) => ({ ...draft, reference_id: draft.reference_id.trim(), title: draft.title.trim(), text: normalizeRichText(draft.text) }),
    validate: (draft) => !draft.reference_id ? 'A reference is required. Enter one, then retry saving.' : undefined,
    persist: async (requirementId, draft) => {
      await api.put(`/requirements/${requirementId}`, { ...draft, title: draft.title || null })
      await queryClient.invalidateQueries({ queryKey: ['requirements'] })
    },
  })
  const drafts = sourceAutosave.drafts
  const hierarchyMutation = useMutation({
    mutationFn: async (requirementId: string) => {
      await api.put(`/requirements/${requirementId}`, { sync_parent_from_reference: true })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['requirements'] }),
    onError: (error: unknown) => notifyApiError(toast, error, 'Hierarchy update failed'),
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

  const flattenedRequirements = useMemo(() => allRequirements.filter(({ item }) => {
    const query = filters.search.trim().toLowerCase()
    return (!filters.status || item.requirement_type === filters.status) && (!query || `${item.reference_id} ${item.title || ''} ${normalizeRichText(item.text).replace(/<[^>]*>/g, ' ')}`.toLowerCase().includes(query))
  }), [allRequirements, filters])

  const selectedRequirement = flattenedRequirements.find(({ item }) => item.id === searchParams.get('item')) || flattenedRequirements[0]
  const editorItems = showAllEditors ? flattenedRequirements.filter(({ depth }) => hierarchyDepth.levels === 'all' || depth < hierarchyDepth.levels) : selectedRequirement ? [selectedRequirement] : []
  const selectedIndex = flattenedRequirements.findIndex(({ item }) => item.id === selectedRequirement?.item.id)
  const selectRequirement = (id: string) => setSearchParams((previous) => { const next = new URLSearchParams(previous); next.set('item', id); return next }, { replace: true })

  const requirementReferenceLookup = useMemo(
    () => buildHierarchyReferenceLookup(data?.items || []),
    [data?.items]
  )

  const hierarchyMismatchByRequirementId = useMemo(() => {
    const mismatchMap = new Map<string, ReturnType<typeof getHierarchyMismatch>>()
    ;(data?.items || []).forEach((item) => {
      mismatchMap.set(item.id, getHierarchyMismatch(item, requirementReferenceLookup))
    })
    return mismatchMap
  }, [data?.items, requirementReferenceLookup])

  const extractionById = useMemo(() => {
    const lookup = new Map<string, ExtractedRequirement>()
    ;(extractionSourceData?.items || []).forEach((item) => {
      lookup.set(item.id, item)
    })
    return lookup
  }, [extractionSourceData?.items])

  const extractionFlagsByRequirementId = useMemo(() => {
    const flagMap = new Map<string, RequirementExtractionFlag>()
    ;(data?.items || []).forEach((item) => {
      if (!item.source_extraction_id) {
        flagMap.set(item.id, {
          extraction_id: null,
          flagged: false,
          reason: null,
        })
        return
      }

      const extraction = extractionById.get(item.source_extraction_id)
      const flagged = !!extraction?.needs_review
      flagMap.set(item.id, {
        extraction_id: item.source_extraction_id,
        flagged,
        reason: flagged ? extraction?.review_reason || 'needs_review' : null,
      })
    })
    return flagMap
  }, [data?.items, extractionById])

  const updateDraft = (item: RequirementWithStatus, patch: Partial<RequirementDraft>) => {
    if (isAdminOrManager) sourceAutosave.update(item.id, patch)
  }
  const hasChanges = (item: RequirementWithStatus) => sourceAutosave.state(item.id) !== 'saved'
  const handleAutoSave = (item: RequirementWithStatus) => {
    if (isAdminOrManager) void sourceAutosave.save(item.id)
  }
  const handleHierarchySync = (item: RequirementWithStatus) => {
    if (isAdminOrManager && !hasChanges(item)) hierarchyMutation.mutate(item.id)
  }

  const requirementTypeOptions = [
    { value: 'mandatory', label: 'Mandatory' },
    { value: 'recommended', label: 'Recommended' },
    { value: 'informational', label: 'Informational' },
    { value: 'not_applicable', label: 'Not Applicable' },
  ]

  const requirementChildrenMap = useMemo(
    () => buildChildrenMap(data?.items || []),
    [data?.items]
  )
  const hasUnsavedDrafts = sourceAutosave.hasUnsavedChanges || metadataAutosave.hasUnsavedChanges
  useDraftNavigationGuard(hasUnsavedDrafts)

  const openDecision = (action: 'approve' | 'reject') => {
    setDecisionAction(action)
    setDecisionComment('')
    setDecisionCommentError(null)
  }

  const handleDecisionConfirm = () => {
    if (!decisionAction || hasUnsavedDrafts) return
    const trimmedComment = decisionComment.trim()
    if (decisionAction === 'reject' && !trimmedComment) {
      setDecisionCommentError('Rejection comment is required.')
      return
    }
    setDecisionCommentError(null)
    if (decisionAction === 'approve') {
      approveSetMutation.mutate(trimmedComment || undefined, {
        onSuccess: () => {
          setDecisionAction(null)
          setDecisionComment('')
        },
      })
      return
    }
    rejectSetMutation.mutate(trimmedComment, {
      onSuccess: () => {
        setDecisionAction(null)
        setDecisionComment('')
      },
    })
  }

  const requestInsert = (kind: RequirementInsertKind, anchorId: string) => {
    if (hasUnsavedDrafts) {
      setPendingInsert({ kind, anchorId })
      return
    }
    insertRequirementMutation.mutate({ kind, anchorId })
  }

  const handleQuickTypeChange = (item: RequirementWithStatus, nextType: RequirementDraft['requirement_type']) => {
    updateDraft(item, { requirement_type: nextType })
    handleAutoSave(item)
  }

  const outlineGroups = useMemo(() => {
    const matchingIds = new Set(flattenedRequirements.map(({ item }) => item.id))
    const navItems: FlattenedNavItem[] = withHierarchyContext(allRequirements, (item) => matchingIds.has(item.id))
      .map(({ item, depth, isContext }) => {
        const extractionFlag = extractionFlagsByRequirementId.get(item.id)
        return {
          key: item.id,
          isContext,
          targetId: `req-${item.id}`,
          referenceId: item.reference_id,
          title: item.title || null,
          isFlagged: !!extractionFlag?.flagged,
          flagReason: extractionFlag?.reason || null,
          // Use the same hierarchy used in the main list. Deriving depth purely from
          // numeric segments (e.g., "12.1") can create phantom parents when "12" doesn't exist.
          depth,
        }
      })
      .filter(Boolean) as FlattenedNavItem[]

    const maxDepthInData = navItems.reduce((max, item) => Math.max(max, item.depth), 0)
    const maxOutlineDepth = maxDepthInData

    return [
      {
        key: documentId || 'requirements',
        title: doc?.name || doc?.filename || 'Requirements',
        nodes: buildOutlineTree(navItems, maxOutlineDepth),
      },
    ]
  }, [doc?.filename, doc?.name, documentId, extractionFlagsByRequirementId, flattenedRequirements, allRequirements])

  if (!isAdminOrManager) {
    return (
      <div className="rounded-lg border border-line bg-surface p-6 text-sm text-muted">
        Editing is restricted to managers and admins.
      </div>
    )
  }

  return (
    <div className="workflow-page requirement-edit-page min-w-0">
      <div className="workflow-heading flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">
            Edit: {doc?.name || doc?.filename || 'Requirements Set'}
          </h1>
          {doc?.jurisdiction_id && (
            <div className="mt-1 text-sm text-muted">
              Jurisdiction:{' '}
              {jurisdictionById[doc.jurisdiction_id]?.name || doc.jurisdiction_id}
            </div>
          )}
          <p className="text-sm text-muted mt-1">
            Drafts save automatically. Submission and approval are separate actions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/requirements" className="text-sm text-muted hover:text-ink">
            &larr; Back to Requirements
          </Link>
          {documentId ? (
            <button
              type="button"
              onClick={() => setShowAddRequirementModal(true)}
              className="inline-flex rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-hover"
            >
              Add Requirement
            </button>
          ) : null}
          {documentId && (
            <Link
              to={`/requirements/sets/${documentId}`}
              className="inline-flex rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-ink hover:bg-canvas"
            >
              View
            </Link>
          )}
          {doc && ['draft', 'changes_requested'].includes(doc.status) ? (
            <button
              type="button"
              onClick={() => { if (!hasUnsavedDrafts) submitSetMutation.mutate() }}
              disabled={submitSetMutation.isPending || hasUnsavedDrafts}
              className="inline-flex rounded-md bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
            >
              {submitSetMutation.isPending ? 'Submitting...' : 'Submit for Approval'}
            </button>
          ) : null}
          {doc && doc.status === 'pending_approval' ? (
            <>
              <button
                type="button"
                onClick={() => openDecision('approve')}
                disabled={approveSetMutation.isPending || rejectSetMutation.isPending || hasUnsavedDrafts}
                className="inline-flex rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {approveSetMutation.isPending ? 'Approving...' : 'Approve'}
              </button>
              <button
                type="button"
                onClick={() => openDecision('reject')}
                disabled={approveSetMutation.isPending || rejectSetMutation.isPending || hasUnsavedDrafts}
                className="inline-flex rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {rejectSetMutation.isPending ? 'Rejecting...' : 'Reject'}
              </button>
            </>
          ) : null}
          <DropdownMenu ariaLabel="Requirement set actions" disabled={deleteSetMutation.isPending || archiveSetMutation.isPending || restoreSetMutation.isPending} items={[
            ...(hasAny ? [{ key: 'archive', label: isArchivedSet ? 'Restore Set' : 'Archive Set', onSelect: () => isArchivedSet ? restoreSetMutation.mutate() : archiveSetMutation.mutate() }] : []),
            { key: 'delete', label: 'Delete Set', tone: 'destructive', onSelect: () => setShowDeleteSetModal(true) },
          ]} />

        </div>
      </div>

      {reconciliationQuery.data && !reconciliationQuery.data.reconciled && (
        <section className="rounded-lg border border-warning-line bg-warning-soft p-4 mb-6" aria-label="Reconcile structured import">
          <h2 className="font-semibold text-ink">Reconcile source changes before approval</h2>
          <p className="mt-1 text-sm text-ink">
            The prepared draft differs from the current PDF extraction. Review each difference below.
            Reconciliation adds missing source rows and records your decision to retain any draft edits;
            it does not replace edited wording.
          </p>
          {!!reconciliationQuery.data.missing.length && <p className="mt-2 text-sm">
            Source rows to add: {reconciliationQuery.data.missing.map((item) => item.reference_id).join(', ')}
          </p>}
          {!!reconciliationQuery.data.stale.length && <p className="mt-2 text-sm">
            Stale draft rows must be deactivated here: {reconciliationQuery.data.stale.map((item) => item.reference_id).join(', ')}
          </p>}
          {!!reconciliationQuery.data.duplicate.length && <p className="mt-2 text-sm">
            Duplicate source links must be resolved before reconciliation.
          </p>}
          {reconciliationQuery.data.differences.map((item) => (
            <div key={item.source_id} className="mt-3 rounded border border-line bg-surface p-3 text-sm">
              <div className="font-medium">Source {item.reference_id}</div>
              {Object.entries(item.fields).map(([field, values]) => (
                <div key={field} className="mt-2">
                  <div className="font-medium">{field.replace(/_/g, ' ')}</div>
                  <div className="whitespace-pre-wrap break-words">Source: {values.source ?? '(empty)'}</div>
                  <div className="whitespace-pre-wrap break-words">Draft: {values.draft ?? '(empty)'}</div>
                </div>
              ))}
            </div>
          ))}
          <button type="button" className="mt-3 rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={reconcileMutation.isPending || !!reconciliationQuery.data.stale.length ||
              !!reconciliationQuery.data.duplicate.length || doc?.status === 'pending_approval'}
            onClick={() => {
              const report = reconciliationQuery.data
              if (report) reconcileMutation.mutate(report)
            }}>
            {reconcileMutation.isPending ? 'Reconciling...' : 'Add missing rows and confirm reviewed differences'}
          </button>
        </section>
      )}

      <details className="rounded-lg border border-line bg-surface p-4 mb-6">
        <summary className="cursor-pointer font-semibold text-ink">Requirement set details</summary>
        <form
          onSubmit={(event) => { event.preventDefault(); if (documentId) void metadataAutosave.save(documentId, true) }}
          onBlur={() => { if (documentId) void metadataAutosave.save(documentId) }}
          className="grid grid-cols-1 gap-4 items-end md:grid-cols-6"
        >
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-ink mb-1">
              Requirement Set Name
            </label>
            <input
              type="text"
              aria-label="Requirement Set Name"
              value={metadataForm.name}
              onChange={(e) => updateMetadata({ name: e.target.value })}
              placeholder="Requirement set name"
              className="w-full px-3 py-2 border border-line-strong rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">Document category</label>
            <input type="text" maxLength={50} placeholder="Enter a category"
              aria-label="Document category"
              value={metadataForm.document_type}
              onChange={(e) => updateMetadata({ document_type: e.target.value })}
              className={`w-full px-3 py-2 border rounded-md ${
                metadataError ? 'border-danger-line' : 'border-line-strong'
              }`}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Testing Frequency
            </label>
            <select
              aria-label="Testing Frequency"
              value={metadataForm.testing_frequency}
              onChange={(e) => updateMetadata({ testing_frequency: e.target.value })}
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
              onChange={(e) => updateMetadata({ version: e.target.value })}
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
              onChange={(e) => updateMetadata({ effective_date: e.target.value })}
              className="w-full px-3 py-2 border border-line-strong rounded-md"
            />
          </div>
          <div className="md:col-span-6">
            {documentId && <DraftSaveStatus state={metadataAutosave.state(documentId)} message={metadataError} onRetry={() => { void metadataAutosave.save(documentId, true) }} />}
          </div>
        </form>
      </details>

      <div className="workflow-toolbar mb-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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
          <div>
            <label className="block text-sm font-medium text-ink mb-1">Requirement type</label>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              aria-label="Requirement type filter"
              className="w-full px-3 py-2 border border-line-strong rounded-md"
            >
              <option value="">All types</option>
              <option value="mandatory">Mandatory</option>
              <option value="recommended">Recommended</option>
              <option value="informational">Informational</option>
              <option value="not_applicable">Not Applicable</option>
            </select>
          </div>
        </div>
      </div>

      <div className="requirement-editor-navigation sticky top-16 z-20 mb-4 flex flex-wrap items-center justify-between gap-3 bg-canvas py-3" aria-label="Editor navigation">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" aria-pressed={!showAllEditors} variant={!showAllEditors ? 'primary' : 'secondary'} onClick={() => setSearchParams((previous) => { const next = new URLSearchParams(previous); next.delete('mode'); return next }, { replace: true })}>Focused editing</Button>
          <Button size="sm" aria-pressed={showAllEditors} variant={showAllEditors ? 'primary' : 'secondary'} onClick={() => setSearchParams((previous) => { const next = new URLSearchParams(previous); next.set('mode', 'all'); return next }, { replace: true })}>All requirements</Button>
        </div>
        {!showAllEditors && selectedRequirement && <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted">{selectedIndex + 1} of {flattenedRequirements.length}</span>
          <Button size="sm" disabled={selectedIndex <= 0} onClick={() => selectRequirement(flattenedRequirements[selectedIndex - 1].item.id)}>Previous</Button>
          <Button size="sm" disabled={selectedIndex >= flattenedRequirements.length - 1} onClick={() => selectRequirement(flattenedRequirements[selectedIndex + 1].item.id)}>Next</Button>
        </div>}
      </div>
      {prepareEditQuery.isError ? (
        <div className="mb-6 rounded-lg border border-danger-line bg-danger-soft p-4 text-sm text-danger">
          {getApiErrorMessage(prepareEditQuery.error, 'Failed to prepare editable requirements')}
        </div>
      ) : null}

      {isError ? <LoadError subject="Requirements" onRetry={() => refetch()} /> : isLoading || prepareEditQuery.isLoading ? (
        <div className="text-center py-8">Loading...</div>
      ) : (
        (() => {
          const sidebar = (
            <div className="sticky top-20 max-h-[calc(100dvh-7rem)] overflow-auto">
              <RequirementsOutline
                groups={outlineGroups}
                levels={hierarchyDepth.levels}
                onLevelsChange={hierarchyDepth.changeLevels}
                maxLevels={Math.max(1, ...allRequirements.map(({ depth }) => depth + 1))}
                selectedTargetId={!showAllEditors && selectedRequirement ? `req-${selectedRequirement.item.id}` : undefined}
                onNavigate={(targetId) => {
                  if (!showAllEditors) { selectRequirement(targetId.replace(/^req-/, '')); return }
                  const target = allRequirements.find(({ item }) => `req-${item.id}` === targetId)
                  if (target && hierarchyDepth.levels !== 'all' && target.depth >= hierarchyDepth.levels) {
                    hierarchyDepth.changeLevels(target.depth + 1)
                    requestAnimationFrame(() => window.document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
                    return
                  }
                  window.document.getElementById(targetId)?.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start',
                  })
                }}
             />
            </div>
          )

          const main = (
            <section aria-label="Requirement editor" className="min-w-0">
              <div className="min-w-0">
                <div className="space-y-4">
                  <div className="hidden 2xl:grid 2xl:grid-cols-[minmax(0,1.6fr)_minmax(0,3fr)_minmax(0,1.4fr)_minmax(0,0.7fr)] gap-4 bg-canvas px-6 py-3 text-xs font-medium uppercase tracking-wide text-muted rounded-md">
                    <div className="col-span-2">Reference / Title</div>
                    <div>Details</div>
                    <div>Actions</div>
                  </div>

                  {showAllEditors && flattenedRequirements.length > 0 && editorItems.length === 0 && <p role="status" className="text-sm text-muted">No requirements at this depth. <button type="button" className="text-accent underline" onClick={() => hierarchyDepth.changeLevels('all')}>Show all levels</button></p>}
                  {editorItems.map(({ item, depth }) => {
                    const draft = drafts[item.id]
                    const extractionFlag = extractionFlagsByRequirementId.get(item.id)
                    const hierarchyMismatch = hierarchyMismatchByRequirementId.get(item.id)
                    const isFlagged = !!extractionFlag?.flagged
                    const flagReason = extractionFlag?.reason || 'needs_review'
                    const isSaving = sourceAutosave.state(item.id) === 'saving' || (hierarchyMutation.isPending && hierarchyMutation.variables === item.id)
                    const isBusy =
                      isSaving ||
                      createRequirementMutation.isPending ||
                      deleteRequirementSubtreeMutation.isPending ||
                      insertRequirementMutation.isPending

                    return (
                      <div key={item.id} className="space-y-2">
                        <div
                          id={`req-${item.id}`}
                          className={`rounded-lg border p-4 ${
                            isFlagged
                              ? 'border-warning-line bg-warning-soft/40'
                              : item.requirement_type === 'informational' ||
                                  item.requirement_type === 'not_applicable'
                                ? 'border-line bg-canvas'
                                : 'border-line bg-surface'
                          }`}
                        >
                          {isFlagged ? (
                            <div className="mb-3 rounded-md border border-warning-line bg-warning-soft px-3 py-2 text-xs text-warning">
                              Flagged from extraction review: {flagReason}
                            </div>
                          ) : null}
                          {hierarchyMismatch?.isMismatch ? (
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-info-line bg-info-soft px-3 py-2 text-xs text-info">
                              <span>
                                Hierarchy mismatch. Reference implies{' '}
                                {hierarchyMismatch.parentReferenceId
                                  ? `parent ${hierarchyMismatch.parentReferenceId}`
                                  : 'a top-level item'}
                                .
                              </span>
                              <button
                                type="button"
                                onClick={() => handleHierarchySync(item)}
                                disabled={isBusy || hasChanges(item)}
                                data-testid={`fix-hierarchy-${item.id}`}
                                className="inline-flex items-center justify-center rounded-md border border-info-line bg-surface px-3 py-1.5 text-xs font-semibold text-info hover:bg-info-soft disabled:opacity-50"
                              >
                                Fix hierarchy
                              </button>
                            </div>
                          ) : null}
                          <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1.6fr)_minmax(0,3fr)_minmax(0,1.4fr)_minmax(0,0.7fr)]">
                            <div className="relative" style={{ paddingLeft: `${showAllEditors ? Math.min(depth, 6) * 16 : 0}px` }}>
                              {showAllEditors && depth > 0 ? (
                                <div
                                  aria-hidden="true"
                                  className="pointer-events-none absolute inset-y-0 left-0 flex"
                                  style={{ width: `${depth * 16}px` }}
                                >
                                  {Array.from({ length: depth }).map((_, index) => (
                                    <div
                                      key={index}
                                      className="h-full w-4 border-l border-line/70"
                                  />
                                  ))}
                                </div>
                              ) : null}

                              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
                                Reference
                              </label>
                              <input
                                type="text"
                                aria-label={`Reference for ${item.reference_id}`}
                                value={draft?.reference_id ?? item.reference_id}
                                onChange={(e) => updateDraft(item, { reference_id: e.target.value })}
                                onBlur={() => handleAutoSave(item)}
                                className={`w-full rounded-md border px-3 py-2 text-base ${
                                  isFlagged ? 'border-warning-line bg-warning-soft/50' : 'border-line-strong'
                                }`}
                            />
                              <label className="mb-1 mt-3 block text-xs font-medium uppercase tracking-wide text-muted">
                                Title
                              </label>
                              <input
                                type="text"
                                aria-label={`Title for ${item.reference_id}`}
                                value={draft?.title ?? (item.title || '')}
                                onChange={(e) => updateDraft(item, { title: e.target.value })}
                                placeholder="Optional title"
                                onBlur={() => handleAutoSave(item)}
                                className={`w-full rounded-md border px-3 py-2 text-base ${
                                  isFlagged ? 'border-warning-line bg-warning-soft/50' : 'border-line-strong'
                                }`}
                            />
                            </div>

                            <div>
                              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
                                Requirement Text
                              </label>
                              <RichTextEditor
                                ariaLabel={`Requirement text for ${item.reference_id}`}
                                value={draft?.text ?? item.text}
                                onChange={(value) => updateDraft(item, { text: value })}
                                onBlur={() => handleAutoSave(item)}
                                className={isFlagged ? 'border-warning-line bg-warning-soft/25 shadow-sm' : 'shadow-sm'}
                                editorClassName="min-h-[180px] text-base"
                            />
                            </div>

                            <div className="space-y-3">
                              <div>
                                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
                                  Requirement Type
                                </label>
                                <div className="flex flex-wrap gap-2">
                                  {requirementTypeOptions.map((option) => {
                                    const currentType =
                                      draft?.requirement_type ?? item.requirement_type
                                    const isActive = currentType === option.value
                                    return (
                                      <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => handleQuickTypeChange(item, option.value)}
                                        disabled={isBusy}
                                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                                          isActive
                                            ? 'border-info bg-info-soft text-info'
                                            : 'border-line-strong text-muted hover:border-line-strong hover:text-ink'
                                        }`}
                                      >
                                        {option.label}
                                      </button>
                                    )
                                  })}
                                </div>
                              </div>
                            </div>

                            <div className="flex flex-col gap-2">
                              <DraftSaveStatus state={sourceAutosave.state(item.id)} message={sourceAutosave.error(item.id)} onRetry={() => { void sourceAutosave.save(item.id, true) }} />
                              <CopyButton value={`${draft?.reference_id ?? item.reference_id}\n${stripHtml(draft?.text ?? item.text)}`} label="Copy requirement" />
                              <button
                                type="button"
                                onClick={() => {
                                  const subtreeCount = collectSubtreeIds(
                                    requirementChildrenMap,
                                    item.id
                                  ).length
                                  setPendingSubtreeDelete({
                                    rootId: item.id,
                                    rootRef: item.reference_id,
                                    subtreeCount,
                                  })
                                }}
                                disabled={isBusy}
                                className="inline-flex items-center justify-center rounded-md border border-danger-line px-3 py-1.5 text-xs font-semibold text-danger hover:bg-danger-soft disabled:opacity-50"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        </div>

                        <div className="group relative h-7">
                          <div
                            aria-hidden="true"
                            className="absolute inset-0 flex items-center justify-center"
                          >
                            <div className="h-px w-full bg-subtle" />
                          </div>
                          <div className="absolute inset-0 flex items-center justify-center">
                            <details className="relative">
                              <summary
                                aria-label="Insert requirement"
                                className="cursor-pointer select-none rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink shadow-sm hover:bg-canvas disabled:opacity-50 [&::-webkit-details-marker]:hidden list-none"
                              >
                                +
                              </summary>
                              <div className="absolute left-1/2 top-full z-10 mt-2 w-40 -translate-x-1/2 rounded-md border border-line bg-surface p-1 shadow-lg">
                                <button
                                  type="button"
                                  disabled={isBusy}
                                  onClick={() => {
                                    requestInsert('sibling', item.id)
                                  }}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                                >
                                  Insert sibling
                                </button>
                                <button
                                  type="button"
                                  disabled={isBusy}
                                  onClick={() => {
                                    requestInsert('child', item.id)
                                  }}
                                  className="w-full rounded px-2 py-1.5 text-left text-xs font-medium text-ink hover:bg-canvas disabled:opacity-50"
                                >
                                  Insert child
                                </button>
                              </div>
                            </details>
                          </div>
                        </div>
                      </div>
                    )
                  })}

                  {flattenedRequirements.length === 0 && (
                    <div className="text-center py-10 text-muted space-y-3">
                      <div>No requirements match these filters.</div>
                      {(filters.search || filters.status) && <Button size="sm" onClick={() => setFilters({ search: '', status: '' })}>Clear filters</Button>}
                      {isArchivedSet && (
                        <button
                          type="button"
                          onClick={() => restoreSetMutation.mutate()}
                          disabled={restoreSetMutation.isPending}
                          className="inline-flex rounded-md border border-line-strong px-3 py-1.5 text-sm font-medium text-ink hover:bg-canvas disabled:opacity-50"
                        >
                          Restore archived set
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </section>
          )

          return (
            <>
              {isDesktop ? (
                <ResizableSplitView
                  storageKey="requirements-set:outline"
                  defaultSidebarWidth={300}
                  minSidebarWidth={220}
                  maxSidebarWidth={520}
                  sidebar={sidebar}
                  main={main}
                  className="gap-8"
                  handleClassName="relative cursor-col-resize"
                  collapseLabel="Collapse outline"
                  expandLabel="Expand outline"
               />
              ) : (
                <><details className="mb-4 rounded-lg border border-line bg-surface p-3"><summary className="cursor-pointer text-sm font-semibold">Browse requirement hierarchy</summary><div className="mt-3 max-h-64 overflow-y-auto">{sidebar}</div></details>{main}</>
              )}
            </>
          )
        })()
      )}

      {showAddRequirementModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="max-h-[calc(100vh-2rem)] w-full max-w-2xl overflow-y-auto rounded-lg bg-surface p-4 sm:p-6">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-ink">Add Requirement</h2>
                <div className="mt-1 text-sm text-muted">
                  This creates a requirement in the current set (draft-safe). Hierarchy follows
                  the reference automatically.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAddRequirementModal(false)}
                className="rounded-md px-2 py-1 text-sm font-semibold text-muted hover:bg-subtle"
              >
                Close
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (!documentId) return
                const payload = {
                  document_id: documentId,
                  reference_id: newRequirementDraft.reference_id.trim(),
                  title: newRequirementDraft.title.trim() ? newRequirementDraft.title.trim() : null,
                  text: normalizeRichText(newRequirementDraft.text),
                  requirement_type: newRequirementDraft.requirement_type,
                  default_owner_id: newRequirementDraft.default_owner_id || null,
                }
                if (!payload.reference_id) { toast.error('A reference is required. Your changes have not been saved.'); return }
                createRequirementMutation.mutate(payload)
              }}
              className="space-y-4"
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Reference ID
                  </label>
                  <input
                    type="text"
                    value={newRequirementDraft.reference_id}
                    onChange={(e) =>
                      setNewRequirementDraft((prev) => ({
                        ...prev,
                        reference_id: e.target.value,
                      }))
                    }
                    required
                    className="w-full rounded-md border border-line-strong px-3 py-2"
                    placeholder="e.g. 1.2.3"
                 />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Type
                  </label>
                  <select
                    value={newRequirementDraft.requirement_type}
                    onChange={(e) =>
                      setNewRequirementDraft((prev) => ({
                        ...prev,
                        requirement_type: e.target.value,
                      }))
                    }
                    className="w-full rounded-md border border-line-strong px-3 py-2"
                  >
                    {requirementTypeOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-ink">Title</label>
                <input
                  type="text"
                  value={newRequirementDraft.title}
                  onChange={(e) =>
                    setNewRequirementDraft((prev) => ({ ...prev, title: e.target.value }))
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2"
               />
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Default owner (optional)
                  </label>
                  <select
                    value={newRequirementDraft.default_owner_id}
                    onChange={(e) =>
                      setNewRequirementDraft((prev) => ({
                        ...prev,
                        default_owner_id: e.target.value,
                      }))
                    }
                    className="w-full rounded-md border border-line-strong px-3 py-2"
                  >
                    <option value="">None</option>
                    {(mentionUsers?.items || []).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name || u.email}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-ink">Text</label>
                <div className="rounded-md border border-line-strong">
                  <RichTextEditor
                    value={newRequirementDraft.text}
                    onChange={(value) =>
                      setNewRequirementDraft((prev) => ({ ...prev, text: value }))
                    }
                 />
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddRequirementModal(false)}
                  className="rounded-md px-4 py-2 text-sm font-semibold text-ink hover:bg-subtle"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createRequirementMutation.isPending}
                  className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover disabled:opacity-50"
                >
                  {createRequirementMutation.isPending ? 'Adding...' : 'Add Requirement'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

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
        confirmDisabled={hasUnsavedDrafts}
        isWorking={approveSetMutation.isPending || rejectSetMutation.isPending}
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
          deleteSetMutation.mutate()
          setShowDeleteSetModal(false)
        }}
        onClose={() => setShowDeleteSetModal(false)}
        isWorking={deleteSetMutation.isPending}
      />

      <DecisionModal
        open={!!pendingSubtreeDelete}
        title="Delete requirement"
        description={
          pendingSubtreeDelete
            ? pendingSubtreeDelete.subtreeCount > 1
              ? `Delete requirement ${pendingSubtreeDelete.rootRef} and ${pendingSubtreeDelete.subtreeCount - 1} subitems?`
              : `Delete requirement ${pendingSubtreeDelete.rootRef}?`
            : 'Delete selected requirement?'
        }
        confirmLabel="Delete"
        confirmVariant="destructive"
        dangerDetails={
          pendingSubtreeDelete?.subtreeCount && pendingSubtreeDelete.subtreeCount > 1
            ? [
                'This will deactivate the selected requirement and all descendants.',
                'Descendants are deactivated before the selected requirement.',
              ]
            : ['This will deactivate the selected requirement.']
        }
        onConfirm={() => {
          if (!pendingSubtreeDelete) return
          deleteRequirementSubtreeMutation.mutate({ rootId: pendingSubtreeDelete.rootId })
          setPendingSubtreeDelete(null)
        }}
        onClose={() => setPendingSubtreeDelete(null)}
        isWorking={deleteRequirementSubtreeMutation.isPending}
      />

      <DecisionModal
        open={!!pendingInsert}
        title="Unsaved changes detected"
        description="Wait for your draft changes to save before inserting a requirement. If a save failed, close this dialog and retry it."
        confirmLabel="Continue insert"
        confirmVariant="primary"
        confirmDisabled={hasUnsavedDrafts}
        onConfirm={() => {
          if (!pendingInsert || hasUnsavedDrafts) return
          insertRequirementMutation.mutate({
            kind: pendingInsert.kind,
            anchorId: pendingInsert.anchorId,
          })
          setPendingInsert(null)
        }}
        onClose={() => setPendingInsert(null)}
        isWorking={insertRequirementMutation.isPending}
      />
    </div>
  )
}
