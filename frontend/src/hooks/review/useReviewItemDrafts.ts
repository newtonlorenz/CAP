import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../../api/client'
import type { ReviewItemWithRequirement } from '../../types'
import { useToast } from '../../contexts/ToastContext'
import { notifyApiError } from '../../utils/notify'

export type ReviewDraft = {
  review_status: string
  requirement_status: string
  review_evidence: string
}
type SavePayload = { review_status?: string; requirement_status?: string; review_evidence?: string | null }
type SaveStatus = 'dirty' | 'saving' | 'saved' | 'error'
type Session = {
  id: string | undefined
  drafts: Record<string, ReviewDraft>
  server: Record<string, ReviewDraft>
  acknowledged: Record<string, Partial<ReviewDraft>>
  lanes: Record<string, Promise<void>>
  pending: Record<string, number>
  queuedEvidence: Record<string, string>
  timers: Record<string, number>
  evidenceTimers: Record<string, number>
  failed: Record<string, boolean>
}

const createSession = (id: string | undefined): Session => ({
  id, drafts: {}, server: {}, acknowledged: {}, lanes: {}, pending: {}, queuedEvidence: {}, timers: {}, evidenceTimers: {}, failed: {},
})

export const buildReviewDraft = (item: ReviewItemWithRequirement): ReviewDraft => ({
  review_status: item.review_status,
  requirement_status: item.requirement_current_status || 'not_started',
  review_evidence: item.review_evidence || '',
})

