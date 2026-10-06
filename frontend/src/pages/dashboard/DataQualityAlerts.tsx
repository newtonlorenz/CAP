import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'

type QualityItem = {
  requirement_id: string
  reference_id: string
  title?: string | null
  document_name: string
  current_status: string
  evidence_counts: { notes: number; files: number; links: number }
}

function Metric({
  label,
  value,
}: {
  label: string
  value: number
}) {
  return (
    <div className="rounded-lg border border-line bg-surface/80 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">{label}</div>
      <div className="dashboard-number mt-1 text-xl font-semibold text-ink">{value}</div>
    </div>
  )
}

export default function DataQualityAlerts({
  dataQuality,
}: {
  dataQuality: {
    evidenced_without_evidence: QualityItem[]
    evidence_without_evidenced_status: QualityItem[]
    unassigned_requirements_count: number
    unlinked_requirements_count: number
  } | null
}) {
  if (!dataQuality) return null

  const topActions = [
    ...dataQuality.evidenced_without_evidence.map((item) => ({
      key: `missing-${item.requirement_id}`,
      item,
      subtitle: 'Marked evidenced but no evidence objects',
    })),
    ...dataQuality.evidence_without_evidenced_status.map((item) => ({
      key: `status-${item.requirement_id}`,
      item,
      subtitle: 'Has evidence objects but not marked evidenced',
    })),
  ].slice(0, 3)

  return (
    <DashboardCard
      title="Data Quality"
      variant="subtle"
      className="dashboard-reveal"
      actions={
        <Link to="/requirements" className="text-sm font-medium text-accent hover:text-accent hover:underline">
          Review requirements
        </Link>
      }
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Unassigned" value={dataQuality.unassigned_requirements_count} />
        <Metric label="Unlinked" value={dataQuality.unlinked_requirements_count} />
        <Metric label="Evidenced mismatch" value={dataQuality.evidenced_without_evidence.length} />
        <Metric
          label="Status mismatch"
          value={dataQuality.evidence_without_evidenced_status.length}
        />
      </div>

      <div className="mt-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
          Top actions
        </div>
        {topActions.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line-strong bg-surface/60 px-3 py-4 text-sm text-muted">
            No data quality issues found.
          </div>
        ) : (
          <div className="space-y-2">
            {topActions.map((entry) => (
              <Link
                key={entry.key}
                to={`/requirements/${entry.item.requirement_id}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface/80 px-3 py-2 hover:border-brand-line"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-ink">
                    {entry.item.reference_id}
                  </div>
                  <div className="truncate text-xs text-muted">{entry.subtitle}</div>
                </div>
                <span className="shrink-0 text-xs font-semibold text-accent">Open</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </DashboardCard>
  )
}
