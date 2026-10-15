import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import type { CoverageLink, DocumentationExpectation } from '../../types/documentation'
import { Field, inputClass } from '../applications/Fields'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function EvidenceMapping({ expectation, onClose, onSaved, simple = false }: { simple?: boolean; expectation: DocumentationExpectation; onClose: () => void; onSaved: (item: DocumentationExpectation) => void }) {
  const location = useLocation()
  const [search, setSearch] = useState('')
  const [links, setLinks] = useState<CoverageLink[]>(expectation.coverage)
  const [baseline, setBaseline] = useState(expectation.coverage)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(expectation.revision)
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<DocumentationExpectation | null>(null)
  const [page, setPage] = useState(0)
  const evidence = useQuery({ queryKey: ['documentation', 'available-evidence', search, page], queryFn: () => preparationApi.evidence(new URLSearchParams({ q: search, limit: '100', skip: String(page * 100) })) })
  const { requestClose, confirmation } = useLocalDraftGuard(JSON.stringify(links) !== JSON.stringify(baseline), busy, onClose)
  const change = (id: string, patch: Partial<CoverageLink>) => setLinks(current => current.map(item => item.evidence_id === id ? { ...item, ...patch } : item))
  return <>{confirmation}<Modal open title={simple ? 'Link document' : 'Link evidence'} size="lg" description={simple ? 'Choose documents from the existing evidence library. Linking does not record a coverage decision.' : 'Choose existing permitted evidence. Record which part supports this expectation.'} onClose={requestClose} footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={conflict || links.some(item => !item.rationale.trim())} onClick={async () => { setBusy(true); setError(''); try { onSaved(await documentationApi.coverage(expectation.id, revision, links)) } catch (caught) { if (axios.isAxiosError(caught) && caught.response?.status === 409) setConflict(true); setError(getApiErrorMessage(caught, 'Evidence links could not be saved. Your selections are preserved.')) } finally { setBusy(false) } }}>{simple ? 'Link selected documents' : 'Save evidence links'}</Button></>}>
    <div className="space-y-4"><Field label="Search available evidence"><input type="search" className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field>
      <Link className="text-sm text-accent underline" to={`/library?section=evidence&returnTo=${encodeURIComponent(location.pathname + location.search)}`}>Add or upload evidence in the evidence library</Link>
      {evidence.isLoading && <p role="status">Loading available evidence…</p>}{evidence.isError && <LoadError subject="Available evidence" onRetry={() => void evidence.refetch()} />}
      {evidence.isSuccess && !evidence.data.items.length && <p className="text-sm text-muted">No permitted evidence matches this search.</p>}
      <div className="max-h-52 space-y-2 overflow-y-auto rounded-md border border-line p-3">{evidence.data?.items.map(item => <label key={item.id} className="flex items-start gap-3 py-1 text-sm"><input className="mt-1" type="checkbox" checked={links.some(link => link.evidence_id === item.id)} onChange={event => setLinks(current => event.target.checked ? [...current, { evidence_id: item.id, evidence: item, locator: '', scope: '', period: '', rationale: simple ? 'Selected document for this register entry. Coverage has not been reviewed.' : '' }] : current.filter(link => link.evidence_id !== item.id))} /><span className="break-words">{item.title}<span className="block text-muted">{item.kind}{item.filename ? ` · ${item.filename}` : ''}</span></span></label>)}</div>
      {(evidence.data?.total || 0) > 100 && <div className="flex gap-2"><Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous evidence</Button><Button size="sm" disabled={(page + 1) * 100 >= (evidence.data?.total || 0)} onClick={() => setPage(page + 1)}>Next evidence</Button></div>}
      <h3 className="font-semibold">Selected evidence ({links.length})</h3>
      {links.map(link => <fieldset key={link.evidence_id} disabled={busy} className="space-y-3 border-t border-line pt-3"><legend className="break-words pt-2 font-semibold">{link.evidence?.title || link.title || 'Existing evidence link'}</legend>{simple && <p className="text-sm text-muted">The document will be linked to this row. Review its coverage separately in Details.</p>}<details open={!simple}><summary className="cursor-pointer text-sm font-semibold">Link details</summary><div className="mt-3 space-y-3"><Field label="Evidence locator"><input className={inputClass} placeholder="Section, page, worksheet, or record" value={link.locator || ''} onChange={event => change(link.evidence_id, { locator: event.target.value })} /></Field><div className="grid gap-3 sm:grid-cols-2"><Field label="Evidence scope"><input className={inputClass} value={link.scope || ''} onChange={event => change(link.evidence_id, { scope: event.target.value })} /></Field><Field label="Evidence period"><input className={inputClass} value={link.period || ''} onChange={event => change(link.evidence_id, { period: event.target.value })} /></Field></div><Field label="Coverage explanation"><textarea required className={inputClass} value={link.rationale} onChange={event => change(link.evidence_id, { rationale: event.target.value })} /></Field></div></details><Button size="sm" onClick={() => setLinks(current => current.filter(item => item.evidence_id !== link.evidence_id))}>Remove evidence link</Button></fieldset>)}
      {conflict && <section className="space-y-3 rounded-md border border-line p-3"><h3 className="font-semibold">Review concurrent evidence changes</h3><Button disabled={busy} onClick={async () => { setBusy(true); try { setLatest((await api.get<DocumentationExpectation>(`/documentation/expectations/${expectation.id}`)).data) } catch (caught) { setError(getApiErrorMessage(caught, 'Current links could not be loaded. Your selections are preserved.')) } finally { setBusy(false) } }}>Load current evidence links</Button>{latest && <><p className="text-sm">Current saved links:</p><ul className="space-y-1 text-sm">{latest.coverage.map((item, index) => <li key={index}>{item.title || item.evidence?.title || 'Linked evidence'}</li>)}</ul><p className="text-sm text-muted">Compare these links with your preserved selections above before replacing them.</p><div className="flex flex-wrap gap-2"><Button onClick={() => { setBaseline(latest.coverage); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Your reviewed selections are ready to save.') }}>Keep reviewed evidence selections</Button><Button onClick={() => { setLinks(latest.coverage); setBaseline(latest.coverage); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Current links restored.') }}>Use current evidence links</Button></div></>}</section>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  </Modal></>
}
