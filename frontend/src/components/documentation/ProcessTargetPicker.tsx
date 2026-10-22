import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, ProcessTarget } from '../../types/documentation'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { targetKey } from './processNavigation'
import { Field, inputClass } from '../applications/Fields'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'

export default function ProcessTargetPicker({ row, onClose, onSaved }: { row: DocumentationExpectation; onClose: () => void; onSaved: (row: DocumentationExpectation) => void }) {
  const [targets, setTargets] = useState<ProcessTarget[]>(row.process_targets?.filter(target => target.available) || [])
  const [baselineTargets, setBaselineTargets] = useState(targets)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(row.revision)
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<DocumentationExpectation | null>(null)
  const unavailable = row.process_targets?.some(target => !target.available)
  const { requestClose, confirmation } = useLocalDraftGuard(JSON.stringify(targets.map(target => [targetKey(target), target.requirement_id, target.requirement_set_version_id])) !== JSON.stringify(baselineTargets.map(target => [targetKey(target), target.requirement_id, target.requirement_set_version_id])), busy, onClose)
  const options = useQuery({ queryKey: ['documentation', 'process-target-options', row.id, row.process?.id, search, page], queryFn: () => documentationApi.rowProcessTargets(row.id, search, page * 100) })
  return <>{confirmation}<Modal open title="Match process reference" size="lg" description="Choose the exact requirement or form question. Similar or repeated references require an explicit choice." onClose={requestClose} footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={unavailable || conflict || targets.length > 50} onClick={async () => { setBusy(true); setError(''); try { onSaved(await documentationApi.linkTargets(row.id, revision, targets)) } catch (caught) { setConflict(axios.isAxiosError(caught) && caught.response?.status === 409); setError(getApiErrorMessage(caught, 'The reference match could not be saved. Your selections are preserved.')) } finally { setBusy(false) } }}>Save reference matches</Button></>}>
    <div className="space-y-4"><p className="whitespace-pre-wrap break-words text-sm"><strong>Original SCP reference:</strong> {row.source_reference || 'Not supplied'}</p>{unavailable && <p role="alert" className="text-sm text-muted">Some existing targets are unavailable. A person with access to all targets must change this mapping.</p>}<Field label="Search process requirements"><input type="search" maxLength={255} className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field>{options.isLoading && <p role="status">Loading process requirements…</p>}{options.isError && <LoadError subject="Process requirements" onRetry={() => void options.refetch()} />}{options.data?.items.map(target => <div key={targetKey(target)} className="space-y-2 border-t border-line py-4 text-sm">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1 shrink-0" disabled={busy || unavailable}
            checked={targets.some(value => targetKey(value) === targetKey(target))}
            onChange={event => {
              const checked = event.target.checked
              setTargets(current => checked ? [...current, target] : current.filter(value => targetKey(value) !== targetKey(target)))
            }} />
          <span className="min-w-0 space-y-2">
            <strong className="block break-words">{target.reference_id}</strong>
            <TargetDescription target={target} />
          </span>
        </label>
        {target.href && <div className="pl-7"><Link to={target.href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2">
          {target.kind === 'review_item' ? 'Open full requirement (new tab)' : 'Open form question (new tab)'}
        </Link></div>}
      </div>)}{options.data && !options.data.items.length && <p className="text-sm text-muted">No permitted targets match this search. The original reference remains unchanged.</p>}{options.data && options.data.total > 100 && <div className="flex gap-2"><Button disabled={!page} onClick={() => setPage(page - 1)}>Previous requirements</Button><Button disabled={(page + 1) * 100 >= options.data.total} onClick={() => setPage(page + 1)}>Next requirements</Button></div>}
      <h3 className="font-semibold">Selected references ({targets.length})</h3>{targets.map(target => <div key={targetKey(target)} className="flex items-start justify-between gap-2 text-sm"><span className="min-w-0 space-y-2"><strong className="block break-words">{target.reference_id}</strong><TargetDescription target={target} /></span><Button size="sm" disabled={unavailable} onClick={() => setTargets(current => current.filter(value => targetKey(value) !== targetKey(target)))}>Remove match</Button></div>)}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}{conflict && <div className="space-y-3 border-t border-line pt-3"><p className="text-sm text-muted">The row or an available target changed. Reload available requirements and explicitly choose the current version.</p><Button onClick={() => void options.refetch()}>Reload available requirements</Button>{targets.map(target => { const refreshed = options.data?.items.find(value => targetKey(value) === targetKey(target)); return refreshed && (refreshed.requirement_id !== target.requirement_id || refreshed.requirement_set_version_id !== target.requirement_set_version_id) ? <div key={targetKey(target)} className="space-y-2 text-sm"><p>{target.reference_id}: a different requirement version is now available.</p><Button size="sm" onClick={() => setTargets(current => current.map(value => targetKey(value) === targetKey(target) ? refreshed : value))}>Use refreshed target</Button></div> : null })}<Button onClick={async () => { try { setLatest((await api.get<DocumentationExpectation>(`/documentation/expectations/${row.id}`)).data) } catch (caught) { setError(getApiErrorMessage(caught, 'Current reference matches could not be loaded.')) } }}>Load current reference matches</Button>{latest && <><p className="text-sm">Current matches: {(latest.process_targets || []).map(target => target.available ? `${target.reference_id} ${target.title}` : 'Unavailable target').join('; ') || 'None'}</p><Button disabled={latest.process_targets?.some(target => !target.available)} onClick={() => { setBaselineTargets((latest.process_targets || []).filter(target => target.available)); setRevision(latest.revision); setLatest(null); setConflict(false); setError('Your reviewed selections are ready to save.') }}>Keep reviewed matches</Button></>}</div>}
    </div>
  </Modal></>
}

function TargetDescription({ target }: { target: ProcessTarget }) {
  const title = target.title?.trim()
  const context = target.requirement_context?.map(section => [section.reference_id,
    section.title === section.reference_id ? '' : section.title].filter(Boolean).join(' ')).join(' › ')
  return <>
    {target.set_name && <span className="block break-words font-medium">{target.set_name}{target.version_number ? ` · Version ${target.version_number}` : ''}</span>}
    {!target.set_name && target.version_number && <span className="block text-muted">Version {target.version_number}</span>}
    {context && <span className="block break-words text-muted">{context}</span>}
    {title && title !== target.reference_id?.trim() && title !== target.requirement_text?.trim() && <span className="block whitespace-pre-wrap break-words font-medium">{title}</span>}
    {target.requirement_text && <span className="block whitespace-pre-wrap break-words">{target.requirement_text}{target.requirement_text_truncated ? '…' : ''}</span>}
    {target.requirement_text_truncated && <span className="block text-muted">Wording preview. Open the full requirement to read all text.</span>}
    <span className="block break-words text-muted">{target.kind === 'review_item' ? 'Assessment requirement' : 'Licence form question'}{target.process_name ? ` · ${target.process_name}` : ''}</span>
    {target.case_name && <span className="block break-words text-muted">Form: {target.case_name}</span>}
    {target.owner_name && <span className="block break-words text-muted">Owner: {target.owner_name}</span>}
  </>
}
