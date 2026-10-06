import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Tooltip from './ui/Tooltip'

type ResizableSplitViewProps = {
  storageKey: string
  defaultSidebarWidth: number
  minSidebarWidth?: number
  maxSidebarWidth?: number
  sidebar: React.ReactNode
  main: React.ReactNode
  className?: string
  sidebarClassName?: string
  mainClassName?: string
  handleClassName?: string
  collapseLabel?: string
  expandLabel?: string
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export default function ResizableSplitView({
  storageKey,
  defaultSidebarWidth,
  minSidebarWidth = 220,
  maxSidebarWidth = 520,
  sidebar,
  main,
  className,
  sidebarClassName,
  mainClassName,
  handleClassName,
  collapseLabel = 'Collapse sidebar',
  expandLabel = 'Expand sidebar',
}: ResizableSplitViewProps) {
  const widthKey = `${storageKey}:sidebarWidth`
  const collapsedKey = `${storageKey}:collapsed`

  const initial = useMemo(() => {
    const rawWidth = Number(localStorage.getItem(widthKey))
    const width = Number.isFinite(rawWidth) && rawWidth > 0 ? rawWidth : defaultSidebarWidth
    const collapsed = localStorage.getItem(collapsedKey) === '1'
    return { width: clamp(width, minSidebarWidth, maxSidebarWidth), collapsed }
  }, [collapsedKey, defaultSidebarWidth, maxSidebarWidth, minSidebarWidth, widthKey])

  const [sidebarWidth, setSidebarWidth] = useState(initial.width)
  const [collapsed, setCollapsed] = useState(initial.collapsed)
  const draggingRef = useRef(false)

  useEffect(() => {
    localStorage.setItem(widthKey, String(sidebarWidth))
  }, [sidebarWidth, widthKey])

  useEffect(() => {
    localStorage.setItem(collapsedKey, collapsed ? '1' : '0')
  }, [collapsed, collapsedKey])

  const setDraggingUi = (dragging: boolean) => {
    document.body.style.userSelect = dragging ? 'none' : ''
    document.body.style.cursor = dragging ? 'col-resize' : ''
  }

  useEffect(() => {
    return () => setDraggingUi(false)
  }, [])

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.preventDefault()
    draggingRef.current = true
    setDraggingUi(true)
    ;(event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId)
  }, [])

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return
      const next = clamp(sidebarWidth + event.movementX, minSidebarWidth, maxSidebarWidth)
      if (collapsed) setCollapsed(false)
      setSidebarWidth(next)
    },
    [collapsed, maxSidebarWidth, minSidebarWidth, sidebarWidth]
  )

  const onPointerUp = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    setDraggingUi(false)
    try {
      ;(event.currentTarget as HTMLDivElement).releasePointerCapture(event.pointerId)
    } catch {
      // Ignore if capture already released.
    }
  }, [])

  const toggleCollapsed = () => setCollapsed((prev) => !prev)

  const templateColumns = collapsed ? `0px 12px minmax(0, 1fr)` : `${sidebarWidth}px 12px minmax(0, 1fr)`

  return (
    <div className={className} style={{ display: 'grid', gridTemplateColumns: templateColumns }}>
      <aside className={sidebarClassName} style={{ overflow: collapsed ? 'hidden' : undefined }}>
        {!collapsed ? sidebar : null}
      </aside>

      <div
        className={handleClassName || 'relative'}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
      >
        <div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 rounded bg-line/90 hover:bg-brand-soft/90" />
        <Tooltip content={collapsed ? expandLabel : collapseLabel}><button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            toggleCollapsed()
          }}
          className="absolute top-4 left-1/2 -translate-x-1/2 rounded-full border border-line-strong bg-surface/90 px-1.5 py-1 text-[10px] font-semibold text-muted shadow-[0_10px_24px_-22px_rgba(15,23,42,0.8)] hover:border-brand-line hover:text-accent"
          aria-label={collapsed ? expandLabel : collapseLabel}
        >
          {collapsed ? '>' : '<'}
        </button></Tooltip>
      </div>

      <div className={mainClassName}>{main}</div>
    </div>
  )
}
