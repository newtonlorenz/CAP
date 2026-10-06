import { useRef } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Keep successive quick-filter updates together, including back/forward navigation. */
export function useReviewLocation() {
  const [params, setParams] = useSearchParams()
  const latest = useRef(params)
  latest.current = params
  const update = (changes: Record<string, string | null>, replace = true) => {
    const next = new URLSearchParams(latest.current)
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null || value === '' || value === 'all') next.delete(key)
      else next.set(key, value)
    })
    latest.current = next
    setParams(next, { replace, preventScrollReset: true })
  }
  return { params, update }
}
