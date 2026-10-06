import { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import type { User } from '../types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
  refreshUser: () => Promise<void>
  sessionError: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const identityGeneration = useRef(0)

  useEffect(() => {
    fetchUser()
  }, [])

  const fetchUser = async () => {
    const generation = identityGeneration.current
    try {
      // Use /auth/me instead of /users/me to avoid some privacy/adblock rules
      // that block requests matching `/users/me`.
      const response = await api.get<User>('/auth/me')
      if (generation === identityGeneration.current) setUser(response.data)
    } catch {
      if (generation === identityGeneration.current) setUser(null)
    } finally {
      if (generation === identityGeneration.current) setIsLoading(false)
    }
  }

  const login = async (email: string, password: string) => {
    identityGeneration.current += 1
    setSessionError(null)
    setUser(null)
    await queryClient.cancelQueries()
    queryClient.clear()
    await api.post('/auth/login', { email, password })
    await fetchUser()
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
      identityGeneration.current += 1
      await queryClient.cancelQueries()
      queryClient.clear()
      setUser(null)
      setSessionError(null)
    } catch {
      setSessionError('Sign out failed. Check your connection and try again; this session is still signed in.')
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser: fetchUser, sessionError, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
