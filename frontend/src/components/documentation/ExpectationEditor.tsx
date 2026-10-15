import { useState } from 'react'
import axios from 'axios'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import api from '../../api/client'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, ExpectationDraft, CoverageStatus } from '../../types/documentation'
import type { PaginatedResponse, UserMention } from '../../types'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import { Field, inputClass, OwnerField } from '../applications/Fields'
import DraftSaveStatus, { type DraftSaveState } from '../ui/DraftSaveStatus'
import Button from '../ui/Button'
import { formatDate } from '../../utils/dateFormat'
import { expectationReasons } from './model'
import EvidenceMapping from './EvidenceMapping'
import RequirementMapping from './RequirementMapping'
import NativeReferences from './NativeReferences'
import ProcessDocumentsModal from './ProcessDocumentsModal'
import { processTargetHref } from './processNavigation'
import type { ProcessTarget } from '../../types/documentation'
import DocumentationSuggestions from './DocumentationSuggestions'

type AdvancedDraft = Pick<ExpectationDraft, 'category' | 'interpretation' | 'basis' | 'applicability' | 'not_applicable_reason' | 'responsible_party' | 'owner_id'>
const toDraft = (item: DocumentationExpectation): AdvancedDraft => ({ category: item.category || '', interpretation: item.interpretation || '', basis: item.basis || '', applicability: item.applicability, not_applicable_reason: item.not_applicable_reason || '', responsible_party: item.responsible_party || '', owner_id: item.owner_id })

