import { formatDate } from '../../utils/dateFormat'
import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'

export default function ReviewCyclesPanel({
  cycles,
}: {
  cycles: Array<{
    id: string
    name: string
    deadline: string | null
    progress: { total: number; completed: number; pending: number }
    due_in_days: number | null
    my_pending_count: number | null
  }>
}) {
  return (
    <DashboardCard
      title="Active requirement assessments"
      actions={
        <span className="dashboard-number rounded-full border border-line bg-surface/70 px-2.5 py-1 text-xs font-semibold text-ink">
          {cycles.length} active
        </span>
      }
      className="dashboard-reveal"
    >
      <div className="divide-y divide-line">
        {cycles.slice(0, 5).map((cycle) => {
          const pct =
            cycle.progress.total > 0
              ? Math.round((cycle.progress.completed / cycle.progress.total) * 100)
              : 0
          const dueLabel =
            cycle.due_in_days === null
              ? 'No deadline'
              : cycle.due_in_days < 0
                ? `${Math.abs(cycle.due_in_days)}d overdue`
                : `${cycle.due_in_days}d left`

          return (
            <div key={cycle.id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link
                    to={`/review-cycles/${cycle.id}?mode=focus`}
                    className="font-semibold text-ink hover:underline"
                  >
                    {cycle.name}
                  </Link>
                  <div className="mt-1 text-xs text-muted">
                    {cycle.deadline
                      ? `Deadline ${formatDate(cycle.deadline)}`
                      : 'No deadline'}
                    {cycle.deadline ? ` · ${dueLabel}` : ''}
                    {(cycle.my_pending_count ?? 0) > 0
                      ? ` · My pending: ${cycle.my_pending_count}`
                      : ''}
                  </div>
                </div>
                <div className="dashboard-number shrink-0 text-sm font-semibold text-ink">
                  {pct}%
                </div>
              </div>
              <div className="dashboard-progress-track mt-2 h-2 w-full rounded-full">
                <div
                  className="dashboard-progress-fill-emerald h-2 rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                />
              </div>
              <div className="mt-2 text-xs text-muted">
                {cycle.progress.completed} completed · {cycle.progress.pending} pending ·{' '}
                {cycle.progress.total} total
              </div>
            </div>
          )
        })}
        {cycles.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-4 py-5 text-sm text-muted">
            No active requirement assessments.
          </div>
        ) : null}
      </div>
      {cycles.length > 5 && <Link to="/review-cycles" className="mt-4 inline-flex min-h-10 items-center text-sm font-semibold text-accent hover:underline">View all {cycles.length} active requirement assessments</Link>}
    </DashboardCard>
  )
}
