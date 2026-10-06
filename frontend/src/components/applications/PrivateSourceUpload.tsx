import { useState } from 'react'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import Button from '../ui/Button'

export default function PrivateSourceUpload({ onUploaded, disabled = false }: { onUploaded: (id: string) => void; disabled?: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const upload = async () => {
    if (!file) return
    setBusy(true); setError('')
    try {
      const body = new FormData()
      body.append('file', file)
      body.append('title', title.trim() || file.name)
      body.append('visibility', 'secret')
      const created = await preparationApi.uploadEvidence(body)
      onUploaded(created.id)
      setFile(null)
      setTitle('')
    } catch (caught) { setError(getApiErrorMessage(caught, 'The file could not be uploaded.')) }
    finally { setBusy(false) }
  }
  return <div className="flex flex-wrap items-end gap-3"><label className="min-w-0 max-w-full text-sm font-medium">Upload a private source file<input className="mt-1 block w-full max-w-full text-sm" type="file" disabled={disabled || busy} onChange={(event) => setFile(event.target.files?.[0] || null)} /></label><label className="min-w-0 max-w-full text-sm font-medium">Title (optional)<input className="mt-1 block w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm" value={title} placeholder={file?.name || 'Use filename'} disabled={disabled || busy} onChange={(event) => setTitle(event.target.value)} /></label><Button size="sm" disabled={!file || disabled || busy} onClick={() => void upload()}>{busy ? 'Uploading…' : 'Upload and attach'}</Button>{error && <p role="alert" className="w-full text-sm text-danger">{error}</p>}</div>
}
