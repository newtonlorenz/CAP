import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'
import { formatStatus } from './status'

export default function StatusBreakdown({
  rows,
}: {
  rows: Array<{ status: string; total: number; percentage_of_total: number }>
}) {
  return (
    <DashboardCard title="Status Snapshot" variant="subtle" className="dashboard-reveal">
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.status} className="rounded-lg border border-line bg-surface/70 p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Link
                to={`/requirements?status=${encodeURIComponent(row.status)}`}
                className="font-medium text-ink hover:underline"
              >
                {formatStatus(row.status)}
              </Link>
              <div className="dashboard-number text-sm text-ink">
                <span className="font-semibold">{row.total}</span>{' '}
                <span className="text-muted">({row.percentage_of_total}%)</span>
              </div>
            </div>
            <div className="dashboard-progress-track mt-2 h-1.5 w-full rounded-full">
              <div
                className="dashboard-progress-fill-cyan h-1.5 rounded-full"
                style={{ width: `${Math.min(100, Math.max(0, row.percentage_of_total))}%` }}
              />
            </div>
          </div>
        ))}
        {rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line-strong bg-surface/60 px-3 py-4 text-sm text-muted">
            No requirements yet.
          </div>
        ) : null}
      </div>
    </DashboardCard>
  )
}
