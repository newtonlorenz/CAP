import { useState } from 'react'
import Button from './ui/Button'

type Props = {
  title: string
  description: string
  formats: readonly string[]
  disabled?: boolean
  onDownload: (format: string) => void
}

/** A report is one task; format is an option, not a separate competing action. */
export default function ReportDownloadRow({ title, description, formats, disabled, onDownload }: Props) {
  const [format, setFormat] = useState(formats[0])
  return <div className="flex flex-wrap items-center justify-between gap-3 py-4">
    <div className="min-w-0"><h3 className="font-semibold text-ink">{title}</h3><p className="mt-1 text-sm text-muted">{description}</p></div>
    <div className="flex shrink-0 items-center gap-2">
      {formats.length > 1 && <select aria-label={`${title} format`} value={format} onChange={event => setFormat(event.target.value)} disabled={disabled} className="min-h-10 px-3 py-2 text-sm">
        {formats.map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}
      </select>}
      <Button aria-label={`Download ${title} (${format.toUpperCase()})`} disabled={disabled} onClick={() => onDownload(format)}>Download{formats.length === 1 ? ` ${format.toUpperCase()}` : ''}</Button>
    </div>
  </div>
}
