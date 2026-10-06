import { formatDate } from '../../utils/dateFormat'
import DashboardCard from './DashboardCard'
import type { ReactNode } from 'react'

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export default function SnapshotTrend({
  snapshots,
  actions,
}: {
  snapshots: Array<{
    id: string
    name: string
    total_requirements: number
    evidenced_requirements: number
    created_at: string
  }>
  actions?: ReactNode
}) {
  const points = [...snapshots].reverse().slice(-20)
  const width = 640
  const height = 160
  const pad = 18
  const innerW = width - pad * 2
  const innerH = height - pad * 2

  const maxTotal = Math.max(1, ...points.map((p) => p.total_requirements))
  const xFor = (idx: number) =>
    points.length <= 1 ? pad : pad + (idx / (points.length - 1)) * innerW
  const yFor = (value: number) => pad + (1 - value / maxTotal) * innerH

  const evidencePath = points
    .map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${xFor(idx)} ${yFor(p.evidenced_requirements)}`)
    .join(' ')

  const totalPath = points
    .map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${xFor(idx)} ${yFor(p.total_requirements)}`)
    .join(' ')

  const latest = points[points.length - 1]
  const percent = latest
    ? clamp((latest.evidenced_requirements / Math.max(1, latest.total_requirements)) * 100, 0, 100)
    : 0

  const header = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {latest ? (
        <div className="text-sm text-muted">
          Latest snapshot:{' '}
          <span className="dashboard-number font-semibold text-ink">
            {percent.toFixed(1)}%
          </span>
        </div>
      ) : null}
      {actions}
    </div>
  )

  return (
    <DashboardCard title="Snapshot Trend" actions={header} className="dashboard-reveal">
      <p className="mb-3 text-xs text-muted">Manual snapshots of the full requirement register across all jurisdictions, including informational and excluded entries. Completed review snapshots are available within each review.</p>
      {points.length < 2 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-4 py-5 text-sm text-muted">
          Create snapshots to see trend over time.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface/70 px-3 py-3">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="min-w-[520px] w-full max-w-full"
            role="img"
            aria-label="Snapshots trend chart"
          >
            <rect x="0" y="0" width={width} height={height} fill="rgb(var(--surface))" />
            <path d={totalPath} fill="none" stroke="rgb(var(--line-strong))" strokeWidth="2" />
            <path d={evidencePath} fill="none" stroke="rgb(var(--accent))" strokeWidth="3" />
            {points.map((p, idx) => (
              <circle
                key={p.id}
                cx={xFor(idx)}
                cy={yFor(p.evidenced_requirements)}
                r="3.5"
                fill="rgb(var(--accent))"
              />
            ))}
            <text x={pad} y={height - 6} fontSize="10" fill="rgb(var(--muted))">
              {formatDate(points[0].created_at)}
            </text>
            <text x={width - pad} y={height - 6} fontSize="10" fill="rgb(var(--muted))" textAnchor="end">
              {formatDate(points[points.length - 1].created_at)}
            </text>
          </svg>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-brand" aria-hidden="true" />
          Evidenced
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-line-strong" aria-hidden="true" />
          Total
        </div>
      </div>
    </DashboardCard>
  )
}
