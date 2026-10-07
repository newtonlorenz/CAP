import { flushSync } from 'react-dom'
import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { accessApi } from '../../api/access'
import { getApiErrorMessage } from '../../api/errors'
import { useAuth } from '../../contexts/AuthContext'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import type { UserMention } from '../../types'
import type { AccessTeam } from '../../types/access'
import { Field, inputClass } from '../applications/Fields'
import Button from '../ui/Button'

export default function TeamsPanel({ users, usersLoading = false, usersError = false }: {
  users: UserMention[]; usersLoading?: boolean; usersError?: boolean
}) {
  const { user } = useAuth()
  const teams = useQuery({ queryKey: ['access', 'teams'], queryFn: accessApi.teams })
  const [params, setParams] = useSearchParams()
  const selected = params.get('team') || ''
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const available = !usersLoading && !usersError && users.length > 0
  const team = teams.data?.find(item => item.id === selected)
  const editing = dismissed !== selected && (selected === 'new' || team?.owner_id === user?.id)
  const choose = (id: string) => {
    setDismissed(null)
    setParams(current => { const next = new URLSearchParams(current); next.set('team', id); return next })
  }
  const close = () => {
    setDismissed(selected)
    setParams(current => { const next = new URLSearchParams(current); next.delete('team'); return next }, { replace: true })
  }
  const visible = teams.data?.filter(item => item.name.toLowerCase().includes(search.trim().toLowerCase())) || []
  return <section data-tour="teams-list" className="space-y-5" aria-label="Access teams">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Your teams</h2><p className="mt-1 text-sm text-muted">Manage membership for the teams you own.</p></div><Button variant="primary" disabled={!available || teams.isLoading || teams.isError} onClick={() => choose('new')}>New team</Button></div>
    <p className="max-w-prose text-sm text-muted">Adding a member shares every resource granted to that team. Only its owner can change membership; account administrators cannot add themselves to another owner's team.</p>
    {users.length >= 1000 && <p className="text-sm text-warning">Showing the first 1,000 active people. Search applies to this list; existing team members outside it remain included.</p>}
    {usersLoading && <p role="status" className="text-sm text-muted">Loading people…</p>}
    {(usersError || (!usersLoading && !users.length)) && <p role="alert" className="text-sm text-danger">People are unavailable. Reload the page before saving team membership.</p>}
    {teams.isLoading ? <p role="status">Loading teams…</p> : teams.isError ? <p role="alert" className="text-danger">Teams could not be loaded. <Button size="sm" onClick={() => void teams.refetch()}>Retry</Button></p> : <>
      <label className="block max-w-md text-sm font-medium">Find a team<input type="search" className={`${inputClass} mt-1`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search team names" /></label>
      <p className="text-xs text-muted">{visible.length} of {teams.data?.length || 0} teams</p>
      <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line bg-surface" aria-label="Teams">
        {visible.map(item => <li key={item.id} className={`flex items-center justify-between gap-3 px-4 py-3 ${item.id === selected ? 'bg-brand-soft' : ''}`}>
          <div className="min-w-0"><h3 className="break-words font-semibold">{item.name}</h3><p className="mt-1 text-xs text-muted">{item.member_ids.length} members · {item.owner_id === user?.id ? 'You own this team' : 'managed by its owner'}</p></div>
          {item.owner_id === user?.id && <Button size="sm" aria-label={`Edit ${item.name}`} onClick={() => choose(item.id)}>Edit</Button>}
        </li>)}
        {!visible.length && <li className="px-4 py-6 text-sm text-muted">{teams.data?.length ? 'No teams match this search.' : 'No teams yet. Create one to share access with a group.'}</li>}
      </ul>
      {selected && selected !== 'new' && !team && <p role="alert" className="text-sm text-danger">This team is unavailable. Choose another team.</p>}
    </>}
    {editing && user && <TeamEditor key={selected} team={team} ownerId={team?.owner_id || user.id} users={users} available={available} onCancel={close} />}
  </section>
}

function TeamEditor({ team, ownerId, users, available, onCancel }: {
  team?: AccessTeam; ownerId: string; users: UserMention[]; available: boolean; onCancel: () => void
}) {
  const [baseline] = useState(team)
  const initialMembers = [...new Set([...(baseline?.member_ids || []), ownerId])]
  const [name, setName] = useState(team?.name || '')
  const [members, setMembers] = useState(initialMembers)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const dirty = name !== (baseline?.name || '') || [...members].sort().join(',') !== [...initialMembers].sort().join(',')
  useDraftNavigationGuard(!saved && (dirty || busy))
  const candidates = [...users, ...initialMembers.filter(id => !users.some(person => person.id === id)).map(id => ({ id, full_name: id === ownerId ? 'Team owner' : 'Current member', email: '' }))]
  const filtered = candidates.filter(person => `${person.full_name} ${person.email}`.toLowerCase().includes(search.trim().toLowerCase()))
  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (!available || !name.trim() || busy) return
    setBusy(true); setError('')
    try {
      const member_ids = [...new Set([...members, ownerId])]
      const persisted = team
        ? await accessApi.updateTeam(team.id, { name: name.trim(), member_ids, expected_revision: baseline!.revision })
        : await accessApi.createTeam({ name: name.trim(), member_ids })
      // Restore the saved team after refreshing permissions and all resource caches.
      const nextUrl = new URL(window.location.href)
      nextUrl.searchParams.set('team', persisted.id)
      window.history.replaceState(window.history.state, '', nextUrl)
      // Complete the draft registration before a full-document reload.
      flushSync(() => { setSaved(true); setBusy(false) })
      // Let the provider's pending-draft update commit and remove its unload listener.
      requestAnimationFrame(() => requestAnimationFrame(() => window.location.reload()))
    } catch (caught) { setError(getApiErrorMessage(caught, 'The team could not be saved. Your changes are retained; reload to check for a newer revision.')); setBusy(false) }
  }
  return <form className="space-y-4 rounded-lg border border-line bg-surface p-5" onSubmit={save} aria-label={team ? `Edit ${team.name}` : 'New team'}>
    <h3 className="text-lg font-semibold">{team ? `Edit ${team.name}` : 'New team'}</h3>
    <fieldset disabled={busy} className="space-y-4">
      <Field label="Team name"><input required maxLength={200} className={inputClass} value={name} onChange={event => setName(event.target.value)} /></Field>
      <div className="space-y-2"><div className="flex items-center justify-between gap-3"><h4 className="text-sm font-semibold">Team members</h4><span className="text-xs text-muted">{members.length} selected</span></div>
        <label className="block text-sm">Find a person<input type="search" className={`${inputClass} mt-1`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search names or email addresses" disabled={!available} /></label>
        <fieldset disabled={!available} className="max-h-64 overflow-y-auto rounded-md border border-line" aria-label="Choose team members">
          {filtered.map(person => <label key={person.id} className="flex items-center gap-3 border-b border-line px-3 py-3 text-sm last:border-b-0"><input type="checkbox" checked={members.includes(person.id)} disabled={person.id === ownerId} onChange={event => setMembers(current => event.target.checked ? [...current, person.id] : current.filter(id => id !== person.id))} /><span className="min-w-0 break-words">{person.full_name}{person.id === ownerId && <span className="ml-2 text-xs text-muted">Owner · always included</span>}{person.email && <span className="block text-xs text-muted">{person.email}</span>}</span></label>)}
          {!filtered.length && <p className="p-4 text-sm text-muted">No people match this search. Selected members are retained.</p>}
        </fieldset>
      </div>
      <div className="flex flex-wrap gap-3"><Button type="submit" variant="primary" disabled={!available || !name.trim() || (Boolean(team) && !dirty)}>{team ? 'Save membership' : 'Create team'}</Button><Button type="button" onClick={onCancel}>Cancel</Button></div>
    </fieldset>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </form>
}
