import type { ApplicationBlocker, ApplicationComponent } from '../../types/applications'
import type { UserMention } from '../../types'
import Button from '../ui/Button'

function issueType(issue: ApplicationBlocker) {
  if (issue.code === 'pending_acceptance') return 'Acceptance'
  if (issue.field_type === 'evidence' || /evidence|expired|revoked|file/.test(issue.code)) return 'Evidence'
  if (issue.field_key) return 'Answers'
  return 'Pack setup and review'
}

export default function ReadinessIssues({ blockers, components, users, onOpenCase, onOpenComponent, onReviewPack }: {
  blockers: ApplicationBlocker[]; components: ApplicationComponent[]; users: UserMention[]
  onOpenCase: (caseId: string, fieldKey?: string) => void
  onOpenComponent: (componentId: string) => void
  onReviewPack: (code: string) => void
}) {
  const groups = new Map<string, { component?: ApplicationComponent; types: Map<string, ApplicationBlocker[]> }>()
  for (const issue of blockers) {
    const component = components.find(item => item.id === issue.component_id)
    const key = component?.id || 'pack'
    if (!groups.has(key)) groups.set(key, { component, types: new Map() })
    const types = groups.get(key)!.types
    const type = issueType(issue)
    types.set(type, [...(types.get(type) || []), issue])
  }
  return <section className="space-y-5" aria-label="Readiness actions">
    {[...groups].map(([key, { component, types }]) => <section key={key} className="border-t border-line pt-4">
      <h4 className="font-semibold">{component?.name || 'Pack requirements'}</h4>
      {component && <p className="mt-1 text-sm text-muted">Owner: {users.find(user => user.id === component.owner_id)?.full_name || (component.owner_id ? 'Assigned owner' : 'Unassigned')}</p>}
      {[...types].map(([type, issues]) => <details key={type} className="mt-3" open={issues.length <= 5}>
        <summary className="cursor-pointer text-sm font-semibold">{type} · {issues.length} {issues.length === 1 ? 'action' : 'actions'}</summary>
        <ul className="mt-2 space-y-3">{issues.map((issue, index) => <li key={`${issue.code}-${issue.field_key}-${index}`} className="flex flex-wrap items-start justify-between gap-2 text-sm">
          <div className="min-w-0 flex-1">{issue.field_label && <p className="font-medium break-words">{issue.section ? `${issue.section} · ` : ''}{issue.field_label}</p>}<p className="text-muted">{issue.message}</p>{issue.code === 'pending_acceptance' && <p className="mt-1 text-xs text-muted">A manager with approval access must accept this answer.</p>}</div>
          {component?.case_id && issue.case_id === component.case_id && issue.field_key
            ? <Button size="sm" onClick={() => onOpenCase(component.case_id!, issue.field_key!)}>Review {issue.field_label || 'field'}</Button>
            : component ? <Button size="sm" onClick={() => onOpenComponent(component.id)}>Review {component.name}</Button>
            : issue.code !== 'restricted_source' && <Button size="sm" onClick={() => onReviewPack(issue.code)}>Review {issue.code === 'open_followup' ? 'authority queries' : issue.code === 'empty_pack' ? 'pack contents' : issue.code === 'invalid_evidence' ? 'evidence library' : 'pack requirements'}</Button>}
        </li>)}</ul>
      </details>)}
    </section>)}
  </section>
}
