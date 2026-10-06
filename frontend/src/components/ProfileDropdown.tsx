import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import ThemeSwitcher from './ThemeSwitcher'

export default function ProfileDropdown() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const container = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  const initials = (user?.full_name || user?.email || '').split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase()

  useEffect(() => { setOpen(false) }, [location.pathname, location.search])
  useEffect(() => {
    if (!open) return
    const dismiss = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  const itemClass = 'flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-ink hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent'
  return <div ref={container} className="relative" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false)
  }}>
    <button ref={trigger} type="button" aria-label="Profile options" aria-expanded={open} aria-controls="profile-options"
      onClick={() => setOpen(value => !value)}
      onKeyDown={event => {
        if (event.key === 'ArrowDown') {
          event.preventDefault()
          setOpen(true)
          requestAnimationFrame(() => container.current?.querySelector<HTMLAnchorElement>('nav a')?.focus())
        }
      }}
      className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-ink hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
      <span className="avatar" aria-hidden="true">{initials}</span>
      <span className="hidden max-w-36 truncate text-xs font-semibold md:block">{user?.full_name || user?.email}</span>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d={open ? 'm6 15 6-6 6 6' : 'm6 9 6 6 6-6'} /></svg>
    </button>
    {open && <div id="profile-options" className="absolute right-0 z-50 mt-2 w-72 max-w-[calc(100vw-2rem)] rounded-xl bg-surface p-2 shadow-lg ring-1 ring-line">
      <div className="border-b border-line px-3 py-3">
        <p className="break-words text-sm font-semibold text-ink">{user?.full_name}</p>
        <p className="mt-1 break-words text-xs text-muted">{user?.email}</p>
        <p className="mt-1 text-xs capitalize text-muted">{user?.role.replace(/_/g, ' ')}</p>
      </div>
      <nav aria-label="Profile options" className="py-1">
        <Link className={itemClass} to="/account?section=account">Account settings</Link>
        <Link className={itemClass} to="/account?section=notifications">Notification settings</Link>
      </nav>
      <div className="flex items-center justify-between border-y border-line px-3 py-3"><span className="text-sm text-muted">Appearance</span><ThemeSwitcher /></div>
      <button type="button" className={`${itemClass} mt-1 w-full text-danger disabled:opacity-50`} disabled={signingOut}
        onClick={async () => {
          setSigningOut(true)
          try { await logout() } finally { setSigningOut(false); setOpen(false) }
        }}>{signingOut ? 'Signing out…' : 'Logout'}</button>
    </div>}
  </div>
}
