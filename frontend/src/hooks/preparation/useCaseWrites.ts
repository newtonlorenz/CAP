import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import { useQueryClient } from '@tanstack/react-query'
import { getApiErrorMessage } from '../../api/errors'
import { preparationApi } from '../../api/preparation'
import type { PreparationCase } from '../../types/preparation'

type PauseReason = 'error' | 'conflict' | null

/** Case revisions are shared by every answer, so writes must share one queue. */
export function useCaseWrites(caseId: string, revision: number, metadataDirty = false) {
  const queryClient = useQueryClient()
  const active = useRef(true)
  const queue = useRef(Promise.resolve())
  const pending = useRef(0)
  const dirtyFields = useRef(new Set<string>())
  const paused = useRef<PauseReason>(null)
  const latestRevision = useRef(revision)
  const [isWriting, setIsWriting] = useState(false)
  const [hasPendingDrafts, setHasPendingDrafts] = useState(false)
  const [hasPendingUploads, setHasPendingUploads] = useState(false)
  const [hasPendingAnswerDrafts, setHasPendingAnswerDrafts] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pauseReason, setPauseReason] = useState<PauseReason>(null)
  const [conflictReady, setConflictReady] = useState(false)
  const [resumeVersion, setResumeVersion] = useState(0)
  // A background refresh must not silently rebase an unsaved draft.
  if (!pending.current && !dirtyFields.current.size && !paused.current && !metadataDirty)
    latestRevision.current = Math.max(revision, latestRevision.current)

  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [caseId])

  const setFieldDirty = useCallback((key: string, dirty: boolean) => {
    if (dirty) dirtyFields.current.add(key)
    else dirtyFields.current.delete(key)
    setHasPendingDrafts(dirtyFields.current.size > 0)
    setHasPendingUploads([...dirtyFields.current].some(item => item.startsWith('upload:')))
    setHasPendingAnswerDrafts([...dirtyFields.current].some(item => !item.startsWith('upload:')))
  }, [])

  const refreshConflict = useCallback(async () => {
    setConflictReady(false)
    try {
      const latest = await preparationApi.getCase(caseId)
      if (!active.current) return
      await queryClient.cancelQueries({ queryKey: ['preparation', 'case', caseId], exact: true })
      if (!active.current) return
      const cached = queryClient.getQueryData<PreparationCase>(['preparation', 'case', caseId])
      const current = cached && cached.revision > latest.revision ? cached : latest
      latestRevision.current = current.revision
      queryClient.setQueryData(['preparation', 'case', caseId], current)
      setConflictReady(true)
    } catch {
      if (active.current)
        setError('The latest form could not be loaded. Your drafts are still here. Reload the latest form before resolving the conflict.')
    }
  }, [caseId, queryClient])

  const resumeWrites = useCallback(() => {
    if (pending.current || (paused.current === 'conflict' && !conflictReady)) return false
    paused.current = null
    setPauseReason(null)
    setError(null)
    setResumeVersion((version) => version + 1)
    return true
  }, [conflictReady])

  const enqueue = useCallback((
    action: (expectedRevision: number) => Promise<PreparationCase>,
    canRun: () => boolean = () => true,
  ): Promise<PreparationCase | null> => {
    if (paused.current || !active.current) return Promise.resolve(null)
    pending.current += 1
    setIsWriting(true)
    const result = queue.current.then(async () => {
      if (paused.current || !active.current || !canRun()) return null
      try {
        await queryClient.cancelQueries({ queryKey: ['preparation', 'case', caseId], exact: true })
        if (!active.current || !canRun()) return null
        const updated = await action(latestRevision.current)
        if (!active.current) return updated
        // Reads begun before/during this write must not replace its acknowledgement.
        await queryClient.cancelQueries({ queryKey: ['preparation', 'case', caseId], exact: true })
        if (!active.current) return updated
        latestRevision.current = updated.revision
        const cached = queryClient.getQueryData<PreparationCase>(['preparation', 'case', caseId])
        if (!cached || cached.revision <= updated.revision) queryClient.setQueryData(['preparation', 'case', caseId], updated)
        void queryClient.invalidateQueries({ queryKey: ['preparation', 'cases'] })
        void queryClient.invalidateQueries({ queryKey: ['applications', 'item'] })
        void queryClient.invalidateQueries({ queryKey: ['preparation', 'review-queue'] })
        return updated
      } catch (caught) {
        if (!active.current) return null
        const conflict = axios.isAxiosError(caught) && caught.response?.status === 409
        paused.current = conflict ? 'conflict' : 'error'
        setPauseReason(paused.current)
        setError(conflict
          ? 'This form changed elsewhere. Autosave is paused. Compare your drafts with the latest saved answers before continuing.'
          : getApiErrorMessage(caught, 'Your changes could not be saved. Your drafts are still here. Retry when you are ready.'))
        if (conflict) await refreshConflict()
        return null
      }
    }).finally(() => {
      pending.current -= 1
      if (active.current) setIsWriting(pending.current > 0)
    })
    queue.current = result.then(() => undefined)
    return result
  }, [caseId, queryClient, refreshConflict])

  const run = useCallback((action: (expectedRevision: number) => Promise<PreparationCase>) => {
    // Explicit acceptance/reuse/metadata changes must never overtake draft writes.
    if (pending.current || dirtyFields.current.size) return Promise.resolve(false)
    return enqueue(action).then(Boolean)
  }, [enqueue])

  const saveField = useCallback((
    key: string,
    value: Omit<Parameters<typeof preparationApi.saveResponse>[2], 'expected_revision'>,
    canRun?: () => boolean,
  ) => enqueue((expected_revision) => preparationApi.saveResponse(caseId, key, {
    ...value, expected_revision,
  }), canRun), [caseId, enqueue])
  const acceptField = useCallback((key: string) =>
    run((revision) => preparationApi.acceptResponse(caseId, key, revision)), [caseId, run])
  const reuseField = useCallback((key: string, source_case_id: string, source_field_key: string) =>
    run((expected_revision) => preparationApi.reuseResponse(caseId, key, {
      expected_revision, source_case_id, source_field_key,
    })), [caseId, run])
  const updateCase = useCallback((patch: Omit<Parameters<typeof preparationApi.updateCase>[1], 'expected_revision'>) =>
    run((expected_revision) => preparationApi.updateCase(caseId, { ...patch, expected_revision })), [caseId, run])

  return useMemo(() => ({
    run, revision, isWriting, hasPendingDrafts, hasPendingUploads, hasPendingAnswerDrafts, error, pauseReason,
    conflicted: pauseReason === 'conflict', conflictReady, resumeVersion,
    setFieldDirty, refreshConflict, resumeWrites, saveField, acceptField, reuseField, updateCase,
  }), [run, revision, isWriting, hasPendingDrafts, hasPendingUploads, hasPendingAnswerDrafts, error, pauseReason, conflictReady, resumeVersion,
    setFieldDirty, refreshConflict, resumeWrites, saveField, acceptField, reuseField, updateCase])
}
export type CaseWrites = ReturnType<typeof useCaseWrites>
