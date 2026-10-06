import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Modal from './ui/Modal'

export default function NavigationSearch({ items }: { items: { path: string; label: string; section: string; aliases?: string[] }[] }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const list = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const matches = items.filter((item) => `${item.label} ${item.section} ${(item.aliases || []).join(' ')}`.toLowerCase().includes(query.toLowerCase().trim()))
  const go = (path: string) => { setOpen(false); navigate(path) }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        if (document.querySelector('[role="dialog"]:not([aria-label="Go to a page"])')) return
        event.preventDefault(); setOpen((value) => !value); setQuery(''); setActive(0)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' }) }, [active])
  return <>
    <button type="button" className="page-search" onClick={() => { setOpen(true); setQuery(''); setActive(0) }} aria-label="Find a page">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
      <span>Find a page…</span><kbd>⌘ K</kbd>
    </button>
    <Modal open={open} title="Go to a page" description="Search the workspace navigation." onClose={() => setOpen(false)}>
      <input data-autofocus="true" role="combobox" aria-expanded="true" aria-controls="page-results" aria-autocomplete="list"
        aria-activedescendant={matches[active] ? `page-result-${active}` : undefined}
        aria-label="Search pages" value={query} placeholder="Licence Applications, Certifications, teams…"
        className="w-full px-3 py-3 text-sm" onChange={(event) => { setQuery(event.target.value); setActive(0) }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault(); setActive((value) => matches.length ? (value + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length : 0)
          } else if (event.key === 'Enter' && matches[active]) { event.preventDefault(); go(matches[active].path) }
        }} />
      <div ref={list} id="page-results" role="listbox" aria-label="Pages" className="mt-3 max-h-72 overflow-y-auto">
        {matches.map((item, index) => <div key={item.path} id={`page-result-${index}`} role="option" aria-selected={index === active}
          onMouseDown={(event) => event.preventDefault()} onClick={() => go(item.path)}
          className={`flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-3 text-sm ${index === active ? 'bg-brand-soft text-accent' : 'text-ink hover:bg-subtle'}`}>
          <span className="font-semibold">{item.label}</span><span className="text-xs text-muted">{item.section}</span>
        </div>)}
      </div>
      {!matches.length && <p role="status" className="py-4 text-sm text-muted">No pages match “{query}”. Try a different name.</p>}
      <p className="mt-4 text-xs text-muted">Arrow keys to choose · Enter to open · Escape to close</p>
    </Modal>
  </>
}
