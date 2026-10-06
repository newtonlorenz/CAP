import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type { PaginatedResponse, ProductFeedbackReport, ProductFeedbackStatus } from '../../types'
import { formatDateTime } from '../../utils/dateFormat'

const statuses = { new: 'New', in_progress: 'In progress', done: 'Done' }
const kinds = { bug: 'Bug', feature: 'Feature request', other: 'Other' }
const endpoint = '/product-feedback'

export default function ProductFeedback() {
  const [status, setStatus] = useState<ProductFeedbackStatus | ''>('')
  const [page, setPage] = useState(0)
  const [preview, setPreview] = useState<string | null>(null)
  const [imageError, setImageError] = useState(false)
  const queryClient = useQueryClient()
  const config = useQuery({ queryKey: ['product-feedback-admin-config'],
    queryFn: async () => (await api.get<{ enabled: boolean }>(`${endpoint}/config`)).data })
  const reports = useQuery({ queryKey: ['product-feedback', status, page],
    queryFn: async () => (await api.get<PaginatedResponse<ProductFeedbackReport>>(endpoint,
      { params: { skip: page * 20, limit: 20, status: status || undefined } })).data,
    enabled: config.data?.enabled === true,
  })
  const update = useMutation({
    mutationFn: ({ id, value }: { id: string; value: ProductFeedbackStatus }) => api.patch(`${endpoint}/${id}`, { status: value }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['product-feedback'] }) },
  })
  return <div className="mx-auto max-w-5xl space-y-5">
    <header><h1>Product feedback</h1><p className="mt-2 text-sm text-muted">Bugs and ideas reported by your organization.</p></header>
    {config.isLoading && <p role="status">Loading feedback…</p>}
    {config.isError && <p role="alert">Could not check feedback availability. <button className="underline" onClick={() => void config.refetch()}>Retry</button></p>}
    {config.data?.enabled === false && <p className="rounded-xl border border-line bg-surface p-5 text-muted">Product feedback is not configured. Connect the Page Feedback service to enable the widget and inbox.</p>}
    {config.data?.enabled && <>
      <label className="flex items-center gap-3 text-sm">Status <select aria-label="Filter feedback by status" className="px-3 py-2"
        value={status} onChange={event => { setStatus(event.target.value as ProductFeedbackStatus | ''); setPage(0); setPreview(null) }}>
        <option value="">All statuses</option>{Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      {reports.isLoading && <p role="status">Loading reports…</p>}
      {reports.isError && <p role="alert" className="text-danger">Could not load feedback. <button className="underline" onClick={() => void reports.refetch()}>Retry</button></p>}
      {update.isError && <p role="alert" className="text-danger">Could not update the status. Please try again.</p>}
      {reports.data?.items.length === 0 && <p className="rounded-xl border border-line bg-surface p-8 text-center text-muted">No feedback{status ? ' with this status' : ' yet'}.</p>}
      {reports.data?.items.map(report => <article key={report.id} className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><span className="text-sm font-semibold">{kinds[report.kind]}</span><span className="ml-3 text-xs text-muted">{formatDateTime(report.created_at)}</span></div>
          <select aria-label={`Status for ${report.message.slice(0, 60)}`} className="px-3 py-2 text-sm" value={report.status} disabled={update.isPending}
            onChange={event => update.mutate({ id: report.id, value: event.target.value as ProductFeedbackStatus })}>
            {Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></div>
        <p className="mt-4 whitespace-pre-wrap break-words text-sm">{report.message}</p>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted">
          <span className="break-all">Page: {report.page_path}</span>
          {report.pin && <span>① Element pinned</span>}
          {report.has_screenshot && <button className="font-semibold text-accent underline" onClick={() => { setImageError(false); setPreview(preview === report.id ? null : report.id) }}>{preview === report.id ? 'Hide screenshot' : 'View screenshot'}</button>}
        </div>
        {report.pin && <details className="mt-3 text-xs text-muted"><summary>Element reference</summary><code className="mt-2 block break-all">{report.pin.selector}</code></details>}
        {preview === report.id && (imageError ? <p role="alert" className="mt-4 text-sm text-danger">Could not load screenshot. Close it and try again.</p> :
          <img data-feedback-private="" className="mt-4 max-h-[70vh] w-full rounded-lg border border-line object-contain" alt="Screenshot attached to this report"
            src={`${import.meta.env.BASE_URL}api/v1/product-feedback/${report.id}/screenshot`} onError={() => setImageError(true)} />)}
      </article>)}
      {reports.data && reports.data.total > 20 && <div className="flex items-center justify-between text-sm">
        <button disabled={page === 0} onClick={() => setPage(value => value - 1)}>Previous</button>
        <span>Page {page + 1} of {Math.ceil(reports.data.total / 20)}</span>
        <button disabled={(page + 1) * 20 >= reports.data.total} onClick={() => setPage(value => value + 1)}>Next</button>
      </div>}
    </>}
  </div>
}
