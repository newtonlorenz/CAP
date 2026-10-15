import { useState } from 'react'
import axios from 'axios'
import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { PaginatedResponse, UserMention } from '../../types'
import type { DocumentationExpectation } from '../../types/documentation'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'
import { OwnerField } from '../applications/Fields'
import Button from '../ui/Button'
import DraftSaveStatus from '../ui/DraftSaveStatus'
import LoadError from '../ui/LoadError'
import Modal from '../ui/Modal'

export default function RegisterOwnerPicker({ row, onClose, onSaved }: {
  row: DocumentationExpectation
  onClose: () => void
  onSaved: (row: DocumentationExpectation) => void
}) {
  const [ownerId, setOwnerId] = useState(row.owner_id || '')
  const [baseline, setBaseline] = useState(ownerId)
  const [revision, setRevision] = useState(row.revision)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<DocumentationExpectation | null>(null)
  const dirty = ownerId !== baseline
  const { requestClose, confirmation } = useLocalDraftGuard(dirty, busy, onClose)
  const users = useQuery({ queryKey: ['documentation', 'users'], queryFn: async () =>
    (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data })
  const selectedName = ownerId ? users.data?.items.find(user => user.id === ownerId)?.full_name
    || (ownerId === row.owner_id ? row.owner_name : null) || 'Assigned owner (unavailable)' : 'Unassigned'
  const save = async () => {
    if (!dirty || busy || conflict) return
    setBusy(true); setError('')
    try { onSaved(await documentationApi.updateExpectation(row.id, revision, { owner_id: ownerId || null })) }
    catch (caught) {
      setConflict(axios.isAxiosError(caught) && caught.response?.status === 409)
      setLatest(null)
      setError(getApiErrorMessage(caught, 'The responsible owner could not be saved. Your selection is preserved.'))
    } finally { setBusy(false) }
  }
  return <>{confirmation}<Modal open title="Assign responsible owner"
    description="Responsibility is optional. Assigning a user does not grant access to the register."
    onClose={requestClose} footer={<>
      <DraftSaveStatus state={busy ? 'saving' : conflict ? 'conflict' : error ? 'error' : dirty ? 'dirty' : 'saved'} />
      <Button disabled={busy} onClick={requestClose}>Cancel</Button>
      <Button variant="primary" loading={busy} disabled={!dirty || conflict} onClick={() => void save()}>Save assignment</Button>
    </>}>
    <div className="space-y-4">
      <p className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words text-sm font-medium">{row.required_documentation ?? row.title}</p>
      {users.isLoading && <p role="status">Loading users…</p>}
      {users.isError && <LoadError subject="Available users" onRetry={() => void users.refetch()} />}
      <fieldset disabled={busy} className="space-y-3">
        <OwnerField users={users.data?.items || []} value={ownerId} onChange={setOwnerId} />
        <Button size="sm" disabled={!ownerId} onClick={() => setOwnerId('')}>Clear assignment</Button>
      </fieldset>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {conflict && <section className="space-y-3 border-t border-line pt-3">
        <h3 className="font-semibold">Review concurrent assignment changes</h3>
        <Button disabled={busy} onClick={async () => {
          setBusy(true)
          try { setLatest((await api.get<DocumentationExpectation>(`/documentation/expectations/${row.id}`)).data) }
          catch (caught) { setError(getApiErrorMessage(caught, 'The current assignment could not be loaded. Your selection is preserved.')) }
          finally { setBusy(false) }
        }}>Load current assignment</Button>
        {latest && <>
          <p className="text-sm">Current owner: {latest.owner_id ? latest.owner_name || 'Assigned owner (unavailable)' : 'Unassigned'}</p>
          <p className="text-sm">Your selection: {selectedName}</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => { setBaseline(latest.owner_id || ''); setRevision(latest.revision); setConflict(false); setLatest(null); setError('') }}>Keep reviewed assignment</Button>
            <Button onClick={() => { setOwnerId(latest.owner_id || ''); setBaseline(latest.owner_id || ''); setRevision(latest.revision); setConflict(false); setLatest(null); setError('') }}>Use current assignment</Button>
          </div>
        </>}
      </section>}
    </div>
  </Modal></>
}
