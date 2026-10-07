import { useEffect, useRef, useState } from 'react'
import PilotIcon from '../preparation/PilotIcon'
import type { LicenceApplication } from '../../types/applications'
import Button from '../ui/Button'

export default function PackContents({ pack, currentCaseId, onOpenCase, onOpenContents }: {
  pack: LicenceApplication; currentCaseId?: string; onOpenCase: (caseId: string) => void; onOpenContents: () => void
}) {
  const [open, setOpen] = useState(false)
  const [attention, setAttention] = useState(false)
  const [search, setSearch] = useState('')
  const rail = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    rail.current?.querySelector<HTMLElement>('button')?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false) }
      if (event.key !== 'Tab') return
      const targets = Array.from(rail.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href]') || [])
      const first = targets[0], last = targets[targets.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); previous?.focus() }
  }, [open])
  const required = pack.components.filter(item => item.required).length
  const optional = pack.components.length - required
  const items = pack.components.filter(item => (!attention || (item.included && !item.ready)) && item.name.toLowerCase().includes(search.toLowerCase()))
  return <>
    <Button className="pilot-pack-toggle" aria-expanded={open} onClick={() => setOpen(!open)}><PilotIcon name="file" size={20} />Pack contents · {required} required, {optional} optional</Button>
    {open && <button type="button" className="pilot-drawer-backdrop" aria-label="Close pack contents" onClick={() => setOpen(false)} />}
    <aside ref={rail} role={open ? 'dialog' : undefined} aria-modal={open ? true : undefined} className={`pilot-pack-rail ${open ? 'is-open' : ''}`} aria-label="Pack contents">
      <div className="flex items-start justify-between gap-2"><div><h2>Pack contents</h2><p>{required} required · {optional} optional</p></div><Button className="pilot-drawer-close" variant="ghost" aria-label="Close pack contents" onClick={() => setOpen(false)}><PilotIcon name="close" size={20} /></Button></div>
      <label className="pilot-attention-filter"><input type="checkbox" checked={attention} onChange={event => setAttention(event.target.checked)} />Needs attention only</label>
      <label className="pilot-pack-search"><PilotIcon name="search" size={17} /><input type="search" aria-label="Find pack content" placeholder="Find a form or document" value={search} onChange={event => setSearch(event.target.value)} /></label>
      {[true, false].map(isRequired => <section key={String(isRequired)}><h3>{isRequired ? 'Required' : 'Optional'}</h3><ul>{items.filter(item => item.required === isRequired).map(item => {
        const pending = item.blockers.filter(blocker => blocker.code === 'pending_acceptance').length
        return <li key={item.id}><button type="button" aria-current={item.case_id === currentCaseId ? 'page' : undefined} className={item.case_id === currentCaseId ? 'is-selected' : ''} onClick={() => { setOpen(false); if (item.case_id) onOpenCase(item.case_id); else onOpenContents() }}><PilotIcon name="file" size={24} /><span className="pilot-pack-item-title">{item.name}<small><i className={item.included && item.ready ? 'pilot-dot ready' : item.included ? 'pilot-dot pending' : 'pilot-dot'} />{!item.included ? 'Excluded' : item.ready ? 'Ready · Included' : pending ? `${pending} ${pending === 1 ? 'answer needs' : 'answers need'} acceptance` : 'Included · Needs attention'}</small></span></button></li>
      })}</ul></section>)}
      {!items.length && <p className="text-sm">No pack contents match these filters.</p>}
      <Button variant="ghost" onClick={onOpenContents}>Manage pack contents</Button>
    </aside>
  </>
}
