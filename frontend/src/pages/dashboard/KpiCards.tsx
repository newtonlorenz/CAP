import DashboardCard from './DashboardCard'

function MetricTile({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: string
  detail: string
  tone: 'cyan' | 'emerald' | 'amber'
}) {
  const toneClass = tone === 'amber' ? 'text-warning' : tone === 'emerald' ? 'text-success' : 'text-ink'

  return (
    <div className="px-1 py-2 sm:px-4">
      <div className="text-xs font-semibold text-muted">
        {label}
      </div>
      <div className={`dashboard-kpi-value mt-2 text-2xl font-bold tracking-tight ${toneClass}`}>{value}</div>
      <div className="mt-1 text-sm text-muted">{detail}</div>
    </div>
  )
}

export default function KpiCards({
  overall,
  mandatory,
  atRiskCount,
}: {
  overall: { total: number; evidenced: number; percentage: number }
  mandatory: { total: number; evidenced: number; percentage: number }
  atRiskCount: number
}) {
  return (
    <DashboardCard title="Compliance Overview" >
      <p className="mb-4 text-sm text-muted">Current approved baselines and standalone controls. Informational sections and exclusions are excluded from coverage.</p>
      <div className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <MetricTile
          label="Evidence coverage"
          value={overall.total ? `${overall.percentage}%` : '—'}
          detail={overall.total ? `${overall.evidenced} of ${overall.total} applicable controls evidenced` : 'No applicable controls in this scope'}
          tone="cyan"
        />
        <MetricTile
          label="Mandatory coverage"
          value={mandatory.total ? `${mandatory.percentage}%` : '—'}
          detail={mandatory.total ? `${mandatory.evidenced} of ${mandatory.total} mandatory requirements evidenced` : 'No mandatory requirements in this scope'}
          tone="emerald"
        />
        <MetricTile
          label="At-risk items"
          value={`${atRiskCount}`}
          detail="Requirements currently in progress or blocked"
          tone="amber"
        />
      </div>

    </DashboardCard>
  )
}
