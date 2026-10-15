import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import type { CertificationProject } from '../../types'
import { documentationApi } from '../../api/documentation'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, RequirementLink } from '../../types/documentation'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { Field, inputClass } from '../applications/Fields'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function RequirementMapping({ expectation, jurisdictionId, projectId, onClose, onSaved }: { expectation: DocumentationExpectation; jurisdictionId: string; projectId?: string; onClose: () => void; onSaved: (item: DocumentationExpectation) => void }) {
  const [documentId, setDocumentId] = useState('')
  const [versionId, setVersionId] = useState('')
  const [search, setSearch] = useState('')
  const [links, setLinks] = useState<RequirementLink[]>(expectation.requirements)
  const [baseline, setBaseline] = useState(expectation.requirements)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(expectation.revision)
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<DocumentationExpectation | null>(null)
  const [page, setPage] = useState(0)
  const { requestClose, confirmation } = useLocalDraftGuard(JSON.stringify(links) !== JSON.stringify(baseline), busy, onClose)
  const project = useQuery({ queryKey: ['documentation', 'project-baseline', projectId], queryFn: async () => (await api.get<CertificationProject>(`/certification-projects/${projectId}`)).data, enabled: Boolean(projectId) })
  const allowedVersions = project.data?.baseline_versions?.map(item => item.requirement_set_version_id) || []
  const sets = useQuery({ queryKey: ['documentation', 'requirement-sets', jurisdictionId], queryFn: () => preparationApi.requirementSets(jurisdictionId) })
  const versions = useQuery({ queryKey: ['documentation', 'requirement-versions', documentId], queryFn: () => preparationApi.requirementVersions(documentId), enabled: Boolean(documentId) })
  const requirements = useQuery({ queryKey: ['documentation', 'requirement-options', documentId, versionId, page], queryFn: () => preparationApi.requirementsPreview({ document_id: documentId, jurisdiction_id: jurisdictionId, version_id: versionId, skip: page * 100, limit: 100 }), enabled: Boolean(documentId && versionId) })
  return <>{confirmation}<Modal open title="Link obligations" size="lg" description="Choose a requirement set and an explicit version. Links retain that version." onClose={requestClose} footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button><Button loading={busy} disabled={conflict} variant="primary" onClick={async () => { setBusy(true); setError(''); try { onSaved(await documentationApi.requirements(expectation.id, revision, links)) } catch (caught) { if (axios.isAxiosError(caught) && caught.response?.status === 409) setConflict(true); setError(getApiErrorMessage(caught, 'Obligation links could not be saved. Your selections are preserved.')) } finally { setBusy(false) } }}>Save obligation links</Button></>}>
    <div className="space-y-4"><Field label="Requirement set"><select className={inputClass} value={documentId} onChange={event => { setDocumentId(event.target.value); setVersionId(''); setPage(0) }}><option value="">Select requirement set</option>{sets.data?.items.map(item => <option key={item.document_id} value={item.document_id}>{item.name || item.filename || 'Requirement set'}</option>)}</select></Field>{sets.isError && <LoadError subject="Requirement sets" onRetry={() => void sets.refetch()} />}
      <Field label="Requirement version"><select className={inputClass} value={versionId} disabled={!documentId || versions.isLoading} onChange={event => { setVersionId(event.target.value); setPage(0) }}><option value="">Select an explicit version</option>{versions.data?.items.filter(item => item.status === 'approved' && (!projectId || allowedVersions.includes(item.id))).map(item => <option key={item.id} value={item.id}>Version {item.version_number} · {item.status}{item.is_current ? ' · Current' : ''}</option>)}</select></Field>{versions.isError && <LoadError subject="Requirement versions" onRetry={() => void versions.refetch()} />}
      {projectId && <p className="text-sm text-muted">This project permits only its pinned approved baseline versions.</p>}{project.isError && <LoadError subject="Project baseline" onRetry={() => void project.refetch()} />}
      <Field label="Filter loaded obligations"><input type="search" className={inputClass} value={search} onChange={event => setSearch(event.target.value)} /></Field>
      {requirements.isLoading && <p role="status">Loading obligations…</p>}{requirements.isError && <LoadError subject="Versioned requirements" onRetry={() => void requirements.refetch()} />}
      <div className="max-h-64 space-y-3 overflow-y-auto">{requirements.data?.fields.filter(field => `${field.source?.reference_id || ''} ${field.label}`.toLowerCase().includes(search.toLowerCase())).map(field => { const source = field.source; if (!source?.requirement_id) return null; const id = source.requirement_id; return <label key={field.key} className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-1" checked={links.some(item => item.requirement_id === id && item.requirement_set_version_id === versionId)} onChange={event => setLinks(current => event.target.checked ? [...current.filter(item => item.requirement_id !== id), { requirement_id: id, requirement_set_version_id: versionId, reference_id: source.reference_id, title: field.label }] : current.filter(item => !(item.requirement_id === id && item.requirement_set_version_id === versionId)))} /><span className="break-words"><strong>{source.reference_id}</strong> {field.label}</span></label> })}</div>
      {!!requirements.data?.warnings.length && <p className="text-sm text-warning">{requirements.data.warnings.join(' ')}</p>}
      {(requirements.data?.total || 0) > 100 && <div className="flex gap-2"><Button size="sm" disabled={!page} onClick={() => setPage(page - 1)}>Previous obligations</Button><Button size="sm" disabled={(page + 1) * 100 >= (requirements.data?.total || 0)} onClick={() => setPage(page + 1)}>Next obligations</Button></div>}
      <h3 className="font-semibold">Selected obligations ({links.length})</h3>{links.map(link => <div key={`${link.requirement_id}-${link.requirement_set_version_id}`} className="flex items-start justify-between gap-2 text-sm"><span className="break-words">{link.reference_id || 'Linked requirement'} {link.title || ''}</span><Button size="sm" onClick={() => setLinks(current => current.filter(item => item !== link))}>Remove obligation</Button></div>)}
      {conflict && <section className="space-y-3 rounded-md border border-line p-3"><h3 className="font-semibold">Review concurrent obligation changes</h3><Button disabled={busy} onClick={async () => { setBusy(true); try { setLatest((await api.get<DocumentationExpectation>(`/documentation/expectations/${expectation.id}`)).data) } catch (caught) { setError(getApiErrorMessage(caught, 'Current links could not be loaded. Your selections are preserved.')) } finally { setBusy(false) } }}>Load current obligation links</Button>{latest && <><p className="text-sm">Current saved links:</p><ul className="space-y-1 text-sm">{latest.requirements.map((item, index) => <li key={index}>{item.reference_id || item.title || 'Linked obligation'}</li>)}</ul><p className="text-sm text-muted">Compare these links with your preserved selections above before replacing them.</p><div className="flex flex-wrap gap-2"><Button onClick={() => { setBaseline(latest.requirements); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Your reviewed selections are ready to save.') }}>Keep reviewed obligation selections</Button><Button onClick={() => { setLinks(latest.requirements); setBaseline(latest.requirements); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Current links restored.') }}>Use current obligation links</Button></div></>}</section>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  </Modal></>
}
