export const STATUS_LABELS: Record<string, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  blocked: 'Blocked',
  evidenced: 'Evidenced',
  not_applicable: 'Not applicable',
}

export const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  updated: 'Updated',
  escalated: 'Escalated',
}

export function formatStatus(status: string): string {
  return STATUS_LABELS[status] || status.replace(/_/g, ' ')
}

export function formatReviewStatus(status: string): string {
  return REVIEW_STATUS_LABELS[status] || status.replace(/_/g, ' ')
}

export function statusClass(status: string): string {
  const classes: Record<string, string> = {
    not_started: 'bg-gray-100 text-gray-800',
    in_progress: 'bg-blue-100 text-blue-800',
    blocked: 'bg-red-100 text-red-800',
    evidenced: 'bg-green-100 text-green-800',
    not_applicable: 'bg-purple-100 text-purple-800',
    pending: 'bg-gray-100 text-gray-800',
    confirmed: 'bg-green-100 text-green-800',
    updated: 'bg-blue-100 text-blue-800',
    escalated: 'bg-amber-100 text-amber-900',
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

