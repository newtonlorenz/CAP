import { cloneElement, useEffect, useId, useLayoutEffect, useRef, useState, type HTMLAttributes, type ReactElement } from 'react'
import { createPortal } from 'react-dom'

type TriggerProps = HTMLAttributes<HTMLElement> & { disabled?: boolean }

/** Supplemental help for a focusable trigger. Keep essential instructions visible. */
export default function Tooltip({ content, children, delay = 250 }: {
  content?: string
  children: ReactElement<TriggerProps>
  delay?: number
}) {
  const id = useId()
  const anchor = useRef<HTMLElement | null>(null)
  const bubble = useRef<HTMLDivElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const hovered = useRef(false)
  const focused = useRef(false)
  const dismissed = useRef(false)
  const touchInteraction = useRef(false)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)

  const clearTimer = () => clearTimeout(timer.current)
  const show = (element: HTMLElement, immediate = false) => {
    clearTimer()
    anchor.current = element
    if (!content || dismissed.current) return
    if (immediate) setOpen(true)
    else timer.current = setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    clearTimer()
    if (!hovered.current && !focused.current) {
      timer.current = setTimeout(() => { setOpen(false); setPosition(null) }, 100)
    }
  }

  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      dismissed.current = true
      clearTimer()
      setOpen(false)
      setPosition(null)
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [open])

  useLayoutEffect(() => {
    if (!open || !content) return
    const updatePosition = () => {
      if (!anchor.current || !bubble.current) return
      const target = anchor.current.getBoundingClientRect()
      const help = bubble.current.getBoundingClientRect()
      const viewportWidth = document.documentElement.clientWidth || window.innerWidth
      const viewportHeight = document.documentElement.clientHeight || window.innerHeight
      const left = Math.max(8, Math.min(target.left + (target.width - help.width) / 2, viewportWidth - help.width - 8))
      const preferredTop = target.top - help.height - 8
      const top = Math.max(8, Math.min(preferredTop >= 8 ? preferredTop : target.bottom + 8, viewportHeight - help.height - 8))
      setPosition({ left, top })
    }
    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(updatePosition) : null
    if (anchor.current) observer?.observe(anchor.current)
    if (bubble.current) observer?.observe(bubble.current)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
      observer?.disconnect()
    }
  }, [open, content])

  if (!content) return children

  const description = [children.props['aria-describedby'], open ? id : undefined].filter(Boolean).join(' ') || undefined
  const interactionProps: HTMLAttributes<HTMLElement> = {
    onPointerDown: (event) => {
      touchInteraction.current = event.pointerType === 'touch'
      if (touchInteraction.current) {
        clearTimer()
        setOpen(false)
        setPosition(null)
      }
    },
    onPointerEnter: (event) => {
      if (event.pointerType === 'touch') return
      hovered.current = true
      dismissed.current = false
      show(event.currentTarget)
    },
    onPointerLeave: () => { hovered.current = false; hide() },
    onFocus: (event) => {
      focused.current = true
      dismissed.current = false
      if (!touchInteraction.current) show(event.currentTarget, true)
    },
    onBlur: () => { focused.current = false; touchInteraction.current = false; hide() },
  }
  const trigger = children.props.disabled ? (
    <span className="ui-tooltip-disabled-trigger" tabIndex={0} role="group"
      aria-label={children.props['aria-label'] || (typeof children.props.children === 'string' ? children.props.children : undefined)} aria-describedby={description} {...interactionProps}>
      {cloneElement(children, { 'aria-describedby': description, style: { ...children.props.style, pointerEvents: 'none' } })}
    </span>
  ) : cloneElement(children, {
    'aria-describedby': description,
    onPointerDown: (event) => { children.props.onPointerDown?.(event); interactionProps.onPointerDown?.(event) },
    onPointerEnter: (event) => { children.props.onPointerEnter?.(event); interactionProps.onPointerEnter?.(event) },
    onPointerLeave: (event) => { children.props.onPointerLeave?.(event); interactionProps.onPointerLeave?.(event) },
    onFocus: (event) => { children.props.onFocus?.(event); interactionProps.onFocus?.(event) },
    onBlur: (event) => { children.props.onBlur?.(event); interactionProps.onBlur?.(event) },
  })

  return <>
    {trigger}
    {open && createPortal(
      <div ref={bubble} id={id} role="tooltip" className="ui-tooltip"
        style={{ left: position?.left ?? 0, top: position?.top ?? 0, visibility: position ? 'visible' : 'hidden' }}
        onPointerEnter={() => { hovered.current = true; clearTimer() }}
        onPointerLeave={() => { hovered.current = false; hide() }}>
        {content}
      </div>, document.body
    )}
  </>
}
