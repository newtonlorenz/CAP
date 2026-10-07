import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../api/client'
import { preparationApi } from '../../api/preparation'
import Button from '../ui/Button'

export default function EvidencePreview({ id }: { id: string }) {
  const item = useQuery({ queryKey: ['preparation', 'evidence', 'item', id], queryFn: () => preparationApi.getEvidence(id) })
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const evidence = item.data
  const previewable = evidence?.kind === 'file' && /\.(pdf|png|jpg|jpeg|webp|gif)$/i.test(evidence.filename || '')
  useEffect(() => {
    let alive = true
    let objectUrl = ''
    setUrl(''); setError('')
    if (previewable) void api.get<Blob>(`/preparation/evidence/${id}/download`, { responseType: 'blob' }).then(async result => {
      if (!alive) return
      // Downloads deliberately use octet-stream; give only supported passive formats their preview MIME.
      const extension = evidence?.filename?.split('.').pop()?.toLowerCase() || ''
      const mime: Record<string, string> = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif' }
      if (extension === 'pdf' && !((await result.data.slice(0, 5).text()) === '%PDF-')) throw new Error('Invalid PDF header')
      if (!alive) return
      objectUrl = URL.createObjectURL(new Blob([result.data], { type: mime[extension] || 'application/octet-stream' })); setUrl(objectUrl)
    }).catch(() => { if (alive) setError('The evidence preview could not be loaded.') })
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [id, previewable, attempt, evidence?.filename])
  return <section className="pilot-evidence-preview" aria-label="Selected evidence preview"><header><strong>{evidence?.filename || evidence?.title || 'Evidence preview'}</strong>{url && <a href={url} target="_blank" rel="noopener noreferrer">Open full size</a>}</header>
    {item.isError || error ? <p role="alert">{error || 'Evidence details could not be loaded.'} <Button size="sm" onClick={() => { setAttempt(value => value + 1); void item.refetch() }}>Retry preview</Button></p> : item.isLoading || (previewable && !url) ? <p role="status">Loading evidence preview…</p> : url ? /\.pdf$/i.test(evidence?.filename || '') ? <iframe title={`Evidence preview: ${evidence?.title}`} src={url} /> : <img src={url} alt={evidence?.title} /> : <div className="p-5"><p>{evidence?.body || 'A preview is not available for this file type. Open the attachment above to review its contents.'}</p>{evidence?.link_url && /^https?:\/\//i.test(evidence.link_url) && <a href={evidence.link_url} target="_blank" rel="noopener noreferrer">Open evidence link</a>}</div>}
  </section>
}
