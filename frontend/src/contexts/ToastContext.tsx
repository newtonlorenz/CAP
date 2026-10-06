import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type ToastKind = 'success' | 'error' | 'info'

export type Toast = {
  id: string
  kind: ToastKind
  title: string
  description?: string
  createdAt: number
  durationMs: number | null
}

export type ToastApi = {
  success: (title: string, opts?: { description?: string; durationMs?: number | null }) => void
  error: (title: string, opts?: { description?: string; durationMs?: number | null }) => void
  info: (title: string, opts?: { description?: string; durationMs?: number | null }) => void
  dismiss: (id: string) => void
  toasts: Toast[]
}

const ToastContext = createContext<ToastApi | null>(null)

const DEFAULT_DURATION_MS = 5000

function randomId() {
  // Not security-sensitive; just stable keys.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timeoutsRef = useRef(new Map<string, number>())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const handle = timeoutsRef.current.get(id)
    if (handle) {
      window.clearTimeout(handle)
      timeoutsRef.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (kind: ToastKind, title: string, opts?: { description?: string; durationMs?: number | null }) => {
      const id = randomId()
      const durationMs =
        opts?.durationMs === undefined ? DEFAULT_DURATION_MS : opts.durationMs
      const toast: Toast = {
        id,
        kind,
        title,
        description: opts?.description,
        createdAt: Date.now(),
        durationMs,
      }
      setToasts((prev) => [toast, ...prev].slice(0, 5))
      if (durationMs !== null) {
        const handle = window.setTimeout(() => dismiss(id), Math.max(0, durationMs))
        timeoutsRef.current.set(id, handle)
      }
    },
    [dismiss]
  )

  const api = useMemo<ToastApi>(
    () => ({
      success: (title, opts) => push('success', title, opts),
      error: (title, opts) => push('error', title, opts),
      info: (title, opts) => push('info', title, opts),
      dismiss,
      toasts,
    }),
    [dismiss, push, toasts]
  )

  return <ToastContext.Provider value={api}>{children}</ToastContext.Provider>
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return ctx
}

