import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { pilotReviewApi } from '../../api/pilotReview'
import type { PilotPreparationCase } from '../../types/pilotReview'
import type { CaseWrites } from '../../hooks/preparation/useCaseWrites'
import Button from '../ui/Button'

export default function ReviewerAssignment({ item, writes }: { item: PilotPreparationCase; writes: CaseWrites }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(item.reviewer_id || '')
  const reviewers = useQuery({ queryKey: ['preparation', 'reviewers', item.id], queryFn: () => pilotReviewApi.reviewers(item.id), enabled: open })
  return <div className="pilot-reviewer-assignment"><p>Answer review owner: <strong>{item.reviewer_name || 'Unassigned'}</strong>{item.reviewer_source && item.reviewer_source !== 'case' && <span> · Inherited from {item.reviewer_source === 'pack' ? 'licence pack' : 'programme'}</span>} <button type="button" className="text-accent underline" onClick={() => { setSelected(item.reviewer_id || ''); setOpen(!open) }} aria-expanded={open}>Change review owner</button></p>
    {open && <div className="mt-3 flex flex-wrap items-center gap-3">{reviewers.isLoading ? <p role="status">Loading eligible reviewers…</p> : reviewers.isError ? <p role="alert">Review owners could not be loaded. <Button size="sm" onClick={() => void reviewers.refetch()}>Retry</Button></p> : <><label>Review owner<select className="ml-2 px-3 py-2" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Review owner unassigned</option>{reviewers.data?.items.map(reviewer => <option key={reviewer.id} value={reviewer.id}>{reviewer.full_name}</option>)}</select></label><Button size="sm" disabled={writes.isWriting || writes.hasPendingDrafts || Boolean(writes.pauseReason)} onClick={async () => { if (await writes.run(revision => pilotReviewApi.assignReviewer(item.id, selected || null, revision))) setOpen(false) }}>Save review owner</Button></>}<p className="w-full text-xs text-muted">Assignment coordinates the next action. It does not grant access or approval permission.</p></div>}
  </div>
}
