import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { useState } from 'react'
import api from '../../api/client'
import Button from '../../components/ui/Button'
import LoadError from '../../components/ui/LoadError'
import { formatDate } from '../../utils/dateFormat'
import './overview.css'

type TeamItem = {
  id: string; kind: string; title: string; context: string; status: string;
  owner_id: string | null; owner_name: string | null; due_date: string | null;
  overdue: boolean; href: string; next_action?: string; action_label?: string;
}
type TeamWork = {
  items: TeamItem[]; total: number; skip: number; limit: number;
  counts: { total: number; overdue: number; unassigned: number; by_kind: Record<string, number> };
  people: { id: string | null; name: string; total: number; overdue: number }[];
  contexts?: string[];
}
const kinds: Record<string, string> = { requirement: 'Requirements', review: 'Requirement assessments', form: 'Forms', answer_review: 'Answer reviews', authority_query: 'Authority queries', change: 'Changes' }
const nextActions: Record<string, string> = { requirement: 'Review requirement', review: 'Open assessment', form: 'Continue form', answer_review: 'Review answer', authority_query: 'Respond to query', change: 'Open change' }

export default function TeamWorkPanel({ jurisdictionId }: { jurisdictionId: string }) {
  const [search, setSearch] = useSearchParams()
  const [comfortable, setComfortable] = useState(false)
  const page = Math.max(1, Number(search.get('team_page')) || 1)
  const attention = search.get('team_filter') || 'all'
  const owner = search.get('team_owner') || ''
  const kind = search.get('team_kind') || ''
  const context = search.get('team_context') || ''
  const requestedSort = search.get('team_sort') || search.get('team_group') || 'priority'
  const sort = ['programme', 'owner', 'priority'].includes(requestedSort) ? requestedSort : 'priority'
  const update = (values: Record<string, string>) => setSearch(previous => {
    const next = new URLSearchParams(previous)
    next.set('team_page', '1')
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
    return next
  })
  const query = useQuery({
    queryKey: ['team-work', jurisdictionId, page, attention, owner, kind, context, sort],
    queryFn: async () => (await api.get<TeamWork>('/dashboard/team-work', { params: {
      jurisdiction_id: jurisdictionId, skip: (page - 1) * 20, limit: 20,
      sort_by: sort, owner_id: owner || undefined, kind: kind || undefined, context: context || undefined,
      overdue: attention === 'overdue' || undefined, unassigned: attention === 'unassigned' || undefined,
    } })).data,
  })
  const data = query.data
  const items = data?.items ?? []
  return <section className={`cap-team-work ${comfortable ? 'comfortable' : ''}`} aria-label="Team work queue">
    <div className="cap-work-toolbar">
      <div className="cap-work-filters" aria-label="Team attention filters">
        {(['all', 'overdue', 'unassigned'] as const).map(filter => <button key={filter} type="button" aria-pressed={attention === filter} onClick={() => update({ team_filter: filter })}>
          {filter === 'all' ? 'All active work' : filter === 'overdue' ? 'Overdue' : 'Unassigned'}
        </button>)}
      </div>
      <label>Programme<select value={context} onChange={e => update({ team_context: e.target.value })}><option value="">All programmes</option>{data?.contexts?.map(name => <option key={name}>{name}</option>)}</select></label>
      <label>Action owner<select value={owner} onChange={e => update({ team_owner: e.target.value, team_filter: e.target.value && attention === 'unassigned' ? 'all' : attention })}><option value="">All action owners</option>{data?.people.filter(person => person.id).map(person => <option key={person.id} value={person.id ?? ''}>{person.name}</option>)}</select></label>
      <label>Work type<select value={kind} onChange={e => update({ team_kind: e.target.value })}><option value="">All work types</option>{Object.entries(kinds).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      <label>Sort by<select value={sort} onChange={e => update({ team_sort: e.target.value, team_group: '' })}><option value="programme">Programme</option><option value="owner">Action owner</option><option value="priority">Priority</option></select></label>
    </div>
    {query.isPending ? <div role="status" className="cap-work-empty">Loading team work…</div> : query.isError ? <div className="p-5"><LoadError subject="Team work" onRetry={() => query.refetch()} /></div> : data && <>
      <div className="cap-work-summary"><span>{data.total} matching items · {data.counts.overdue} overdue · {data.counts.unassigned} unassigned</span><span>Only work you can access</span></div>
      {items.length ? <div className="cap-work-table-scroll" tabIndex={0} role="region" aria-label="Team assignments"><table className="cap-work-table">
        <thead><tr><th>Work</th><th>Programme</th><th>Next action</th><th>Next action owner</th><th>Due</th><th><span className="sr-only">Open work</span></th></tr></thead>
        <tbody>{items.map(item => <tr key={`${item.kind}-${item.id}`}>
          <td><Link to={item.href} className="cap-work-title">{item.title}</Link><span className="cap-work-kind">{kinds[item.kind] || item.kind}</span></td>
          <td>{item.context}</td>
          <td>{item.next_action || item.action_label || nextActions[item.kind] || 'Open work'}</td>
          <td><span className={item.owner_name ? 'cap-work-person' : 'text-warning font-medium'}>{item.owner_name && <span className="avatar" aria-hidden="true">{item.owner_name.split(' ').map(part => part[0]).slice(0, 2).join('')}</span>}{item.owner_name || 'Unassigned'}</span></td>
          <td className={item.overdue ? 'text-warning' : 'text-muted'}>{item.due_date ? <><span>{formatDate(item.due_date)}</span>{item.overdue && <span className="cap-work-kind text-warning">Overdue</span>}</> : 'No deadline'}</td>
          <td><Link to={item.href} className="cap-work-action">{item.action_label || nextActions[item.kind] || 'Open work'}</Link></td>
        </tr>)}</tbody>
      </table></div> : <div className="cap-work-empty"><h2>No work matches these filters</h2><p>Choose another programme or owner, or clear the filters to see all accessible active work.</p><Button onClick={() => update({ team_filter: '', team_owner: '', team_context: '', team_kind: '' })}>Clear filters</Button></div>}
      <div className="cap-work-footer"><span>{data.total ? `${Math.min((page - 1) * 20 + 1, data.total)}–${Math.min(page * 20, data.total)} of ${data.total}` : '0 items'}</span><nav aria-label="Team work pages"><Button disabled={page <= 1} onClick={() => update({ team_page: String(page - 1) })}>Previous page</Button><Button disabled={page * 20 >= data.total} onClick={() => update({ team_page: String(page + 1) })}>Next page</Button></nav><label className="cap-density"><input type="checkbox" checked={comfortable} onChange={e => setComfortable(e.target.checked)} />Comfortable spacing</label></div>
      {data.people.length > 0 && <details className="cap-workload"><summary>Workload by action owner</summary><div>{data.people.map(person => <button type="button" key={person.id ?? 'unassigned'} onClick={() => update({ team_owner: person.id ?? '', team_filter: person.id === null ? 'unassigned' : attention === 'unassigned' ? 'all' : attention })}><strong>{person.name}</strong><span>{person.total} items{person.overdue ? ` · ${person.overdue} overdue` : ''}</span></button>)}</div></details>}
    </>}
  </section>
}
