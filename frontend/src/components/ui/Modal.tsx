import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../utils/cn'
import IconButton from './IconButton'
import { getFocusable } from './focus'

const dialogStack: HTMLElement[] = []
let bodyWasLocked = false

export default function Modal({ open, title, description, onClose, children, footer, size = 'md' }: {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const titleId = useId()
  const descriptionId = useId()
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    const panel = panelRef.current
    if (!open || !panel) return
    const previous = document.activeElement as HTMLElement | null
    if (!dialogStack.length) bodyWasLocked = document.body.classList.contains('overflow-hidden')
    dialogStack.push(panel)
    document.body.classList.add('overflow-hidden')
    const focusables = getFocusable(panel)
    ;(focusables.find((element) => element.hasAttribute('data-autofocus')) || focusables[0] || panel).focus({ preventScroll: true })

    const onKeyDown = (event: KeyboardEvent) => {
      if (dialogStack[dialogStack.length - 1] !== panel || event.defaultPrevented) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
      } else if (event.key === 'Tab') {
        const elements = getFocusable(panel)
        const first = elements[0] || panel
        const last = elements[elements.length - 1] || panel
        const active = document.activeElement
        if (!panel.contains(active) || active === panel || (event.shiftKey ? active === first : active === last)) {
          event.preventDefault()
          ;(event.shiftKey ? last : first).focus()
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      const wasTop = dialogStack[dialogStack.length - 1] === panel
      const index = dialogStack.indexOf(panel)
      if (index >= 0) dialogStack.splice(index, 1)
      if (!dialogStack.length && !bodyWasLocked) document.body.classList.remove('overflow-hidden')
      if (wasTop && previous?.isConnected && (!dialogStack.length || dialogStack[dialogStack.length - 1]?.contains(previous))) previous.focus({ preventScroll: true })
    }
  }, [open])

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      <div className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm" aria-hidden="true" onMouseDown={onClose} />
      <div ref={panelRef} role="dialog" aria-modal="true" aria-label={title} aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined} tabIndex={-1}
        className={cn('relative flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-2xl bg-elevated shadow-[var(--elevation)]', size === 'lg' ? 'max-w-2xl' : size === 'sm' ? 'max-w-sm' : 'max-w-md')}
        onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="break-words text-lg font-semibold text-ink">{title}</h2>
            {description && <p id={descriptionId} className="mt-1 text-sm text-muted">{description}</p>}
          </div>
          <IconButton onClick={onClose} aria-label="Close dialog"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-5 w-5" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg></IconButton>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain px-5 py-5">{children}</div>
        {footer && <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-line px-5 py-4">{footer}</div>}
      </div>
    </div>, document.body
  )
}
