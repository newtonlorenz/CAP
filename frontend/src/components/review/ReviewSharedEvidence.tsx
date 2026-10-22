import { useEffect, useState } from 'react'
import axios from 'axios'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../../api/client'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { invalidateDocumentationCollections } from '../documentation/cache'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import LoadError from '../ui/LoadError'
import { Field, inputClass } from '../applications/Fields'

type EvidenceLink = { evidence_id: string; title: string; kind: string; filename?: string; locator: string | null; rationale: string; problems: string[] }
type EvidenceState = { items: EvidenceLink[]; evidence_changed_at: string | null; warning?: string | null }

export function SharedEvidenceDialog({ cycleId, itemId, onClose }: { cycleId: string; itemId: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [initial, setInitial] = useState<EvidenceState | null>(null)
  const [links, setLinks] = useState<EvidenceLink[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<EvidenceState | null>(null)
  const root = `/review-cycles/${cycleId}/items/${itemId}/shared-evidence`
  const existing = useQuery({ queryKey: ['review-shared-evidence', cycleId, itemId], queryFn: async () => (await api.get<EvidenceState>(root)).data, refetchOnWindowFocus: false })
  const available = useQuery({ queryKey: ['shared-evidence-options', search, page], queryFn: () => preparationApi.evidence(new URLSearchParams({ q: search, limit: '100', skip: String(page * 100) })) })
  useEffect(() => { if (existing.data && initial === null) { setInitial(existing.data); setLinks(existing.data.items) } }, [existing.data, initial])
  const dirty = initial !== null && JSON.stringify(links) !== JSON.stringify(initial.items)
  const { requestClose, confirmation } = useLocalDraftGuard(dirty, busy, onClose)
  const save = async () => {
    if (!initial || conflict || busy) return
    setBusy(true); setError('')
    try {
      await api.put(root, { expected_evidence_changed_at: initial.evidence_changed_at, links: links.map(({ evidence_id, locator, rationale }) => ({ evidence_id, locator, rationale })) })
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['review-cycle', cycleId] }), queryClient.invalidateQueries({ queryKey: ['review-shared-evidence', cycleId, itemId] }), invalidateDocumentationCollections(queryClient)])
      onClose()
    } catch (caught) { setConflict(axios.isAxiosError(caught) && caught.response?.status === 409); setLatest(null); setError(getApiErrorMessage(caught, 'Evidence links could not be saved. Your selections are preserved.')) } finally { setBusy(false) }
  }
  return <>{confirmation}<Modal open title="Reuse evidence from the library" size="lg" onClose={requestClose} description="Link an existing evidence version and explain how it supports this assessment." footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!initial || !!initial.warning || conflict || !dirty || links.some(link => !link.rationale.trim())} onClick={() => void save()}>Save evidence links</Button></>}>
    <div className="space-y-4">
      {existing.isError && <LoadError subject="Linked evidence" onRetry={() => void existing.refetch()} />}
      {initial?.warning && <p role="alert" className="text-sm text-muted">{initial.warning}. A person with access to all linked sources must change these associations.</p>}
      <Field label="Search available evidence"><input type="search" className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field>
      <Link className="text-sm text-accent underline" to="/library?section=evidence">Add or upload evidence in the library</Link>
      {available.isLoading && <p role="status">Loading available evidence…</p>}
      {available.isError && <LoadError subject="Available evidence" onRetry={() => void available.refetch()} />}
      <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border border-line p-3">{available.data?.items.map(item => <label key={item.id} className="flex items-start gap-3 text-sm"><input type="checkbox" disabled={busy || !initial || !!initial.warning} checked={links.some(link => link.evidence_id === item.id)} onChange={event => { const checked = event.target.checked; setLinks(current => checked ? [...current, { evidence_id: item.id, title: item.title, kind: item.kind, locator: '', rationale: '', problems: [] }] : current.filter(link => link.evidence_id !== item.id)) }} /><span>{item.title}<span className="block text-muted">{item.kind}</span></span></label>)}</div>
      {(available.data?.total || 0) > 100 && <div className="flex gap-2"><Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" disabled={(page + 1) * 100 >= (available.data?.total || 0)} onClick={() => setPage(page + 1)}>Next</Button></div>}
      {links.map(link => <fieldset key={link.evidence_id} disabled={busy || !!initial?.warning} className="space-y-3 border-t border-line pt-3"><legend className="pt-2 font-semibold">{link.title}</legend><Field label="Evidence locator"><input className={inputClass} placeholder="Section, page, worksheet, or record" value={link.locator || ''} onChange={event => { const locator = event.target.value; setLinks(current => current.map(value => value.evidence_id === link.evidence_id ? { ...value, locator } : value)) }} /></Field><Field label="Assessment explanation"><textarea className={inputClass} value={link.rationale} onChange={event => { const rationale = event.target.value; setLinks(current => current.map(value => value.evidence_id === link.evidence_id ? { ...value, rationale } : value)) }} /></Field><Button size="sm" onClick={() => setLinks(current => current.filter(value => value.evidence_id !== link.evidence_id))}>Remove link</Button></fieldset>)}
      {conflict && <section className="space-y-3 border-t border-line pt-3"><h3 className="font-semibold">Review concurrent evidence changes</h3><Button disabled={busy} onClick={async () => { setBusy(true); try { setLatest((await api.get<EvidenceState>(root)).data) } catch (caught) { setError(getApiErrorMessage(caught, 'Current evidence links could not be loaded. Your selections are preserved.')) } finally { setBusy(false) } }}>Load current evidence links</Button>{latest && <><p className="text-sm font-semibold">Current saved evidence</p>{latest.warning && <p role="alert" className="text-sm text-muted">{latest.warning}. A person with access to all sources must change these associations.</p>}<ul className="space-y-2 text-sm">{latest.items.map(link => <li key={link.evidence_id}><strong>{link.title}</strong><p className="whitespace-pre-wrap">{link.locator || 'No locator'} · {link.rationale}</p></li>)}</ul>{!latest.items.length && !latest.warning && <p className="text-sm">No evidence links are currently saved.</p>}<p className="text-sm text-muted">Compare these current links with your preserved selections above. Keeping your selections will replace the saved links only when you save again.</p><div className="flex flex-wrap gap-2"><Button disabled={Boolean(latest.warning)} onClick={() => { setInitial(latest); setLatest(null); setConflict(false); setError('Your reviewed evidence selections are ready to save.') }}>Keep reviewed evidence selections</Button><Button onClick={() => { setInitial(latest); setLinks(latest.items); setLatest(null); setConflict(false); setError('Current evidence links restored.') }}>Use current evidence links</Button></div></>}</section>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  </Modal></>
}

export default function ReviewSharedEvidence({ cycleId, itemId, active, links = [], warning }: { cycleId: string; itemId: string; active: boolean; links?: EvidenceLink[]; warning?: string | null }) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const download = async (link: EvidenceLink) => {
    try {
      const response = await api.get(`/review-cycles/${cycleId}/items/${itemId}/shared-evidence/${link.evidence_id}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = link.filename || link.title; anchor.click(); URL.revokeObjectURL(url)
    } catch (caught) { setError(getApiErrorMessage(caught, 'Evidence could not be downloaded.')) }
  }
  return <div className="mt-4 space-y-2 border-t border-line pt-3"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-semibold">Shared evidence</h4>{active && <Button size="sm" onClick={() => setOpen(true)}>Link library evidence</Button>}</div>
    {warning && <p className="text-sm text-muted">{warning}</p>}
    {!links.length && !warning && <p className="text-xs text-muted">No shared evidence linked.</p>}
    {links.map(link => <div key={link.evidence_id} className="space-y-1 rounded-md border border-line p-3 text-sm"><p className="font-medium">{link.title}</p>{link.locator && <p className="text-muted">{link.locator}</p>}<p className="whitespace-pre-wrap">{link.rationale}</p>{link.problems.length > 0 && <p className="text-amber-700">Evidence needs review: {link.problems.map(value => value.replace(/_/g, ' ')).join(', ')}</p>}{link.kind === 'file' && <button type="button" className="text-accent underline" onClick={() => void download(link)}>Download evidence</button>}</div>)}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {open && <SharedEvidenceDialog cycleId={cycleId} itemId={itemId} onClose={() => setOpen(false)} />}
  </div>
}
