import { useCallback, useEffect, useState } from 'react'
import type { ReviewItemWithRequirement } from '../../types'

type Options = {
  cycleId?: string
  userId?: string
  focused: boolean
  requestedItemId: string | null
  items: ReviewItemWithRequirement[]
  visibleItems: ReviewItemWithRequirement[]
  pendingItems: ReviewItemWithRequirement[]
  itemNeedsSave: (item: ReviewItemWithRequirement) => boolean
  updateLocation: (values: Record<string, string | null>, replace?: boolean) => void
}

function rememberedItem(key: string | null, value?: string | null): string | null {
  if (!key) return null
  try {
    if (value === null) window.sessionStorage.removeItem(key)
    else if (value !== undefined) window.sessionStorage.setItem(key, value)
    return window.sessionStorage.getItem(key)
  } catch {
    // A blocked browser store must not prevent reviewing or saving evidence.
    return null
  }
}

/** Keep focused navigation independent from assessment and evidence persistence. */
export function useReviewFocus(options: Options) {
  const { cycleId, userId, focused, requestedItemId, items, visibleItems, pendingItems, itemNeedsSave, updateLocation } = options
  const [notice, setNotice] = useState('')
  const key = cycleId && userId ? `cap:review-focus:${userId}:${cycleId}` : null
  const selected = visibleItems.find((item) => item.id === requestedItemId) || pendingItems[0] || visibleItems[0]
  const selectedIndex = visibleItems.findIndex((item) => item.id === selected?.id)
  const nextPending = !focused ? pendingItems[0] : pendingItems.find((item) =>
    visibleItems.findIndex((row) => row.id === item.id) > selectedIndex
  ) || pendingItems.find((item) => item.id !== selected?.id)

  const select = useCallback((itemId: string) => {
    if (selected && selected.id !== itemId && itemNeedsSave(selected)) {
      setNotice('Save this requirement before moving. Retry a failed save or save your evidence, then try again.')
      return
    }
    setNotice('')
    rememberedItem(key, itemId)
    updateLocation({ item: itemId, mode: 'focus' }, false)
    requestAnimationFrame(() => document.getElementById('review-workspace')?.scrollIntoView?.({ block: 'start' }))
  }, [selected, itemNeedsSave, key, updateLocation])

  useEffect(() => {
    if (!focused || requestedItemId || !selected) return
    const savedId = rememberedItem(key)
    const target = visibleItems.some((item) => item.id === savedId) ? savedId : selected.id
    if (savedId && !items.some((item) => item.id === savedId)) rememberedItem(key, null)
    updateLocation({ item: target })
  }, [focused, requestedItemId, selected, key, visibleItems, items, updateLocation])

  useEffect(() => {
    if (focused && requestedItemId && visibleItems.some((item) => item.id === requestedItemId)) {
      rememberedItem(key, requestedItemId)
    }
  }, [focused, requestedItemId, visibleItems, key])

  useEffect(() => {
    if (!focused) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
      const target = event.target
      if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      const targetId = event.key === 'ArrowRight' ? visibleItems[selectedIndex + 1]?.id
        : event.key === 'ArrowLeft' ? visibleItems[selectedIndex - 1]?.id
        : event.key.toLowerCase() === 'n' ? nextPending?.id : null
      if (!targetId) return
      event.preventDefault()
      select(targetId)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [focused, visibleItems, selectedIndex, nextPending, select])

  return { selected, selectedIndex, nextPending, select, notice }
}
