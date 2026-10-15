import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationProcess, DocumentationRegister } from '../../types/documentation'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { Field, inputClass } from '../applications/Fields'
import SectionNav from '../ui/SectionNav'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function RegisterProcessPicker({ register, onClose, onSaved }: { register: DocumentationRegister; onClose: () => void; onSaved: (register: DocumentationRegister) => void }) {
  const [kind, setKind] = useState<'review' | 'application'>(register.process?.kind || 'review')
  const [selected, setSelected] = useState<DocumentationProcess | null>(register.process || null)
  const [baselineProcess, setBaselineProcess] = useState(selected)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [revision, setRevision] = useState(register.revision)
  const [busy, setBusy] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [clearTargets, setClearTargets] = useState(false)
  const [latest, setLatest] = useState<DocumentationRegister | null>(null)
  const [error, setError] = useState('')
  const dirty = selected === null ? Boolean(baselineProcess) : selected.id !== baselineProcess?.id || selected.kind !== baselineProcess?.kind
  const { requestClose, confirmation } = useLocalDraftGuard(dirty, busy, onClose)
  const options = useQuery({ queryKey: ['documentation', 'process-options', register.id, search, page], queryFn: () => documentationApi.processOptions(register.id, search, page * 100) })
  const group = kind === 'review' ? options.data?.review_cycles : options.data?.applications
  return <>{confirmation}<Modal open title="Link process" size="lg" description="Choose a specific assessment or licence application. Each row can then use its existing evidence collection." onClose={requestClose} footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!dirty || conflict} onClick={async () => { setBusy(true); setError(''); try { onSaved(await documentationApi.linkProcess(register.id, revision, selected, clearTargets)) } catch (caught) { setConflict(axios.isAxiosError(caught) && caught.response?.status === 409); setError(getApiErrorMessage(caught, 'The process could not be linked. Your selection is preserved.')) } finally { setBusy(false) } }}>Save process link</Button></>}>
    <div className="space-y-4"><SectionNav label="Process type" value={kind} items={[{ id: 'review', label: 'Assessment or certification' }, { id: 'application', label: 'Licence application' }]} onChange={value => { setKind(value as typeof kind); setPage(0) }} /><Field label="Search processes"><input type="search" maxLength={255} className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field>
      <label className="flex items-start gap-2 text-sm"><input type="radio" name="linked-process" checked={selected === null} onChange={() => setSelected(null)} /><span>None · Keep this register standalone</span></label>
      {options.isLoading && <p role="status">Loading processes…</p>}{options.isError && <LoadError subject="Available processes" onRetry={() => void options.refetch()} />}{group?.items.map(process => <label key={process.id} className="flex items-start gap-3 border-t border-line py-3 text-sm"><input type="radio" name="linked-process" className="mt-1" checked={selected?.kind === process.kind && selected.id === process.id} onChange={() => setSelected(process)} /><span className="min-w-0 break-words"><strong>{process.name}</strong>{process.project_name && <span className="block text-muted">Certification project: {process.project_name}</span>}{process.status && <span className="block text-muted">{process.status}</span>}</span></label>)}{group && !group.items.length && <p className="text-sm text-muted">No permitted processes match this search in the register jurisdiction.</p>}
      {group && group.total > 100 && <div className="flex gap-2"><Button disabled={!page} onClick={() => setPage(page - 1)}>Previous processes</Button><Button disabled={(page + 1) * 100 >= group.total} onClick={() => setPage(page + 1)}>Next processes</Button></div>}
      {baselineProcess && <div className="space-y-2"><p className="text-sm text-muted">Existing evidence stays in its original process. A new process link requires explicit row mappings.</p><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={clearTargets} onChange={event => setClearTargets(event.target.checked)} /><span>Remove register matches; keep process evidence</span></label></div>}{error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {conflict && <div className="space-y-3 border-t border-line pt-3"><Button onClick={async () => { try { setLatest((await api.get<DocumentationRegister>(`/documentation/registers/${register.id}`)).data) } catch (caught) { setError(getApiErrorMessage(caught, 'The current process link could not be loaded.')) } }}>Load current process link</Button>{latest && <><p className="text-sm">Current process: {latest.process?.available ? latest.process.name : latest.process ? 'Unavailable' : 'None'}</p><p className="text-sm">Your selection: {selected?.name || 'None'}</p><Button onClick={() => { setBaselineProcess(latest.process || null); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Review your selection, then save the process link.') }}>Keep reviewed selection</Button></>}</div>}
    </div>
  </Modal></>
}
