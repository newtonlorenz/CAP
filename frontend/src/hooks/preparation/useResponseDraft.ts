import { useCallback, useEffect, useRef, useState } from 'react'
import { fieldValueToString, parseFieldValue, type PreparationField, type PreparationResponse } from '../../types/preparation'
import type { CaseWrites } from './useCaseWrites'

type Draft = { value: string; reason: string; evidenceIds: string[] }
const fromResponse = (response: PreparationResponse): Draft => ({
  value: fieldValueToString(response.value),
  reason: response.not_applicable_reason || '',
  evidenceIds: response.evidence_ids,
})
const toPayload = (field: PreparationField, draft: Draft) => ({
  value: draft.reason.trim() ? null : parseFieldValue(field.type, draft.value),
  not_applicable_reason: draft.reason.trim() || null,
  evidence_ids: [...draft.evidenceIds].sort(),
})

/** Drafts stay in memory. Acknowledging an older save never clears newer input. */
export function useResponseDraft(
  field: PreparationField,
  response: PreparationResponse,
  editable: boolean,
  writes: CaseWrites,
  onDirtyChange: (key: string, dirty: boolean) => void,
) {
  const [draft, setDraft] = useState(() => fromResponse(response))
  const current = useRef(draft)
  const serverSnapshot = JSON.stringify(toPayload(field, fromResponse(response)))
  const acknowledged = useRef(serverSnapshot)
  const observedServer = useRef({ snapshot: serverSnapshot, revision: writes.revision })
  const deferredServer = useRef<{ draft: Draft; revision: number } | null>(null)
  const uncertain = useRef(false)
  const [dirty, setDirty] = useState(false)
  const dirtyRef = useRef(false)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [localError, setLocalError] = useState('')
  const mounted = useRef(true)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const latest = useRef({ field, response, editable, writes, onDirtyChange })
  latest.current = { field, response, editable, writes, onDirtyChange }

  const notifyDirty = useCallback((next: boolean) => {
    dirtyRef.current = next
    setDirty(next)
    const { field, writes, onDirtyChange } = latest.current
    const pending = next || savingRef.current
    writes.setFieldDirty(field.key, pending)
    onDirtyChange(field.key, pending)
  }, [])
  const clearTimer = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = undefined
  }, [])
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      clearTimer()
    }
  }, [clearTimer])

  useEffect(() => {
    if (observedServer.current.snapshot !== serverSnapshot || observedServer.current.revision !== writes.revision) {
      observedServer.current = { snapshot: serverSnapshot, revision: writes.revision }
      deferredServer.current = { draft: fromResponse(latest.current.response), revision: writes.revision }
    }
    if (dirtyRef.current || savingRef.current || !deferredServer.current) return
    current.current = deferredServer.current.draft
    acknowledged.current = JSON.stringify(toPayload(latest.current.field, current.current))
    deferredServer.current = null
    setDraft(current.current)
  }, [serverSnapshot, writes.revision, dirty, saving])

  const change = (patch: Partial<Draft>) => {
    current.current = { ...current.current, ...patch }
    setDraft(current.current)
    setLocalError('')
    notifyDirty(uncertain.current || JSON.stringify(toPayload(field, current.current)) !== acknowledged.current)
  }
  const saveNow = useCallback(async () => {
    clearTimer()
    const { field, editable, writes } = latest.current
    if (!mounted.current || !editable || !dirtyRef.current || savingRef.current || writes.pauseReason) return
    const captured = toPayload(field, current.current)
    if (field.type === 'number' && !current.current.reason.trim() && current.current.value !== '' && !Number.isFinite(Number(current.current.value))) {
      setLocalError('Enter a valid number.')
      return
    }
    savingRef.current = true
    setSaving(true)
    const saved = await writes.saveField(field.key, captured, () => mounted.current && latest.current.editable)
    if (!mounted.current) return
    savingRef.current = false
    setSaving(false)
    if (saved) {
      uncertain.current = false
      acknowledged.current = JSON.stringify(captured)
      if (deferredServer.current && deferredServer.current.revision <= saved.revision)
        deferredServer.current = null
    } else uncertain.current = true
    notifyDirty(uncertain.current || JSON.stringify(toPayload(field, current.current)) !== acknowledged.current)
  }, [clearTimer, notifyDirty])

  useEffect(() => {
    if (editable && dirty && !saving && !writes.pauseReason && !localError)
      timer.current = setTimeout(() => { void saveNow() }, 800)
    return clearTimer
  }, [draft, dirty, editable, saving, writes.pauseReason, writes.resumeVersion, localError, saveNow, clearTimer])

  const useLatest = () => {
    clearTimer()
    const next = fromResponse(response)
    uncertain.current = false
    deferredServer.current = null
    current.current = next
    acknowledged.current = JSON.stringify(toPayload(field, next))
    setDraft(next)
    setLocalError('')
    notifyDirty(false)
  }
  const retry = () => {
    writes.resumeWrites()
  }
  const state = writes.conflicted && dirty ? 'conflict'
    : (writes.pauseReason === 'error' && dirty) || localError ? 'error'
      : saving ? 'saving' : dirty ? 'dirty' : 'saved'
  return { ...draft, dirty, saving, state, localError, change, saveNow, useLatest, retry } as const
}
