import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, DocumentationProcess } from '../../types/documentation'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { Field, inputClass } from '../applications/Fields'
import Button from '../ui/Button'
import LoadError from '../ui/LoadError'
import Modal from '../ui/Modal'

const override = (row: DocumentationExpectation) => row.process_inherited ? null : row.process || null

export default function RowReviewPicker({ row, registerProcess, onClose, onSaved }: {
  row: DocumentationExpectation; registerProcess?: DocumentationProcess | null
  onClose: () => void; onSaved: (row: DocumentationExpectation) => void
}) {
  const [selected, setSelected] = useState<DocumentationProcess | null>(() => override(row))
  const [baseline, setBaseline] = useState(selected)
  const [revision, setRevision] = useState(row.revision)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [clearTargets, setClearTargets] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<DocumentationExpectation | null>(null)
  const dirty = selected === null ? Boolean(baseline) : selected.id !== baseline?.id
  const { requestClose, confirmation } = useLocalDraftGuard(dirty, busy, onClose)
  const options = useQuery({ queryKey: ['documentation', 'row-review-options', row.id, search, page],
    queryFn: () => documentationApi.rowReviewOptions(row.id, search, page * 100) })
  const inheritedName = registerProcess ? registerProcess.available ? registerProcess.name : 'Unavailable' : 'None'
  return <>{confirmation}<Modal open title="Select certification review" size="lg"
    description="Choose a review for this documentation row, then match its exact SCP requirements. Other rows can use different reviews."
    onClose={requestClose} footer={<><Button disabled={busy} onClick={requestClose}>Cancel</Button>
      <Button variant="primary" loading={busy} disabled={!dirty || conflict} onClick={async () => {
        setBusy(true); setError('')
        try { onSaved(await documentationApi.linkRowReview(row.id, revision, selected?.id || null, clearTargets)) }
        catch (caught) { setConflict(axios.isAxiosError(caught) && caught.response?.status === 409); setLatest(null); setError(getApiErrorMessage(caught, 'The review could not be linked. Your selection is preserved.')) }
        finally { setBusy(false) }
      }}>Save review link</Button></>}>
    <div className="space-y-4">
      <p className="whitespace-pre-wrap break-words text-sm"><strong>SCP reference:</strong> {row.source_reference || 'Not supplied'}</p>
      <Field label="Search certification reviews"><input type="search" maxLength={255} className={inputClass} value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></Field>
      <label className="flex items-start gap-2 text-sm"><input type="radio" name="row-review" disabled={busy} checked={selected === null} onChange={() => setSelected(null)} /><span>Use register process · {inheritedName}</span></label>
      {options.isLoading && <p role="status">Loading certification reviews…</p>}
      {options.isError && <LoadError subject="Certification reviews" onRetry={() => void options.refetch()} />}
      {options.data?.items.map(review => <label key={review.id} className="flex items-start gap-3 border-t border-line py-3 text-sm"><input type="radio" name="row-review" disabled={busy} checked={selected?.id === review.id} onChange={() => setSelected(review)} /><span className="min-w-0 break-words"><strong>{review.name}</strong>{review.project_name && <span className="block text-muted">Certification project: {review.project_name}</span>}{review.status && <span className="block text-muted">{review.status}</span>}</span></label>)}
      {options.data && !options.data.items.length && <p className="text-sm text-muted">No permitted certification reviews match this search in the register jurisdiction.</p>}
      {options.data && options.data.total > 100 && <div className="flex gap-2"><Button disabled={!page} onClick={() => setPage(page - 1)}>Previous reviews</Button><Button disabled={(page + 1) * 100 >= options.data.total} onClick={() => setPage(page + 1)}>Next reviews</Button></div>}
      <p className="text-sm text-muted">Documents stay in their original review. Choosing a review does not assess or approve this row.</p>
      {(Boolean(row.process_targets?.length) || baseline || registerProcess) && <label className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={busy} checked={clearTargets} onChange={event => setClearTargets(event.target.checked)} /><span>Remove this row’s matches; keep process evidence</span></label>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {conflict && <section className="space-y-3 border-t border-line pt-3"><Button disabled={busy} onClick={async () => {
        setBusy(true)
        try { setLatest((await api.get<DocumentationExpectation>(`/documentation/expectations/${row.id}`)).data) }
        catch (caught) { setError(getApiErrorMessage(caught, 'The current review link could not be loaded.')) }
        finally { setBusy(false) }
      }}>Load current review link</Button>{latest && <><p className="text-sm">Current process: {latest.process ? latest.process.available ? latest.process.name : 'Unavailable' : 'None'}{latest.process_inherited ? ' · Register default' : ''}</p><p className="text-sm">Your selection: {selected ? selected.available ? selected.name : 'Unavailable' : `Use register process · ${inheritedName}`}</p><Button onClick={() => { setBaseline(override(latest)); setRevision(latest.revision); setConflict(false); setLatest(null); setError('Review your selection, then save the review link.') }}>Keep reviewed review selection</Button></>}</section>}
    </div>
  </Modal></>
}
