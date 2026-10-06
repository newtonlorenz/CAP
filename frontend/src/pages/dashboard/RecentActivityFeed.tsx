import { Link } from 'react-router-dom'
import { formatDateTime } from '../../utils/dateFormat'
import DashboardCard from './DashboardCard'

const activityDestinations: Record<string, { label: string; path: (id: string) => string }> = {
  application: { label: 'Licence application', path: (id) => `/licence-applications?application=${id}` },
  certification_project: { label: 'Certification project', path: (id) => `/certification-projects?project=${id}` },
  preparation_case: { label: 'Form', path: (id) => `/preparation?case=${id}` },
  requirement: { label: 'Requirement', path: (id) => `/requirements/${id}` },
  document: { label: 'Requirement set', path: (id) => `/requirements/sets/${id}` },
  requirement_set: { label: 'Requirement set', path: (id) => `/requirements/sets/${id}` },
  review_cycle: { label: 'Assessment', path: (id) => `/review-cycles/${id}` },
  review_package: { label: 'Assessment', path: (id) => `/review-cycles/${id}` },
}

export default function RecentActivityFeed({
  items,
  compact,
}: {
  items: Array<{
    id: string
    user_name: string
    action: string
    entity_type: string
    entity_id: string
    timestamp: string
    summary?: string | null
    title?: string | null
    destination?: string | null
  }>
  compact?: boolean
}) {
  const rows = items.slice(0, compact ? 6 : 10)
  return (
    <DashboardCard title="Recent Activity" variant="subtle" className="dashboard-reveal">
      <div className="space-y-2">
        {rows.map((activity) => {
          const destination = Object.prototype.hasOwnProperty.call(activityDestinations, activity.entity_type) ? activityDestinations[activity.entity_type] : undefined
          const deleted = /(?:^|_)(?:delete|deleted|remove|removed)(?:_|$)/i.test(activity.action)
          const to = !deleted ? activity.destination || (destination && activity.entity_id ? destination.path(encodeURIComponent(activity.entity_id)) : null) : null
          const label = destination?.label || activity.entity_type.replace(/_/g, ' ')
          return (
            <div
              key={activity.id}
              className="flex flex-col gap-1 rounded-lg border border-line bg-surface/70 p-2.5 text-sm sm:flex-row sm:items-center sm:gap-3"
            >
              <span className="text-xs text-faint sm:w-40 sm:shrink-0">
                {formatDateTime(activity.timestamp)}
              </span>
              <span className="break-words text-ink">{activity.user_name}</span>
              <span className="w-fit rounded bg-subtle px-2 py-0.5 text-ink">
                {activity.action.replace(/_/g, ' ')}
              </span>
              {to ? <Link to={to} className="break-words font-semibold text-accent underline" aria-label={`Open ${activity.title || label.toLowerCase()}`}>{activity.title || label}</Link> : <span className="break-words text-muted">{activity.title || label}</span>}
              {activity.summary ? (
                <span className="break-words text-muted">{activity.summary}</span>
              ) : null}
            </div>
          )
        })}
        {rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line-strong bg-surface/60 px-3 py-4 text-sm text-muted">
            No recent activity.
          </div>
        ) : null}
      </div>
    </DashboardCard>
  )
}
