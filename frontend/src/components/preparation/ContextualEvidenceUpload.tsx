import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import api from '../../api/client'
import { getApiErrorMessage } from '../../api/errors'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import type { PreparationEvidence } from '../../types/preparation'
import Button from '../ui/Button'

/** An uploaded file becomes current only after its answer attachment is saved. */
export default function ContextualEvidenceUpload({ ids, disabled, attach, onBusyChange, caseId }: {
  caseId?: string; ids: string[]; disabled: boolean; attach: (ids: string[]) => Promise<boolean>; onBusyChange?: (pending: boolean) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState('')
  const [uploaded, setUploaded] = useState<PreparationEvidence | null>(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState('')
  const [notice, setNotice] = useState('')
  const latestIds = useRef(ids)
  latestIds.current = ids
  const abort = useRef<AbortController | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false; abort.current?.abort() } }, [])
  const pending = busy || Boolean(file && !receipt)
  useDraftNavigationGuard(pending)
  useEffect(() => { onBusyChange?.(pending); return () => onBusyChange?.(false) }, [pending, onBusyChange])
  const save = async (chosen: File | null = file) => {
    if ((!chosen && !uploaded) || busy || disabled) return
    setBusy(true); setError(''); setReceipt(''); setNotice('')
    let evidence = uploaded
    try {
      if (!evidence && chosen) {
        abort.current = new AbortController()
        const body = new FormData()
        body.append('file', chosen)
        body.append('title', chosen.name)
        body.append('visibility', 'secret')
        if (caseId) body.append('case_id', caseId)
        const result = await api.post<PreparationEvidence>('/preparation/evidence/upload', body, {
          signal: abort.current.signal,
          onUploadProgress: (event) => { if (active.current) setProgress(event.total ? Math.round(event.loaded / event.total * 100) : 0) },
        })
        evidence = result.data
        if (!active.current) return
        setUploaded(evidence)
      }
      if (!evidence || !active.current) return
      const next = [...latestIds.current.filter(id => id !== replace), evidence.id]
      if (await attach([...new Set(next)])) {
        if (!active.current) return
        setReceipt(`${evidence.filename || evidence.title} attached to this answer · ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}. Pending acceptance.`)
        setFile(null); setUploaded(null); setReplace('')
        if (input.current) input.current.value = ''
      } else if (active.current) setError('The file uploaded, but was not attached. The current attachment is unchanged. Resolve any save error above, then retry attaching this file.')
    } catch (caught) {
      if (!active.current) return
      setError(evidence ? 'The file uploaded, but was not attached. Retry attaching it; no new upload is needed.' : axios.isCancel(caught) ? 'Upload cancelled. The file has not been attached. The current attachment is unchanged.' : getApiErrorMessage(caught, 'Upload interrupted. The file has not been attached. The current attachment is unchanged.'))
    } finally { if (active.current) setBusy(false) }
  }
  return <div className="pilot-upload">
    {receipt && <p className="pilot-receipt" role="status">{receipt}</p>}
    {ids.length > 0 && <label className="pilot-replacement-label">Attachment action<select aria-label="Attachment action" value={replace} disabled={busy || disabled || Boolean(uploaded)} onChange={event => setReplace(event.target.value)}><option value="">Add another attachment</option>{ids.map((id, index) => <option key={id} value={id}>Replace attachment {index + 1}</option>)}</select></label>}
    <Button size="sm" disabled={busy || disabled} onClick={() => input.current?.click()}>{file ? 'Choose a different file' : 'Upload evidence'}</Button>
    <input ref={input} className="sr-only" tabIndex={-1} type="file" aria-label="Upload evidence for this answer" disabled={busy || disabled} onChange={event => { setFile(event.target.files?.[0] || null); setUploaded(null); setError(''); setReceipt(''); setNotice(''); setProgress(0) }} />
    {file && <p className="pilot-upload-filename">{file.name}</p>}
    {file && !busy && <Button size="sm" variant="ghost" onClick={() => { if (uploaded) setNotice('The uploaded file remains in the evidence library. It is not attached to this answer.'); setFile(null); setUploaded(null); setError(''); setReplace(''); if (input.current) input.current.value = '' }}>{uploaded ? 'Leave file unattached' : 'Cancel attachment'}</Button>}
    {notice && <p role="status" className="text-sm text-muted">{notice}</p>}
    {error && <p role="alert" className="pilot-upload-error">{error}</p>}
    {busy ? <div className="flex flex-wrap items-center gap-3"><progress aria-label="Evidence upload progress" value={progress} max={100} /><span role="status">{uploaded ? 'Saving attachment…' : `Uploading ${progress}%`}</span>{!uploaded && <Button size="sm" onClick={() => abort.current?.abort()}>Cancel upload</Button>}</div> : file && <Button variant="primary" size="sm" disabled={disabled} onClick={() => void save()}>{uploaded ? 'Retry attaching uploaded file' : error ? 'Retry upload' : replace ? 'Upload replacement and attach' : 'Upload and attach'}</Button>}
    <p className="text-xs text-muted">{caseId && <>File uses this form’s access. </>}The current attachment stays in place until both upload and answer save succeed.</p>
  </div>
}
