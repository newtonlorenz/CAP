import { useEffect, useRef, useState } from 'react'
import { getApiErrorMessage } from '../../api/errors'

type SaveState = 'saved' | 'dirty' | 'saving' | 'error'
type Entry<T> = { value: T; saved: T; saving: boolean; state: SaveState; error?: string; timer?: number }
const same = <T,>(left: T, right: T) => JSON.stringify(left) === JSON.stringify(right)

type Session<T> = { id: string | undefined; active: boolean; entries: Record<string, Entry<T>> }

/** Autosave source fields in order, retaining the latest text until the server acknowledges it. */
export function useSourceDrafts<T extends Record<string, string>>({
  scopeId, originals, normalise, validate, persist,
}: {
  scopeId: string | undefined
  originals: Record<string, T>
  normalise: (draft: T) => T
  validate: (draft: T) => string | undefined
  persist: (id: string, draft: T) => Promise<void>
}) {
  const [, refresh] = useState(0)
  const session = useRef<Session<T>>({ id: scopeId, active: true, entries: {} })
  if (session.current.id !== scopeId) {
    session.current.active = false
    Object.values(session.current.entries).forEach((entry) => window.clearTimeout(entry.timer))
    session.current = { id: scopeId, active: true, entries: {} }
  }
  const owner = session.current
  const config = useRef({ originals, normalise, validate, persist })
  config.current = { originals, normalise, validate, persist }
  const publish = () => {
    if (owner.active && session.current === owner) refresh((version) => version + 1)
  }

  const save = async (id: string, retry = false) => {
    const entry = owner.entries[id]
    if (!entry || !owner.active || session.current !== owner) return
    window.clearTimeout(entry.timer)
    if (entry.saving || (entry.state === 'error' && !retry)) return
    let needsConfirmation = retry && entry.state === 'error'
    entry.error = undefined
    // A newer edit is picked up after each response; requests for one row never overlap.
    while (owner.active && session.current === owner) {
      const snapshot = config.current.normalise(entry.value)
      if (!needsConfirmation && same(snapshot, entry.saved)) { entry.state = 'saved'; publish(); return }
      const error = config.current.validate(snapshot)
      if (error) { entry.state = 'error'; entry.error = error; publish(); return }
      entry.saving = true
      entry.state = 'saving'
      publish()
      try {
        await config.current.persist(id, snapshot)
        if (!owner.active || session.current !== owner) return
        entry.saved = snapshot
        needsConfirmation = false
      } catch (error) {
        if (!owner.active || session.current !== owner) return
        entry.state = 'error'
        entry.error = getApiErrorMessage(error, 'Your draft is still here. Retry saving when you are ready.')
        return
      } finally {
        entry.saving = false
        publish()
      }
    }
  }

  const update = (id: string, patch: Partial<T>) => {
    const initial = config.current.originals[id]
    if (!initial && !owner.entries[id]) return
    const entry = owner.entries[id] ||= {
      value: initial, saved: config.current.normalise(initial), saving: false, state: 'saved',
    }
    entry.value = { ...entry.value, ...patch }
    window.clearTimeout(entry.timer)
    // A failed request needs an explicit retry, including when the user keeps typing.
    if (entry.state !== 'error') {
      entry.state = entry.saving ? 'saving' : same(config.current.normalise(entry.value), entry.saved) ? 'saved' : 'dirty'
      if (entry.state === 'dirty') entry.timer = window.setTimeout(() => { void save(id) }, 800)
    }
    publish()
  }

  // Stop protecting an acknowledged value once a refetch has caught up. Future remote
  // updates can then appear normally; stale refetches cannot replace a local draft.
  useEffect(() => {
    let changed = false
    for (const [id, entry] of Object.entries(owner.entries)) {
      const incoming = originals[id]
      if (!incoming || entry.saving || entry.state !== 'saved') continue
      if (same(normalise(incoming), entry.saved) && same(normalise(entry.value), entry.saved)) {
        window.clearTimeout(entry.timer)
        delete owner.entries[id]
        changed = true
      }
    }
    if (changed) refresh((version) => version + 1)
  }, [owner, originals, normalise])

  useEffect(() => {
    owner.active = true
    return () => {
      owner.active = false
      Object.values(owner.entries).forEach((entry) => window.clearTimeout(entry.timer))
    }
  }, [owner])

  const hasUnsavedChanges = Object.values(owner.entries).some((entry) => entry.state !== 'saved')
  return {
    drafts: Object.fromEntries(Object.entries(owner.entries).map(([id, entry]) => [id, entry.value])) as Record<string, T>,
    state: (id: string): SaveState => owner.entries[id]?.state || 'saved',
    error: (id: string) => owner.entries[id]?.error,
    update, save,
    hasUnsavedChanges,
  }
}
