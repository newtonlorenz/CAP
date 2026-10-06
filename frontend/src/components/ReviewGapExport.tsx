import { useState } from 'react'
import api from '../api/client'
import Modal from './ui/Modal'
import Button from './ui/Button'

export default function ReviewGapExport({ open, cycleId, cycleName, onClose }: {
  open: boolean; cycleId: string; cycleName: string; onClose: () => void
}) {
  const [format, setFormat] = useState('pdf')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const download = async () => {
    setBusy(true); setError('')
    try {
      const response = await api.get(`/reports/gap-analysis?review_cycle_id=${encodeURIComponent(cycleId)}&format=${format}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = `${cycleName.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'review'}-gap-analysis.${format}`
      document.body.append(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      onClose()
    } catch {
      setError('The gap analysis could not be downloaded. Please try again.')
    } finally { setBusy(false) }
  }
  return <Modal open={open} title="Export review gap analysis" onClose={() => { if (!busy) onClose() }}
    footer={<><Button disabled={busy} onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy} onClick={download}>{busy ? 'Preparing report…' : 'Download gap analysis'}</Button></>}>
    <p className="text-sm font-semibold text-ink">{cycleName}</p>
    <p className="mt-2 text-sm text-muted">Includes all requirements you can access in this review, regardless of page filters: readiness, outstanding actions, owners, evidence and review decisions. Informational sections are counted separately.</p>
    <fieldset className="mt-5 space-y-4">
      <legend className="mb-3 text-sm font-semibold">Report format</legend>
      {[
        ['pdf', 'PDF report', 'A shareable summary with owner workloads and detailed actions for every gap.'],
        ['xlsx', 'Excel workbook', 'Filterable action register, owner summary and all assessed requirements.'],
        ['csv', 'CSV data', 'All assessed requirements and gap reasons for further analysis.'],
      ].map(([value, label, description]) => <label key={value} className="flex cursor-pointer gap-3 text-sm">
        <input type="radio" name="gap-format" value={value} checked={format === value} disabled={busy} onChange={() => setFormat(value)} className="mt-1" />
        <span><span className="block font-semibold">{label}</span><span className="block text-muted">{description}</span></span>
      </label>)}
    </fieldset>
    {error && <p role="alert" className="mt-4 text-sm text-danger">{error}</p>}
  </Modal>
}
