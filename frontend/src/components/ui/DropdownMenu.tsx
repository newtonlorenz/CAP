import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../utils/cn'
import IconButton from './IconButton'

export type DropdownItem = {
  key: string
  label: string
  onSelect: () => void
  disabled?: boolean
  tone?: 'default' | 'destructive'
}

export default function DropdownMenu({ ariaLabel = 'Row actions', items, align = 'right', disabled }: {
  ariaLabel?: string
  items: DropdownItem[]
  align?: 'left' | 'right'
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0, maxHeight: 400 })
  const containerRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const startAtEnd = useRef(false)
  const menuId = useId()
  const trigger = () => containerRef.current?.querySelector<HTMLButtonElement>('button')
  const close = () => { setOpen(false); trigger()?.focus({ preventScroll: true }) }

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const anchor = trigger()?.getBoundingClientRect()
      const menu = menuRef.current
      if (!anchor || !menu) return
      const margin = 8
      const below = innerHeight - anchor.bottom - margin * 2
      const above = anchor.top - margin * 2
      const upwards = below < menu.scrollHeight && above > below
      const maxHeight = Math.max(40, upwards ? above : below)
      const height = Math.min(menu.scrollHeight, maxHeight)
      setPosition({
        left: Math.max(margin, Math.min(align === 'right' ? anchor.right - menu.offsetWidth : anchor.left, innerWidth - menu.offsetWidth - margin)),
        top: Math.max(margin, upwards ? anchor.top - height - margin : anchor.bottom + margin),
        maxHeight,
      })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true) }
  }, [open, align, items])

  useEffect(() => {
    if (!open) return
    const onOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node) && !menuRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const enabled = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])
    ;(startAtEnd.current ? enabled[enabled.length - 1] : enabled[0])?.focus({ preventScroll: true })
    document.addEventListener('mousedown', onOutside)
    return () => document.removeEventListener('mousedown', onOutside)
  }, [open])

  return <div ref={containerRef} className="inline-flex" onClick={(event) => event.stopPropagation()}>
    <IconButton aria-label={ariaLabel} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => { startAtEnd.current = false; setOpen((value) => !value) }} disabled={disabled}
      onKeyDown={(event) => {
        if (open && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return }
        if (open && event.key === 'Tab') setOpen(false)
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); startAtEnd.current = event.key === 'ArrowUp'; setOpen(true) }
      }}>
      <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5" aria-hidden="true"><circle cx="10" cy="4" r="1.5" /><circle cx="10" cy="10" r="1.5" /><circle cx="10" cy="16" r="1.5" /></svg>
    </IconButton>
    {open && createPortal(<div ref={menuRef} id={menuId} role="menu" aria-label={ariaLabel} style={position}
      className="fixed z-[60] w-48 max-w-[calc(100vw-1rem)] overflow-y-auto overscroll-contain rounded-xl bg-elevated py-1 shadow-[var(--elevation)] ring-1 ring-line"
      onKeyDown={(event) => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return }
        if (event.key === 'Tab') { close(); return }
        const buttons = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])
        if (!buttons.length) return
        const index = buttons.findIndex((button) => button === document.activeElement)
        const key = event.key
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) {
          event.preventDefault()
          buttons[key === 'Home' ? 0 : key === 'End' ? buttons.length - 1 : (index + (key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus()
        }
      }}>
      {items.map((item, index) => <div key={item.key}>
        {item.tone === 'destructive' && items.findIndex((entry) => entry.tone === 'destructive') === index && <div className="my-1 border-t border-line" aria-hidden="true" />}
        <button type="button" role="menuitem" tabIndex={-1} disabled={item.disabled}
          onClick={() => { close(); item.onSelect() }}
          className={cn('flex w-full items-center px-3 py-2 text-left text-sm', item.tone === 'destructive' ? 'text-danger hover:bg-danger-soft' : 'text-ink hover:bg-canvas', item.disabled && 'opacity-50')}>
          {item.label}
        </button>
      </div>)}
    </div>, document.body)}
  </div>
}
