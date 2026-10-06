import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'

export default function DocumentBreakdown({
  rows,
}: {
  rows: Array<{
    document_id: string
    name: string
    document_type: string
    total: number
    evidenced: number
    percentage: number
  }>
}) {
  const top = rows.slice(0, 10)
  return (
    <DashboardCard title="By Document">
      <div className="space-y-3">
        {top.map((row) => {
          const label = `${row.name} (${row.document_type})`
          const content = (
            <>
              <div className="mb-1 flex items-start justify-between gap-3 text-sm">
                <div className="min-w-0 break-words text-ink font-medium">{label}</div>
                <div className="shrink-0 text-ink">
                  <span className="font-semibold">{row.evidenced}</span>/{row.total}{' '}
                  <span className="text-muted">({row.percentage}%)</span>
                </div>
              </div>
              <div className="h-2 w-full rounded-full bg-line">
                <div
                  className="h-2 rounded-full bg-indigo-600"
                  style={{ width: `${Math.min(100, Math.max(0, row.percentage))}%` }}
                />
              </div>
            </>
          )

          if (row.document_id === 'unassigned') {
            return (
              <div key={row.document_id} className="rounded-md border border-line p-3">
                {content}
              </div>
            )
          }

          return (
            <Link
              key={row.document_id}
              to={`/requirements?document_id=${encodeURIComponent(row.document_id)}`}
              className="block rounded-md border border-line p-3 hover:bg-canvas"
            >
              {content}
            </Link>
          )
        })}
        {top.length === 0 ? (
          <div className="text-sm text-muted">No requirements yet.</div>
        ) : null}
      </div>
    </DashboardCard>
  )
}

