import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import EvidencePreview from '../preparation/EvidencePreview'
import Button from '../ui/Button'
import Modal from '../ui/Modal'

export default function RegisterDocumentPreview({ id, onClose }: { id: string; onClose: () => void }) {
  const evidence = useQuery({ queryKey: ['preparation', 'evidence', 'item', id], queryFn: () => preparationApi.getEvidence(id) })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  return <Modal open title={evidence.data?.title || 'Document'} size="lg" onClose={onClose} footer={<><Button onClick={onClose}>Close document</Button>{evidence.data?.kind === 'file' && <Button loading={busy} onClick={async () => { setBusy(true); setError(''); try { await preparationApi.download(`evidence/${id}/download`, evidence.data?.filename || 'document') } catch (caught) { setError(getApiErrorMessage(caught, 'The document could not be downloaded.')) } finally { setBusy(false) } }}>Download document</Button>}</>}><EvidencePreview id={id} />{error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}</Modal>
}