export default function ExpectationEditor({ expectation, jurisdictionId, projectId, canEdit, canReview, onSaved }: {
  expectation: DocumentationExpectation; jurisdictionId: string; projectId?: string; canEdit: boolean; canReview: boolean; onSaved: (item: DocumentationExpectation) => void
}) {
  const cache = useQueryClient()
  const location = useLocation()
  const [processTarget, setProcessTarget] = useState<ProcessTarget | null>(null)
  const canonical = Boolean(expectation?.process_targets?.length)
  const [current, setCurrent] = useState(expectation)
  const [baseline, setBaseline] = useState<AdvancedDraft>(toDraft(expectation))
  const [draft, setDraft] = useState(baseline)
  const [state, setState] = useState<DraftSaveState>('saved')
  const [error, setError] = useState('')
  const [reviewStatus, setReviewStatus] = useState<CoverageStatus>(expectation?.coverage_status || 'unreviewed')
  const [reviewReason, setReviewReason] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [requirementsOpen, setRequirementsOpen] = useState(false)
  const [comparison, setComparison] = useState<AdvancedDraft | null>(null)
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)
  useDraftNavigationGuard(dirty || state === 'saving' || reviewBusy || Boolean(reviewReason))
  const users = useQuery({ queryKey: ['documentation', 'users'], queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data, enabled: canEdit })
  const change = (patch: Partial<AdvancedDraft>) => { setDraft(value => ({ ...value, ...patch })); if (state !== 'conflict') setState('dirty') }
  const apply = (item: DocumentationExpectation) => { setCurrent(item); setBaseline(toDraft(item)); setDraft(toDraft(item)); onSaved(item) }
  const save = async () => {
    if (state === 'saving' || state === 'conflict') return
    setState('saving'); setError('')
    try {
      const saved = await documentationApi.updateExpectation(current.id, current.revision, draft)
      setState('saved'); apply(saved)
    } catch (caught) { setState(axios.isAxiosError(caught) && caught.response?.status === 409 ? 'conflict' : 'error'); setError(getApiErrorMessage(caught, 'The expectation could not be saved. Your draft is preserved.')) }
  }
  const reconcile = async () => {
    if (!current) return
    try { const fresh = (await api.get<DocumentationExpectation>(`/documentation/expectations/${current.id}`)).data; setCurrent(fresh); setComparison(toDraft(fresh)); setError('Compare the latest record with your preserved draft. Choose which values to keep.'); void cache.invalidateQueries({ queryKey: ['documentation'] }) } catch (caught) { setError(getApiErrorMessage(caught, 'The latest revision could not be loaded. Your draft is preserved.')) }
  }
  const reasons = current ? expectationReasons(current) : []
  return <article className="min-w-0 space-y-5" aria-label="Expectation details">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-lg font-semibold">Advanced details</h3><DraftSaveStatus state={dirty && state === 'saved' ? 'dirty' : state} onRetry={() => void save()} /></div>
    {current && <div className="border-y border-line py-3 text-sm"><p>Coverage review: <strong>{current.effective_coverage_status || current.coverage_status}</strong></p>{current.coverage_warning && <p className="mt-1 text-warning">{current.coverage_warning}</p>}{reasons.length > 0 && <p className="mt-1 text-muted">Evidence conditions: {reasons.join(', ')}</p>}<p className="mt-1 text-muted">These conditions do not change requirement assessments.</p></div>}
    <form className="space-y-4" onSubmit={event => { event.preventDefault(); void save() }}>
      <fieldset disabled={!canEdit || state === 'saving'} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2"><Field label="Documentation category"><input maxLength={100} className={inputClass} value={draft.category || ''} onChange={event => change({ category: event.target.value })} /></Field><OwnerField users={users.data?.items || []} value={draft.owner_id || ''} onChange={value => change({ owner_id: value || null })} /></div>
        {users.isError && <p role="alert" className="text-sm text-danger">Owners could not be loaded. <Button size="sm" onClick={() => void users.refetch()}>Retry owners</Button></p>}
        <Field label="Responsible party"><input className={inputClass} value={draft.responsible_party || ''} placeholder="Team or role responsible for this documentation" onChange={event => change({ responsible_party: event.target.value })} /></Field>
        <Field label="Interpretation"><textarea rows={3} className={inputClass} value={draft.interpretation || ''} onChange={event => change({ interpretation: event.target.value })} /></Field>
        <Field label="Basis for the expectation"><textarea rows={2} className={inputClass} value={draft.basis || ''} onChange={event => change({ basis: event.target.value })} /></Field>
        <Field label="Applicability"><select className={inputClass} value={draft.applicability} onChange={event => change({ applicability: event.target.value as ExpectationDraft['applicability'] })}><option value="unknown">Not decided</option><option value="applicable">Applicable</option><option value="not_applicable">Not applicable</option></select></Field>
        {draft.applicability === 'not_applicable' && <Field label="Reason not applicable"><textarea required rows={2} className={inputClass} value={draft.not_applicable_reason || ''} onChange={event => change({ not_applicable_reason: event.target.value })} /></Field>}
        {canEdit && <Button type="submit" variant="primary" loading={state === 'saving'} disabled={!dirty || state === 'conflict'}>Save expectation</Button>}
      </fieldset>
    </form>
    {error && <p role={state === 'error' || state === 'conflict' ? 'alert' : 'status'} className="text-sm text-danger">{error}</p>}
    {state === 'conflict' && <Button onClick={() => void reconcile()}>Load current revision and keep draft</Button>}
    {comparison && <section className="space-y-3 border border-warning-line rounded-md p-3"><h4 className="font-semibold">Resolve concurrent changes</h4><p className="text-sm text-muted">Your draft is preserved. Review each difference before saving over the latest values.</p>{(Object.keys(draft) as (keyof AdvancedDraft)[]).filter(key => draft[key] !== comparison[key]).map(key => <div key={key} className="space-y-1 border-t border-line pt-2 text-sm"><strong>{key.replace(/_/g, ' ')}</strong><p className="whitespace-pre-wrap break-words">Current: {comparison[key] || 'Empty'}</p><p className="whitespace-pre-wrap break-words">Your draft: {draft[key] || 'Empty'}</p></div>)}<div className="flex flex-wrap gap-2"><Button onClick={() => { setBaseline(comparison); setComparison(null); setState('dirty'); setError('Your reviewed draft is ready to save against the latest revision.') }}>Keep reviewed draft</Button><Button onClick={() => { setBaseline(comparison); setDraft(comparison); setComparison(null); setState('saved'); setError('Current record restored.') }}>Use current values</Button></div></section>}
    {current && <>
      {Boolean(current.source_rows?.length) && <details className="border-t border-line pt-4"><summary className="cursor-pointer font-semibold">Original source rows</summary><div className="mt-3 space-y-4">{current.source_rows?.map((source, index) => <section key={index} className="space-y-2 border-b border-line pb-3 text-sm"><h4 className="font-semibold">{source.sheet} · Row {source.row_number}</h4>{source.original_headers?.map((header, column) => <div key={column}><strong>{header || `Column ${column + 1}`}</strong><p className="whitespace-pre-wrap break-words">{String(source.original_values?.[column] ?? '')}</p></div>)}{Object.entries(source.metadata).map(([key, value]) => <p className="whitespace-pre-wrap break-words" key={key}><strong>{key}:</strong> {String(value ?? '')}</p>)}</section>)}</div></details>}

      <section className="space-y-3 border-t border-line pt-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Linked obligations</h4>{canEdit && <Button size="sm" disabled={dirty || state === 'saving'} onClick={() => setRequirementsOpen(true)}>Link obligations</Button>}</div>{!current.requirements.length && <p className="text-sm text-muted">No versioned requirements are linked.</p>}{current.requirements.map(link => <div key={`${link.requirement_id}-${link.requirement_set_version_id}`} className="text-sm"><Link className="text-accent underline" to={`/requirements/${link.requirement_id}`}>{link.reference_id || link.title || 'Open linked requirement'}</Link><p className="text-muted">{link.set_name || 'Requirement set'} · Version {link.version_number ?? 'recorded'}{link.is_current === false ? ' · Earlier approved version' : ''}</p></div>)}</section>
      <section className="space-y-3 border-t border-line pt-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{canonical ? 'Standalone evidence coverage' : 'Evidence coverage'}</h4>{canEdit && !canonical && <Button size="sm" disabled={dirty || state === 'saving'} onClick={() => setEvidenceOpen(true)}>Link evidence</Button>}</div>{current.standalone_coverage_warning && <p className="text-sm text-warning">{current.standalone_coverage_warning}</p>}{!current.coverage.length && <p className="text-sm text-muted">No evidence is linked. Reuse available evidence or add it to the evidence library.</p>}{current.coverage.map(link => <div key={link.evidence_id} className="space-y-1 border-b border-line pb-3 text-sm"><strong className="break-words">{link.evidence?.title || link.title || 'Linked evidence'}</strong><p>Locator: {link.locator || 'Not recorded'}</p><p>Scope: {link.scope || 'Not recorded'} · Period: {link.period || 'Not recorded'}</p><p className="text-muted">{link.rationale || 'Coverage explanation not recorded'}</p></div>)}</section>
      {canonical && <section className="space-y-3 border-t border-line pt-4"><h4 className="font-semibold">Process evidence collections</h4><p className="text-sm text-muted">Manage documents in their original collection. Standalone links above remain separate historical records.</p>{current.process_targets?.map((target, index) => { const href = processTargetHref(target, `${location.pathname}${location.search}`); return target.available ? <div key={index} className="flex flex-wrap items-center gap-2 text-sm"><span>{target.reference_id} · {target.case_name || target.title}</span>{href && <Link className="text-accent underline" to={href}>Open evidence collection</Link>}<Button size="sm" onClick={() => setProcessTarget(target)}>View process documents</Button></div> : <p key={index} className="text-sm text-muted">A process target is unavailable.</p> })}{processTarget && <ProcessDocumentsModal rowId={current.id} target={processTarget} returnTo={`${location.pathname}${location.search}`} onClose={() => setProcessTarget(null)} />}</section>}
      <NativeReferences expectation={current} canEdit={canEdit && !dirty} onSaved={apply} />
      <DocumentationSuggestions expectation={current} canEdit={canEdit && !dirty} onSaved={apply} />
      <section className="space-y-3 border-t border-line pt-4"><h4 className="font-semibold">Manual coverage review</h4>{canonical && <p className="text-sm text-muted">Review whether the linked process documents cover this register row. Process assessment and approval decisions stay in their existing workflow.</p>}<p className="text-sm text-muted">Review the linked evidence before you record a decision. AI suggestions cannot set sufficient coverage.</p>{current.reviewed_at && <p className="text-sm">Last reviewed {formatDate(current.reviewed_at)}{current.review_rationale ? `: ${current.review_rationale}` : ''}</p>}<fieldset disabled={!canReview || dirty || reviewBusy || (state === 'saving' || state === 'conflict')} className="space-y-3"><Field label="Coverage decision"><select className={inputClass} value={reviewStatus} onChange={event => setReviewStatus(event.target.value as CoverageStatus)}><option value="unreviewed">Unreviewed</option><option value="partial">Partial</option><option value="sufficient">Sufficient</option></select></Field><Field label="Review rationale"><textarea rows={3} className={inputClass} value={reviewReason} onChange={event => setReviewReason(event.target.value)} /></Field>{canReview && <Button disabled={!reviewReason.trim()} loading={reviewBusy} onClick={async () => { setReviewBusy(true); setError(''); try { const saved = await documentationApi.review(current.id, current.revision, reviewStatus, reviewReason.trim()); setReviewReason(''); apply(saved) } catch (caught) { if (axios.isAxiosError(caught) && caught.response?.status === 409) setState('conflict'); setError(getApiErrorMessage(caught, 'Coverage review failed. Your rationale is preserved.')) } finally { setReviewBusy(false) } }}>Record coverage review</Button>}</fieldset>{dirty && <p className="text-sm text-muted">Save the expectation before changing its links or recording a review.</p>}</section>
      {evidenceOpen && <EvidenceMapping expectation={current} onClose={() => setEvidenceOpen(false)} onSaved={item => { apply(item); setEvidenceOpen(false) }} />}
      {requirementsOpen && <RequirementMapping expectation={current} jurisdictionId={jurisdictionId} projectId={projectId} onClose={() => setRequirementsOpen(false)} onSaved={item => { apply(item); setRequirementsOpen(false) }} />}
    </>}
  </article>
}
