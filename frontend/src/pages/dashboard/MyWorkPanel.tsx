import { formatDateTime, formatDate } from '../../utils/dateFormat'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'
import { formatReviewStatus, formatStatus, statusClass } from './status'

type RequirementItem = {
  requirement_id: string
  reference_id: string
  title?: string | null
  document_name: string
  status: string
  action_reasons?: string[]
  last_changed_at?: string | null
}

type ReviewItem = {
  cycle_id: string
  cycle_name: string
  deadline?: string | null
  review_item_id: string
  requirement_reference_id: string
  requirement_title?: string | null
  review_status: string
  action_reasons?: string[]
  project_id?: string | null
  project_name?: string | null
  change_entry_id?: string | null
  change_title?: string | null
}

type FormItem = { case_id: string; name: string; kind?: string; status: string; owner_id: string | null; due_date: string | null; application_id?: string | null; application_name?: string | null; project_id?: string | null; project_name?: string | null }
type QueryItem = { query_id: string; application_id: string; application_name: string; question: string; status: string; owner_id: string | null; due_date: string | null }
type WorkQueue<T> = { total: number; items: T[] }
type WorkMode = 'requirements' | 'review_items' | 'forms' | 'authority_queries'

function deadlineLabel(value: string) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return `${new Date(value) < today ? 'Overdue since' : 'Due'} ${formatDate(value)}`
}

function TabButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={[
        'flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors',
        active
          ? 'border-brand-line bg-brand-soft text-accent'
          : 'border-line bg-surface text-muted hover:border-line-strong',
      ].join(' ')}
    >
      <span>{label}</span>
      <span className="dashboard-number rounded-md bg-subtle px-2 py-0.5 text-xs font-semibold text-ink">
        {count}
      </span>
    </button>
  )
}

function RequirementRow({ item }: { item: RequirementItem }) {
  return (
    <div className="border-b border-line py-4 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/requirements/${item.requirement_id}`} className="font-semibold text-ink hover:underline">
            {item.reference_id}
          </Link>
          <div className="mt-1 break-words text-sm text-muted">{item.title || item.document_name}</div>
          {item.action_reasons?.map(reason => <p key={reason} className="mt-2 text-sm font-medium text-ink">{reason}</p>)}
          <div className="mt-1 text-sm text-muted">
            {item.last_changed_at
              ? `Updated ${formatDateTime(item.last_changed_at)}`
              : 'No status updates yet'}
          </div>
        </div>
        <span className={['shrink-0 rounded px-2 py-0.5 text-xs font-semibold', statusClass(item.status)].join(' ')}>
          {formatStatus(item.status)}
        </span>
      </div>
    </div>
  )
}

function ReviewItemRow({ item }: { item: ReviewItem }) {
  return (
    <div className="border-b border-line py-4 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/review-cycles/${item.cycle_id}?mode=focus&item=${item.review_item_id}`} className="font-semibold text-ink hover:underline">
            {item.requirement_reference_id}
          </Link>
          <div className="mt-1 text-sm text-muted">
            {item.cycle_name}
            {item.deadline ? ` · ${deadlineLabel(item.deadline)}` : ''}
          </div>
          {item.action_reasons?.map(reason => <p key={reason} className="mt-2 text-sm font-medium text-ink">{reason}</p>)}
          {item.project_id && <Link to={`/certification-projects?project=${encodeURIComponent(item.project_id)}`} className="mt-1 block text-xs text-accent hover:underline">{item.project_name || 'Certification project'}</Link>}
          {item.change_entry_id && <Link to={`/change-management?change=${encodeURIComponent(item.change_entry_id)}&tab=changes`} className="mt-1 block text-xs text-accent hover:underline">{item.change_title || 'Change assessment'}</Link>}
          {item.requirement_title ? (
            <div className="mt-1 break-words text-sm text-muted">{item.requirement_title}</div>
          ) : null}
        </div>
        <span
          className={['shrink-0 rounded px-2 py-0.5 text-xs font-semibold', statusClass(item.review_status)].join(
            ' ',
          )}
        >
          {formatReviewStatus(item.review_status)}
        </span>
      </div>
    </div>
  )
}

