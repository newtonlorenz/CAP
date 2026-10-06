import { Link } from 'react-router-dom'
import DashboardCard from './DashboardCard'

type QueueDocument = {
  id: string
  name?: string | null
  filename: string
  document_type: string
  status: string
  created_at: string
  missing_fields: string[]
}

type ExtractionFailureItem = {
  run_id: string
  document_id: string
  document_name: string
  status: string
  error_message?: string | null
  created_at: string
}

type QueuesData = {
  document_status_counts: Array<{ status: string; total: number }>
  documents_pending_approval: QueueDocument[]
  documents_needing_submission: QueueDocument[]
  documents_needing_extraction: QueueDocument[]
  extraction_failures_recent: {
    last_7_days: number
    last_30_days: number
    items: ExtractionFailureItem[]
  }
}

type QueueAction = {
  id: string
  href: string
  title: string
  subtitle: string
}

function buildQueueActions(queues: QueuesData): QueueAction[] {
  const actions: QueueAction[] = []

  queues.documents_pending_approval.slice(0, 3).forEach((doc) => {
    actions.push({
      id: `pending-${doc.id}`,
      href: `/requirements/sets/${doc.id}/import`,
      title: doc.name || doc.filename,
      subtitle: 'Pending approval',
    })
  })

  queues.documents_needing_extraction.slice(0, 3).forEach((doc) => {
    actions.push({
      id: `extract-${doc.id}`,
      href: `/requirements/sets/${doc.id}/import`,
      title: doc.name || doc.filename,
      subtitle: 'Needs extraction',
    })
  })

  queues.documents_needing_submission.slice(0, 3).forEach((doc) => {
    actions.push({
      id: `submit-${doc.id}`,
      href: `/requirements/sets/${doc.id}`,
      title: doc.name || doc.filename,
      subtitle: 'Needs submission',
    })
  })

  queues.extraction_failures_recent.items.slice(0, 3).forEach((run) => {
    actions.push({
      id: `failure-${run.run_id}`,
      href: `/requirements/sets/${run.document_id}/import`,
      title: run.document_name,
      subtitle: 'Recent extraction failure',
    })
  })

  return actions.slice(0, 3)
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

export default function QueuesPanel({
  queues,
}: {
  queues: QueuesData | null
}) {
  if (!queues) return null

  const actions = buildQueueActions(queues)

  return (
    <DashboardCard
      title="Queue Health"
      variant="subtle"
      className="dashboard-reveal"
      actions={
        <Link to="/requirements" className="text-sm font-medium text-accent hover:text-accent hover:underline">
          Open requirement sets
        </Link>
      }
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Pending approval" value={queues.documents_pending_approval.length} />
        <Metric label="Need submission" value={queues.documents_needing_submission.length} />
        <Metric label="Need extraction" value={queues.documents_needing_extraction.length} />
        <Metric label="Failures (7d)" value={queues.extraction_failures_recent.last_7_days} />
      </div>

      <div className="mt-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
          Top actions
        </div>
        {actions.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line-strong bg-surface/60 px-3 py-4 text-sm text-muted">
            No queue actions needed right now.
          </div>
        ) : (
          <div className="space-y-2">
            {actions.map((action) => (
              <Link
                key={action.id}
                to={action.href}
                className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface/80 px-3 py-2 hover:border-brand-line"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-ink">{action.title}</div>
                  <div className="text-xs text-muted">{action.subtitle}</div>
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
