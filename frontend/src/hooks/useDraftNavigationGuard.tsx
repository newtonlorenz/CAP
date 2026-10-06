import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState, type ReactNode } from 'react'
import { useBlocker } from 'react-router-dom'
import ConfirmDialog from '../components/ui/ConfirmDialog'

const DraftNavigationContext = createContext<((id: string, pending: boolean) => void) | null>(null)

/** One blocker for the whole workspace, including browser Back and search-param navigation. */
export function DraftNavigationProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Set<string>>(() => new Set())
  const register = useCallback((id: string, active: boolean) => {
    setPending((current) => {
      if (current.has(id) === active) return current
      const next = new Set(current)
      if (active) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])
  const hasChanges = pending.size > 0
  const shouldBlock = useCallback(({ currentLocation, nextLocation }: { currentLocation: { pathname: string; search: string }; nextLocation: { pathname: string; search: string } }) =>
    hasChanges && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search), [hasChanges])
  const blocker = useBlocker(shouldBlock)
  useEffect(() => {
    if (blocker.state === 'blocked' && !hasChanges) blocker.proceed()
  }, [blocker, hasChanges])
  useEffect(() => {
    if (!hasChanges) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [hasChanges])
  return <DraftNavigationContext.Provider value={register}>
    {children}
    <ConfirmDialog open={blocker.state === 'blocked' && hasChanges} title="Changes are not saved yet"
      description="Stay here to finish saving or resolve any errors. You will continue automatically once all changes are saved. Leaving now may discard unsaved changes; a save already sent may still complete."
      confirmLabel="Leave with unsaved changes" onConfirm={() => { if (blocker.state === 'blocked') blocker.proceed() }}
      onClose={() => { if (blocker.state === 'blocked') blocker.reset() }} />
  </DraftNavigationContext.Provider>
}

export function useDraftNavigationGuard(active: boolean) {
  const register = useContext(DraftNavigationContext)
  const id = useId()
  // Editors can also render in an embedded/test router without owning navigation.
  const registration = useMemo(() => register ? (pending: boolean) => register(id, pending) : null, [register, id])
  useEffect(() => {
    registration?.(active)
    return () => registration?.(false)
  }, [registration, active])
  return Boolean(register)
}
