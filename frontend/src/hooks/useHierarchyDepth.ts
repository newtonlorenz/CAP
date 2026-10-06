import { useCallback, useState } from 'react'

export type HierarchyLevels = number | 'all'
const STORAGE_KEY = 'cap:outline-levels'

function readLevels(): HierarchyLevels {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    const levels = Number(value)
    return value && Number.isSafeInteger(levels) && levels > 0 ? levels : 'all'
  } catch { return 'all' }
}

export function useHierarchyDepth() {
  const [levels, setLevels] = useState<HierarchyLevels>(readLevels)
  const changeLevels = useCallback((next: HierarchyLevels) => {
    setLevels(next)
    try { localStorage.setItem(STORAGE_KEY, String(next)) } catch { /* Keep the in-memory choice. */ }
  }, [])
  return { levels, changeLevels }
}
