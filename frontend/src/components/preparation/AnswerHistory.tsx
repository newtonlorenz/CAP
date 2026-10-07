import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { pilotReviewApi } from '../../api/pilotReview'
import { formatDateTime } from '../../utils/dateFormat'
import type { AnswerHistoryItem } from '../../types/pilotReview'
import Button from '../ui/Button'
import EvidenceAttachments from './EvidenceAttachments'

function Snapshot({ value }: { value: unknown }) {
  if (!value || typeof value !== 'object') return <p>No earlier answer recorded.</p>
  const record = value as Record<string, unknown>
  return <div className="pilot-history-snapshot">
    <p className="whitespace-pre-wrap break-words">{record.not_applicable_reason ? `Not applicable: ${String(record.not_applicable_reason)}` : record.value == null ? 'No answer text' : String(record.value)}</p>
    {Array.isArray(record.evidence_ids) && <EvidenceAttachments ids={record.evidence_ids.filter((id): id is string => typeof id === 'string')} />}
    {typeof record.comment === 'string' && <p>{record.comment}</p>}
  </div>
}

function HistoryEvent({ event }: { event: AnswerHistoryItem }) {
  const [open, setOpen] = useState(false)
  return <li><p><strong>{event.action.replace(/_/g, ' ')}</strong> · {event.user_name || 'User'} · {formatDateTime(event.timestamp)}</p><details open={open} onToggle={change => setOpen(change.currentTarget.open)}><summary>Compare recorded change</summary>{open && <><h4>Before</h4><Snapshot value={event.details.old_value} /><h4>After</h4><Snapshot value={event.details.new_value} /></>}</details></li>
}

export default function AnswerHistory({ caseId, fieldKey, revision }: { caseId: string; fieldKey: string; revision: number }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['preparation', 'answer-history', caseId, fieldKey, revision], queryFn: () => pilotReviewApi.history(caseId, fieldKey), enabled: open })
  return <details className="pilot-answer-history" open={open} onToggle={event => setOpen(event.currentTarget.open)}><summary>Answer history</summary>
    {open && (query.isLoading ? <p role="status">Loading answer history…</p> : query.isError ? <p role="alert">Answer history could not be loaded. <Button size="sm" onClick={() => void query.refetch()}>Retry</Button></p> : query.data?.items.length ? <ol>{query.data.items.map(event => <HistoryEvent key={event.id} event={event} />)}</ol> : <p>No answer history recorded.</p>)}
    {open && <p className="text-xs text-muted">Historical attachment references do not guarantee that earlier file contents remain available. Approved pack snapshots preserve their own evidence.</p>}
  </details>
}
