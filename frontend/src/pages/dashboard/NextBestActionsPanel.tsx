import { Link } from 'react-router-dom'
import type { ProgramWorkspaceAction } from '../../types'
import DashboardCard from './DashboardCard'

const priorityClass = (priority: string) => {
  if (priority === 'high') return 'bg-danger-soft text-danger border-danger-line'
  if (priority === 'medium') return 'bg-warning-soft text-warning border-warning-line'
  return 'bg-subtle text-ink border-line'
}

export default function NextBestActionsPanel({
  actions,
  projects = [],
  isLoading = false,
  isError = false,
  onRetry,
}: {
  actions: ProgramWorkspaceAction[]
  projects?: { project_id: string; project_name: string }[]
  isLoading?: boolean
  isError?: boolean
  onRetry?: () => void
}) {
  return (
    <DashboardCard title="Next actions" variant="subtle" className="dashboard-reveal">
      {isError ? <p role="alert" className="text-sm text-danger">Next actions could not be loaded. <button type="button" className="underline" onClick={onRetry}>Try again</button></p> : isLoading ? <p role="status" className="text-sm text-muted">Loading next actions…</p> : actions.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-4 py-6 text-sm text-muted">
          No pending cross-module actions in this scope.
        </div>
      ) : (
        <div className="divide-y divide-line">
          {actions.slice(0, 6).map((action) => (
            <div key={action.id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-ink">{action.title}</div>
                  {projects.find(project => project.project_id === action.project_id) && <div className="mt-1 text-sm font-medium text-ink">{projects.find(project => project.project_id === action.project_id)?.project_name}</div>}
                  <div className="mt-1 break-words text-sm text-muted">{action.summary}</div>
                </div>
                <span
                  className={[
                    'shrink-0 rounded border px-2 py-0.5 text-xs font-semibold',
                    priorityClass(action.priority),
                  ].join(' ')}
                >
                  {action.priority}
                </span>
              </div>
              <div className="mt-3 flex justify-end">
                <Link
                  to={action.cta_path}
                  className="inline-flex items-center rounded-md border border-line-strong px-2.5 py-1.5 text-sm font-medium text-ink hover:border-brand-line hover:text-accent"
                >
                  {action.cta_label}
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </DashboardCard>
  )
}
