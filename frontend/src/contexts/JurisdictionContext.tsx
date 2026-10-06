import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import type { Jurisdiction, PaginatedResponse } from '../types'
import { useAuth } from './AuthContext'

type JurisdictionContextType = {
  jurisdictionId: string | null
  jurisdictions: Jurisdiction[]
  jurisdictionById: Record<string, Jurisdiction>
  isLoading: boolean
  error: string | null
  retry: () => void
  setJurisdictionId: (next: string) => void
  registerChangeGuard: (guard: () => boolean) => () => void
}

const STORAGE_KEY = 'cap:jurisdictionId'

const JurisdictionContext = createContext<JurisdictionContextType | undefined>(undefined)

export function JurisdictionProvider({ children }: { children: ReactNode }) {
  const changeGuards = useRef(new Set<() => boolean>())
  const registerChangeGuard = useCallback((guard: () => boolean) => {
    changeGuards.current.add(guard)
    return () => { changeGuards.current.delete(guard) }
  }, [])
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth()
  const [jurisdictionId, setJurisdictionIdState] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null
    try { return window.localStorage.getItem(STORAGE_KEY) } catch { return null }
  })

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['jurisdictions', 'active', user?.id],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<Jurisdiction>>(
        '/jurisdictions?limit=1000'
      )
      return response.data
    },
    enabled: isAuthenticated && !isAuthLoading,
    staleTime: 1000 * 60 * 5,
    retry: false,
  })

  const jurisdictions = useMemo(() => data?.items ?? [], [data?.items])
  const jurisdictionById = useMemo(() => {
    const map: Record<string, Jurisdiction> = {}
    jurisdictions.forEach((j) => {
      map[j.id] = j
    })
    return map
  }, [jurisdictions])

  const setJurisdictionId = useCallback((next: string) => {
    if (next !== jurisdictionId && [...changeGuards.current].some((guard) => !guard())) return
    setJurisdictionIdState(next)
    if (typeof window !== 'undefined') {
      try { window.localStorage.setItem(STORAGE_KEY, next) } catch { /* Keep the in-memory selection. */ }
    }
  }, [jurisdictionId])

  useEffect(() => {
    if (!isAuthenticated || isAuthLoading) return
    if (isLoading || isError) return
    if (!jurisdictions.length) {
      setJurisdictionIdState(null)
      if (typeof window !== 'undefined') {
        try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* Storage may be unavailable. */ }
      }
      return
    }
    if (!jurisdictionId || !jurisdictionById[jurisdictionId]) {
      setJurisdictionId(jurisdictions[0].id)
    }
  }, [isAuthenticated, isAuthLoading, isLoading, isError, jurisdictions, jurisdictionById, jurisdictionId, setJurisdictionId])

  // Clear selected jurisdiction on logout.
  useEffect(() => {
    if (isAuthLoading) return
    if (isAuthenticated) return
    setJurisdictionIdState(null)
    if (typeof window !== 'undefined') {
      try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* Storage may be unavailable. */ }
    }
  }, [isAuthenticated, isAuthLoading])

  return (
    <JurisdictionContext.Provider
      value={{
        jurisdictionId,
        jurisdictions,
        jurisdictionById,
        isLoading,
        error: isError ? 'Jurisdictions could not be loaded. Check your connection and try again.' : null,
        retry: () => { void refetch() },
        setJurisdictionId,
        registerChangeGuard,
      }}
    >
      {children}
    </JurisdictionContext.Provider>
  )
}

export function useJurisdiction() {
  const context = useContext(JurisdictionContext)
  if (context === undefined) {
    throw new Error('useJurisdiction must be used within a JurisdictionProvider')
  }
  return context
}
