import DashboardCard from './DashboardCard'

export default function DocumentTypeBreakdown({
  rows,
}: {
  rows: Array<{ document_type: string; total: number; evidenced: number; percentage: number }>
}) {
  return (
    <DashboardCard title="By Document Type">
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.document_type}>
            <div className="mb-1 flex items-start justify-between gap-3 text-sm">
              <div className="min-w-0">
                <div className="break-words font-medium text-ink">
                  {row.document_type}
                </div>
                <div className="text-xs text-muted">
                  {row.evidenced} / {row.total} evidenced
                </div>
              </div>
              <div className="shrink-0 font-semibold text-ink">{row.percentage}%</div>
            </div>
            <div className="h-2 w-full rounded-full bg-line">
              <div
                className="h-2 rounded-full bg-brand"
                style={{ width: `${Math.min(100, Math.max(0, row.percentage))}%` }}
              />
            </div>
          </div>
        ))}
        {rows.length === 0 ? (
          <div className="text-sm text-muted">No documents yet.</div>
        ) : null}
      </div>
    </DashboardCard>
  )
}

