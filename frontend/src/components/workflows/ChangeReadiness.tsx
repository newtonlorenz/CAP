import type { ReactNode } from 'react'
import type { ChangeEntry } from '../../types'
import Button from '../ui/Button'
import { formatDateTime } from '../../utils/dateFormat'
import '../../pages/workflow-pages.css'

const phaseNames = { approval: 'internal approval', implementation: 'implementation', verification: 'internal verification' }
const externalCodes = /^(ato_|preimplementation_certification|code3_|annual_certification|rng_advance_notice|game_approval|game_prior_approval|instant_error_notice|certified_platform_baseline|platform_baseline_renewal)/
const label = (value: string) => value.replace(/_/g, ' ')

export default function ChangeReadiness({ change, prerequisiteAction, actions, readinessExpected = true }: {
  change: ChangeEntry
  readinessExpected?: boolean
  prerequisiteAction?: (code: string) => { label: string; onClick: () => void } | undefined
  actions?: ReactNode
}) {
  const phase = ['draft', 'rejected'].includes(change.status) ? 'approval' : change.status === 'approved' ? 'implementation' : 'verification'
  const readiness = change.readiness?.[phase]
  const closed = ['verified', 'rolled_back'].includes(change.status)
  const reasons = readiness?.reasons.filter(item => !closed || !item.code.endsWith('_status')) || []
  return <div id="change-readiness" className="change-readiness-layout">
    <section className="change-readiness-main" aria-label="Current change readiness">
      <div className={`change-readiness-banner ${closed || readiness?.ready ? 'is-ready' : 'needs-attention'}`} role="status">
        <span className="readiness-symbol" aria-hidden="true">{closed || readiness?.ready ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 12 4 4 8-8" /></svg> : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 6v8m0 3v1" /></svg>}</span>
        <div><h4>{closed ? change.status === 'verified' ? 'Internally verified' : 'Rollback recorded' : !readiness ? readinessExpected ? 'Readiness unavailable' : 'Review the change proposal' : `${readiness.ready ? 'Ready' : 'Not ready'} for ${phaseNames[phase]}`}</h4>
          <p>{reasons.length ? `${reasons.length} required ${reasons.length === 1 ? 'check' : 'checks'} outstanding` : readiness ? closed ? 'Review the recorded decisions and external requirements below.' : 'The current phase has no outstanding checks.' : readinessExpected ? 'Reload this change to check the current prerequisites.' : 'Review the proposal details and evidence before recording a decision. Automated readiness checks are not provided for this jurisdiction.'}</p>
        </div>
        {actions && <div className="readiness-primary-action">{actions}</div>}
      </div>
      {reasons.length > 0 && <section className="readiness-checks"><h4>Required checks needing attention</h4><ul>{reasons.map((item, index) => {
        const action = prerequisiteAction?.(item.code)
        return <li key={`${item.code}-${index}`}><span className="readiness-dot" aria-hidden="true" /><div className="readiness-check-copy"><p>{item.message}</p><span className="readiness-check-meta">Required{item.code.startsWith('blocking_assessment') ? ' · Review the assigned owner in the assessment' : ''}</span></div>{action && <Button size="sm" onClick={action.onClick}>{action.label}</Button>}</li>
      })}</ul><p className="readiness-footnote">Recording a decision alone does not pass a check. Required assessments need acceptable confirmed outcomes and current evidence.</p></section>}
      {!closed && readiness?.ready && <p className="readiness-footnote">Readiness applies to {phaseNames[phase]} only. It does not record an authority decision or external certification.</p>}
    </section>
    <aside className="change-approval-context" aria-label="Approval context">
      <h4>Approval context</h4>
      <dl><div><dt>Internal approval</dt><dd>{change.approved_at ? `Recorded ${formatDateTime(change.approved_at)}` : 'Not recorded'}</dd></div>{change.approved_by && <div><dt>Approved by</dt><dd>{change.approved_by}</dd></div>}<div><dt>Implementation</dt><dd>{change.implemented_at ? `Recorded ${formatDateTime(change.implemented_at)}` : 'Not recorded'}</dd></div></dl>
      <div className="external-requirements"><h4>External requirements</h4>
        {(readinessExpected || change.readiness) && (['approval', 'implementation', 'verification'] as const).map(key => {
          const check = change.readiness?.[key]
          const outstanding = check?.reasons.filter(item => externalCodes.test(item.code))
          return <details key={key}><summary><span>For {phaseNames[key]}</span><span>{!check ? 'Unavailable' : outstanding?.length ? `${outstanding.length} outstanding` : 'No outstanding checks reported'}</span></summary>{!!outstanding?.length && <ul>{outstanding.map(item => <li key={item.code}>{item.message}</li>)}</ul>}</details>
        })}
        <dl><div><dt>Certification</dt><dd>{label(change.readiness?.certification_status || 'Not recorded')}</dd></div>{change.readiness?.certification_due_at && <div><dt>Due</dt><dd>{formatDateTime(change.readiness.certification_due_at)}</dd></div>}</dl>
        <a href="#change-external-evidence" onClick={() => { const element = document.getElementById('change-external-evidence'); if (element instanceof HTMLDetailsElement) element.open = true }}>View applicability &amp; evidence</a>
      </div>
    </aside>
  </div>
}