/** Keep edits across refetches and write each item's updates in user order. */
export function useReviewItemDrafts(
  cycleId: string | undefined,
  items: ReviewItemWithRequirement[] | undefined,
  onSaved: () => void
) {
  const toast = useToast()
  const [draftState, setDraftState] = useState<{ id: string | undefined; value: Record<string, ReviewDraft> }>({ id: cycleId, value: {} })
  const [statusState, setStatusState] = useState<{ id: string | undefined; value: Record<string, SaveStatus> }>({ id: cycleId, value: {} })
  const session = useRef<Session>(createSession(cycleId))
  if (session.current.id !== cycleId) {
    Object.values(session.current.timers).forEach(window.clearTimeout)
    Object.values(session.current.evidenceTimers).forEach(window.clearTimeout)
    session.current = createSession(cycleId)
  }
  const currentSession = session.current
  const onSavedRef = useRef(onSaved)
  onSavedRef.current = onSaved

  const setStatus = useCallback((owner: Session, itemId: string, value: SaveStatus | null) => {
    if (session.current !== owner) return
    setStatusState((previous) => {
      const next = { ...(previous.id === owner.id ? previous.value : {}) }
      if (value === null) delete next[itemId]
      else next[itemId] = value
      return { id: owner.id, value: next }
    })
  }, [])

  const putDraft = useCallback((owner: Session, itemId: string, next: ReviewDraft) => {
    if (session.current !== owner) return
    owner.drafts = { ...owner.drafts, [itemId]: next }
    setDraftState({ id: owner.id, value: owner.drafts })
  }, [])

  useEffect(() => {
    if (!items || session.current !== currentSession) return
    const nextServer: Record<string, ReviewDraft> = {}
    const nextDrafts: Record<string, ReviewDraft> = {}
    for (const item of items) {
      const incoming = buildReviewDraft(item)
      const previousServer = currentSession.server[item.id]
      const previousDraft = currentSession.drafts[item.id]
      const acknowledged = currentSession.acknowledged[item.id]
      nextServer[item.id] = incoming
      if (!previousDraft || !previousServer) {
        nextDrafts[item.id] = incoming
        continue
      }
      const next = { ...incoming }
      for (const field of ['review_status', 'requirement_status', 'review_evidence'] as const) {
        if (acknowledged?.[field] !== undefined) {
          if (incoming[field] === acknowledged[field]) {
            if (previousDraft[field] !== incoming[field]) next[field] = previousDraft[field]
            delete acknowledged[field]
          } else next[field] = previousDraft[field]
        } else if (previousDraft[field] !== previousServer[field]) {
          next[field] = previousDraft[field]
        }
      }
      nextDrafts[item.id] = next
    }
    const previous = currentSession.drafts
    currentSession.server = nextServer
    currentSession.drafts = nextDrafts
    const unchanged = Object.keys(nextDrafts).length === Object.keys(previous).length &&
      Object.entries(nextDrafts).every(([itemId, draft]) => {
        const old = previous[itemId]
        return old && draft.review_status === old.review_status &&
          draft.requirement_status === old.requirement_status && draft.review_evidence === old.review_evidence
      })
    if (!unchanged) setDraftState({ id: currentSession.id, value: nextDrafts })
  }, [items, currentSession])

  useEffect(() => () => {
    Object.values(currentSession.timers).forEach(window.clearTimeout)
    Object.values(currentSession.evidenceTimers).forEach(window.clearTimeout)
  }, [currentSession])

  const queueSave = useCallback((owner: Session, itemId: string, payload: SavePayload, retry = false) => {
    if (!owner.id || session.current !== owner) return
    if (owner.timers[itemId]) window.clearTimeout(owner.timers[itemId])
    if (retry) delete owner.failed[itemId]
    if (payload.review_evidence !== undefined) owner.queuedEvidence[itemId] = payload.review_evidence ?? ''
    owner.pending[itemId] = (owner.pending[itemId] || 0) + 1
    setStatus(owner, itemId, 'saving')
    const previous = owner.lanes[itemId] || Promise.resolve()
    owner.lanes[itemId] = previous.then(async () => {
      try {
        await api.put(`/review-cycles/${owner.id}/items/${itemId}`, payload)
        if (session.current !== owner) return
        const ack = owner.acknowledged[itemId] || {}
        if (payload.review_status !== undefined) ack.review_status = payload.review_status
        if (payload.requirement_status !== undefined) ack.requirement_status = payload.requirement_status
        if (payload.review_evidence !== undefined) ack.review_evidence = payload.review_evidence ?? ''
        owner.acknowledged[itemId] = ack
        onSavedRef.current()
        if (owner.pending[itemId] === 1 && !owner.failed[itemId]) {
          const draft = owner.drafts[itemId]
          const saved = { ...owner.server[itemId], ...ack }
          const dirty = draft && (Object.keys(draft) as (keyof ReviewDraft)[]).some((field) => draft[field] !== saved[field])
          setStatus(owner, itemId, dirty ? 'dirty' : 'saved')
          if (!dirty) owner.timers[itemId] = window.setTimeout(() => setStatus(owner, itemId, null), 1500)
        } else if (owner.pending[itemId] === 1) {
          setStatus(owner, itemId, 'error')
        }
      } catch (error) {
        if (session.current !== owner) return
        owner.failed[itemId] = true
        if (payload.review_evidence !== undefined) delete owner.queuedEvidence[itemId]
        setStatus(owner, itemId, 'error')
        notifyApiError(toast, error, 'Update failed')
      } finally {
        owner.pending[itemId] -= 1
      }
    })
  }, [setStatus, toast])

  const drafts = draftState.id === cycleId ? draftState.value : {}
  const saveStatusByItem = statusState.id === cycleId ? statusState.value : {}
  const getDraft = (item: ReviewItemWithRequirement) => drafts[item.id] || buildReviewDraft(item)

  const changeStatus = useCallback((item: ReviewItemWithRequirement, field: 'review_status' | 'requirement_status', value: string) => {
    const current = currentSession.drafts[item.id] || buildReviewDraft(item)
    if (current[field] === value) return
    const next = { ...current, [field]: value }
    putDraft(currentSession, item.id, next)
    queueSave(currentSession, item.id, field === 'requirement_status'
      ? { review_status: next.review_status, requirement_status: next.requirement_status, review_evidence: next.review_evidence }
      : { review_status: value })
  }, [currentSession, putDraft, queueSave])

  const saveEvidence = useCallback((item: ReviewItemWithRequirement) => {
    window.clearTimeout(currentSession.evidenceTimers[item.id])
    if (currentSession.failed[item.id]) return
    const current = currentSession.drafts[item.id] || buildReviewDraft(item)
    const trimmed = current.review_evidence.trim()
    if (trimmed !== current.review_evidence) putDraft(currentSession, item.id, { ...current, review_evidence: trimmed })
    const saved = currentSession.acknowledged[item.id]?.review_evidence ?? currentSession.server[item.id]?.review_evidence ?? ''
    const queued = currentSession.pending[item.id] > 0 ? currentSession.queuedEvidence[item.id] : undefined
    if (trimmed === (queued ?? saved).trim()) return
    currentSession.queuedEvidence[item.id] = trimmed
    queueSave(currentSession, item.id, { review_evidence: trimmed || null })
  }, [currentSession, putDraft, queueSave])

  const changeEvidence = useCallback((item: ReviewItemWithRequirement, value: string) => {
    const current = currentSession.drafts[item.id] || buildReviewDraft(item)
    putDraft(currentSession, item.id, { ...current, review_evidence: value })
    window.clearTimeout(currentSession.timers[item.id])
    window.clearTimeout(currentSession.evidenceTimers[item.id])
    if (currentSession.failed[item.id]) return
    const saved = currentSession.acknowledged[item.id]?.review_evidence ?? currentSession.server[item.id]?.review_evidence ?? ''
    setStatus(currentSession, item.id, currentSession.pending[item.id] > 0 ? 'saving' : value === saved ? 'saved' : 'dirty')
    currentSession.evidenceTimers[item.id] = window.setTimeout(() => saveEvidence(item), 800)
  }, [currentSession, putDraft, saveEvidence, setStatus])

  const retryItem = useCallback((item: ReviewItemWithRequirement) => {
    if (currentSession.pending[item.id] > 0) return
    window.clearTimeout(currentSession.evidenceTimers[item.id])
    const draft = currentSession.drafts[item.id] || buildReviewDraft(item)
    currentSession.queuedEvidence[item.id] = draft.review_evidence.trim()
    queueSave(currentSession, item.id, {
      review_status: draft.review_status,
      requirement_status: draft.requirement_status,
      review_evidence: draft.review_evidence.trim() || null,
    }, true)
  }, [currentSession, queueSave])

  const itemNeedsSave = (item: ReviewItemWithRequirement) => {
    const draft = currentSession.drafts[item.id] || buildReviewDraft(item)
    const server = currentSession.server[item.id] || buildReviewDraft(item)
    const ack = currentSession.acknowledged[item.id]
    return Boolean(currentSession.pending[item.id] > 0 || currentSession.failed[item.id] ||
      (['review_status', 'requirement_status', 'review_evidence'] as const).some((field) =>
        draft[field] !== (ack?.[field] ?? server[field])))
  }

  const hasUnsavedChanges = Boolean(items?.some((item) => {
    const draft = drafts[item.id]
    const server = currentSession.server[item.id] || buildReviewDraft(item)
    const ack = currentSession.acknowledged[item.id]
    return currentSession.failed[item.id] || (draft && (['review_status', 'requirement_status', 'review_evidence'] as const).some((field) =>
      draft[field] !== (ack?.[field] ?? server[field])))
  })) || Object.values(currentSession.pending).some((count) => count > 0)

  return { getDraft, changeStatus, changeEvidence, saveEvidence, retryItem, itemNeedsSave, saveStatusByItem, hasUnsavedChanges }
}
