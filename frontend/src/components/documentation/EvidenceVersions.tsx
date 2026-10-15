import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { documentationApi } from '../../api/documentation'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import { Field, inputClass } from '../applications/Fields'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import LoadError from '../ui/LoadError'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'

export default function EvidenceVersions({ registerId, canEdit }: { registerId: string; canEdit: boolean }) {
  const cache = useQueryClient()
  const [open, setOpen] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [evidenceId, setEvidenceId] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const groups = useQuery({ queryKey: ['documentation', 'evidence-groups', registerId], queryFn: () => documentationApi.evidenceGroups(registerId) })
  const available = useQuery({ queryKey: ['documentation', 'available-evidence', search, page], queryFn: () => preparationApi.evidence(new URLSearchParams({ q: search, limit: '100', skip: String(page * 100) })), enabled: open !== null })
  const { requestClose, confirmation } = useLocalDraftGuard(Boolean(open && (evidenceId || (open === 'new' && title))), busy, () => setOpen(null))
  return <>{confirmation}<section className="space-y-3 border-t border-line pt-4"><h3 className="font-semibold">Document versions</h3><p className="text-sm text-muted">Group immutable library evidence into document versions. Superseded links require review.</p>{canEdit && <Button size="sm" onClick={() => { setOpen('new'); setTitle(''); setEvidenceId(''); setError('') }}>Group document versions</Button>}{groups.isError && <LoadError subject="Document versions" onRetry={() => void groups.refetch()} />}{groups.data?.items.map(item => <div key={item.id} className="space-y-1 border-b border-line py-3 text-sm"><strong>{item.title}</strong><p>{item.versions.length} recorded versions</p><ul className="space-y-1">{item.versions.map(version => <li key={version.evidence_id}>Version {version.version ?? 'recorded'} · {version.title || 'Permitted evidence'} · {version.evidence_id === item.current_evidence_id ? 'Current' : 'Superseded'}</li>)}</ul>{canEdit && <Button size="sm" onClick={() => { setOpen(item.id); setEvidenceId(''); setError('') }}>Add document version</Button>}</div>)}<Modal open={open !== null} title={open === 'new' ? 'Group document versions' : 'Add document version'} onClose={requestClose}><form className="space-y-4" onSubmit={async event => { event.preventDefault(); setBusy(true); setError(''); try { if (open === 'new') await documentationApi.createEvidenceGroup(registerId, title, evidenceId); else { const group = groups.data?.items.find(item => item.id === open); if (!group) throw new Error('Document group is unavailable'); await documentationApi.addEvidenceVersion(group.id, group.revision, evidenceId) } await cache.invalidateQueries({ queryKey: ['documentation'] }); setOpen(null) } catch (caught) { setError(getApiErrorMessage(caught, 'The document version could not be saved. Your selections are preserved.')) } finally { setBusy(false) } }}>{open === 'new' && <Field label="Document group title"><input required className={inputClass} value={title} onChange={event => setTitle(event.target.value)} /></Field>}<Field label="Search library versions"><input type="search" className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field><Field label="Library evidence version"><select required className={inputClass} value={evidenceId} onChange={event => setEvidenceId(event.target.value)}><option value="">Select existing evidence</option>{available.data?.items.map(item => <option key={item.id} value={item.id}>{item.title}{item.filename ? ` · ${item.filename}` : ''}</option>)}</select></Field>{(available.data?.total || 0) > 100 && <div className="flex gap-2"><Button disabled={!page} onClick={() => setPage(page - 1)}>Previous library versions</Button><Button disabled={(page + 1) * 100 >= (available.data?.total || 0)} onClick={() => setPage(page + 1)}>Next library versions</Button></div>}{available.isError && <LoadError subject="Library evidence" onRetry={() => void available.refetch()} />}{error && <div className="space-y-2"><p role="alert" className="text-sm text-danger">{error}</p><Button onClick={() => void groups.refetch()}>Reload document versions</Button></div>}<Button type="submit" variant="primary" loading={busy} disabled={!evidenceId || (open === 'new' && !title.trim())}>Save document version</Button></form></Modal></section></>
}