export default function MyWorkPanel({
  assignedRequirements,
  assignedReviewItems,
  primaryMode,
  assignedForms = { total: 0, items: [] },
  authorityQueries = { total: 0, items: [] },
  scope = 'unresolved', page = 1, pageSize = 5, expanded = false,
  onScopeChange, onModeChange, onPageChange, onExpand,
}: {
  assignedRequirements: {
    total: number
    items: RequirementItem[]
  }
  assignedReviewItems: {
    total: number
    items: ReviewItem[]
  }
  primaryMode: WorkMode
  assignedForms?: WorkQueue<FormItem>
  authorityQueries?: WorkQueue<QueryItem>
  scope?: 'all' | 'unresolved'
  page?: number
  pageSize?: number
  expanded?: boolean
  onScopeChange?: (scope: 'all' | 'unresolved') => void
  onModeChange?: (mode: WorkMode) => void
  onPageChange?: (page: number) => void
  onExpand?: () => void
}) {
  const [activeMode, setActiveMode] = useState<WorkMode>(primaryMode)

  useEffect(() => {
    setActiveMode(primaryMode)
  }, [primaryMode])

  const selectMode = (mode: WorkMode) => { setActiveMode(mode); onModeChange?.(mode) }
  const total = activeMode === 'requirements' ? assignedRequirements.total : activeMode === 'review_items' ? assignedReviewItems.total : activeMode === 'forms' ? assignedForms.total : authorityQueries.total
  const rows = useMemo(
    () => activeMode === 'requirements' ? assignedRequirements.items : activeMode === 'review_items' ? assignedReviewItems.items : activeMode === 'forms' ? assignedForms.items : authorityQueries.items,
    [activeMode, assignedRequirements.items, assignedReviewItems.items, assignedForms.items, authorityQueries.items],
  )

  const emptyState =
    activeMode === 'requirements' ? 'No assigned requirements.' : activeMode === 'review_items' ? 'No assigned requirement assessments.' : activeMode === 'forms' ? 'No assigned active forms.' : 'No open authority queries assigned to you.'

  return (
    <DashboardCard
      title="Assigned work"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <TabButton
            label="Requirements"
            count={assignedRequirements.total}
            active={activeMode === 'requirements'}
            onClick={() => selectMode('requirements')}
          />
          <TabButton
            label="Requirement assessments"
            count={assignedReviewItems.total}
            active={activeMode === 'review_items'}
            onClick={() => selectMode('review_items')}
          />
          <TabButton label="Forms" count={assignedForms.total} active={activeMode === 'forms'} onClick={() => selectMode('forms')} />
          <TabButton label="Authority queries" count={authorityQueries.total} active={activeMode === 'authority_queries'} onClick={() => selectMode('authority_queries')} />
        </div>
      }
      className="dashboard-reveal"
    >
      {onScopeChange && <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Assignment scope">
        <button type="button" aria-pressed={scope === 'unresolved'} onClick={() => onScopeChange('unresolved')} className={`min-h-10 rounded-lg border px-3 text-sm font-semibold ${scope === 'unresolved' ? 'border-brand-line bg-brand-soft text-accent' : 'border-line text-ink'}`}>Needs attention</button>
        <button type="button" aria-pressed={scope === 'all'} onClick={() => onScopeChange('all')} className={`min-h-10 rounded-lg border px-3 text-sm font-semibold ${scope === 'all' ? 'border-brand-line bg-brand-soft text-accent' : 'border-line text-ink'}`}>All assigned</button>
        <p className="w-full text-sm text-muted">{activeMode === 'forms' || activeMode === 'authority_queries' ? 'Your active forms and open authority queries, earliest deadlines first.' : scope === 'unresolved' ? 'Your unresolved assignments, with the action needed to complete each item.' : 'All your assignments in active work, including completed assessments.'}</p>
      </div>}
      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-4 py-6 text-sm text-muted">
          {total > 0 ? <>This page has no assignments. <button type="button" onClick={() => onPageChange?.(1)} className="font-semibold text-accent underline">Return to the first page</button></> : scope === 'unresolved' && (activeMode === 'requirements' || activeMode === 'review_items') ? 'No assigned work needs attention in this queue.' : emptyState}
        </div>
      ) : (
        <div className="space-y-2">
          {activeMode === 'requirements'
            ? assignedRequirements.items.slice(0, pageSize).map((item) => (
                <RequirementRow key={item.requirement_id} item={item} />
              ))
            : activeMode === 'review_items' ? assignedReviewItems.items.slice(0, pageSize).map((item) => (
                <ReviewItemRow key={item.review_item_id} item={item} />
              )) : activeMode === 'forms' ? assignedForms.items.slice(0, pageSize).map(item => <div key={item.case_id} className="border-b border-line py-3">
                <Link to={item.application_id ? `/licence-applications?application=${encodeURIComponent(item.application_id)}&case=${encodeURIComponent(item.case_id)}` : `${item.kind === 'licence_application' ? '/licence-applications' : '/preparation'}?case=${encodeURIComponent(item.case_id)}`} className="font-semibold text-ink hover:underline">{item.name}</Link>
                <p className="mt-2 text-sm font-medium text-ink">Continue the assigned form</p>
                <p className="mt-1 text-sm text-muted">{item.application_name || item.project_name || 'Standalone form'} · {item.due_date ? deadlineLabel(item.due_date) : 'No deadline set'}</p>
                {item.application_id && <Link to={`/licence-applications?application=${encodeURIComponent(item.application_id)}`} className="mt-1 inline-block text-xs text-accent hover:underline">Open application</Link>}
                {!item.application_id && item.project_id && <Link to={`/certification-projects?project=${encodeURIComponent(item.project_id)}`} className="mt-1 inline-block text-xs text-accent hover:underline">Open certification project</Link>}
              </div>) : authorityQueries.items.slice(0, pageSize).map(item => <div key={item.query_id} className="border-b border-line py-3">
                <Link to={`/licence-applications?application=${encodeURIComponent(item.application_id)}#authority-queries`} className="font-semibold text-ink hover:underline">{item.application_name}</Link>
                <p className="mt-1 break-words text-sm text-muted">{item.question}</p>
                <p className="mt-1 text-sm text-muted">Respond to the authority query · {item.due_date ? deadlineLabel(item.due_date) : 'No deadline set'}</p>
              </div>)}
        </div>
      )}
      {!expanded && total > pageSize && onExpand && <button type="button" onClick={onExpand} className="mt-3 inline-flex min-h-10 items-center text-sm font-semibold text-accent underline">View all {total} in this queue</button>}
      {expanded && <div className="mt-4 flex flex-wrap items-center justify-between gap-3" aria-label="My work pages">
        <p className="text-sm text-muted">{total ? (page - 1) * pageSize >= total ? `${total} assignments in this queue` : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}` : '0 assignments'}</p>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => onPageChange?.(page - 1)} className="min-h-10 rounded-lg border border-line px-3 text-sm disabled:opacity-50">Previous</button>
          <button type="button" disabled={page * pageSize >= total} onClick={() => onPageChange?.(page + 1)} className="min-h-10 rounded-lg border border-line px-3 text-sm disabled:opacity-50">Next</button>
        </div>
      </div>}

    </DashboardCard>
  )
}
