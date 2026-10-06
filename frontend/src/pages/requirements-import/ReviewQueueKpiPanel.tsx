import type { ExtractionBatchDistributionItem } from '../../types'

type ReviewQueueKpiPanelProps = {
  unresolvedCount: number
  resolvedInSession: number
  reviewReasonDistribution: ExtractionBatchDistributionItem[]
  sectionDistribution: ExtractionBatchDistributionItem[]
  bulkReadyCount: number
  manualQueueCount: number
}

function DistributionList({
  title,
  items,
}: {
  title: string
  items: ExtractionBatchDistributionItem[]
}) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h4>
      {items.length ? (
        <ul className="mt-2 space-y-1 text-xs text-ink">
          {items.slice(0, 5).map((item) => (
            <li key={`${title}-${item.key}`} className="flex justify-between gap-3">
              <span className="truncate">{item.key}</span>
              <span className="font-medium">{item.total}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-muted">No items</p>
      )}
    </div>
  )
}

export default function ReviewQueueKpiPanel({
  unresolvedCount,
  resolvedInSession,
  reviewReasonDistribution,
  sectionDistribution,
  bulkReadyCount,
  manualQueueCount,
}: ReviewQueueKpiPanelProps) {
  return (
    <div className="mb-4 rounded-lg border border-line bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">QA Queue KPIs</h3>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-md border border-warning-line bg-warning-soft p-3">
          <div className="text-xs uppercase tracking-wide text-warning">Unresolved</div>
          <div className="text-xl font-semibold text-warning">{unresolvedCount}</div>
        </div>
        <div className="rounded-md border border-success-line bg-success-soft p-3">
          <div className="text-xs uppercase tracking-wide text-success">Resolved (session)</div>
          <div className="text-xl font-semibold text-success">{resolvedInSession}</div>
        </div>
        <div className="rounded-md border border-info-line bg-info-soft p-3">
          <div className="text-xs uppercase tracking-wide text-info">Bulk Ready</div>
          <div className="text-xl font-semibold text-info">{bulkReadyCount}</div>
        </div>
        <div className="rounded-md border border-line bg-canvas p-3">
          <div className="text-xs uppercase tracking-wide text-muted">Manual Review</div>
          <div className="text-xl font-semibold text-ink">{manualQueueCount}</div>
        </div>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <DistributionList title="By Review Reason" items={reviewReasonDistribution} />
        <DistributionList title="By Section Prefix" items={sectionDistribution} />
      </div>
    </div>
  )
}
