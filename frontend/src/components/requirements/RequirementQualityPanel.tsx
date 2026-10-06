import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import { getApiErrorMessage } from '../../api/errors'
import Button from '../ui/Button'

type Finding = {
  id: string
  kind: string
  requirement_id: string | null
  source_page: number | null
  source_excerpt: string | null
  before: Record<string, unknown>
  after: Record<string, unknown>
  applied: boolean
  answers: Record<string, unknown>
}
type QualityRun = {
  id: string
  status: string
  mode: string
  model: string
  coverage: { checked?: number; total?: number; source_blocks_checked?: number; source_blocks_total?: number }
  usage: { input_tokens?: number }
  warnings: string[]
  findings?: Finding[]
}
type Version = { id: string; version_number: number; status: string }
const running = (status: string) => ['waiting_extraction', 'pending', 'running'].includes(status)

function findingNeedsReview(finding: Finding) {
  if (finding.applied || Object.keys(finding.after).length || finding.kind !== 'accuracy') return true
  const support = finding.answers.supported as { noul?: number } | undefined
  const uncertainChoice = (value: unknown) => {
    const answer = value as { choice?: string; confidence?: number; probabilities?: Record<string, number> } | undefined
    return !answer?.choice || ['no_match', 'uncertain'].includes(answer.choice)
      || (answer.confidence ?? 0) < 0.98 || (answer.probabilities?.[answer.choice] ?? 0) < 0.98
  }
  return (support?.noul ?? 0) < 0.98
    || ['source', 'type', 'parent'].some(key => uncertainChoice(finding.answers[key]))
}

export default function RequirementQualityPanel({ documentId, hasSource, archived, enabled, revision,
  canManage, currentExtractionId, documentStatus }: {
  documentId: string; hasSource: boolean; archived: boolean; enabled: boolean; revision: number
  canManage: boolean; currentExtractionId?: string | null; documentStatus: string
}) {
  const queryClient = useQueryClient()
  const generation = useRef({ documentId, revision, value: 0 })
  if (generation.current.documentId !== documentId || generation.current.revision !== revision) {
    generation.current = { documentId, revision, value: generation.current.value + 1 }
  }
  const [consent, setConsent] = useState(false)
  const [target, setTarget] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { setConsent(false); setTarget(''); setSelectedId(null); setError('') }, [documentId, revision])
  const listKey = ['requirement-quality-runs', documentId]
  const { data: list, isError } = useQuery({
    queryKey: listKey,
    queryFn: async () => (await api.get<{ items: QualityRun[] }>(`/documents/${documentId}/quality-runs`)).data,
    refetchInterval: query => query.state.data?.items.some(run => running(run.status)) ? 2000 : false,
  })
  const { data: versions } = useQuery({
    queryKey: ['quality-versions', documentId],
    queryFn: async () => (await api.get<{ items: Version[] }>(`/requirements/sets/${documentId}/versions`)).data,
    enabled: canManage && enabled && hasSource,
  })
  const latest = list?.items[0]
  const shownId = selectedId || latest?.id
  const { data: detail } = useQuery({
    queryKey: ['requirement-quality-run', documentId, shownId],
    queryFn: async () => (await api.get<QualityRun>(`/documents/${documentId}/quality-runs/${shownId}`)).data,
    enabled: !!shownId,
    refetchInterval: query => query.state.data && running(query.state.data.status) ? 2000 : false,
  })
  const run = detail || latest
  const runId = run?.id
  const runStatus = run?.status
  useEffect(() => {
    if (runStatus && ['completed', 'partial'].includes(runStatus)) {
      queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      queryClient.invalidateQueries({ queryKey: ['extractions', documentId] })
      queryClient.invalidateQueries({ queryKey: ['document-extractions', documentId] })
    }
  }, [runId, runStatus, documentId, queryClient])
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ['requirement-quality-runs', documentId] })
  }, [documentStatus, documentId, queryClient])
  const defaultTarget = documentStatus === 'approved' && versions?.items[0]
    ? `version:${versions.items[0].id}` : currentExtractionId ? `extraction:${currentExtractionId}`
      : versions?.items[0] ? `version:${versions.items[0].id}` : ''
  const selectedTarget = target || defaultTarget
  const create = useMutation({
    mutationFn: async (input: { generation: number; documentId: string; target: string; consent: boolean; revision: number }) => {
      const [kind, id] = input.target.split(':')
      return (await api.post<QualityRun>(`/documents/${input.documentId}/quality-runs`, {
        allow_external_ai: input.consent, jev_settings_revision: input.revision,
        ...(kind === 'version' ? { version_id: id } : { extraction_run_id: id }),
      })).data
    },
    onSuccess: (value, input) => { if (input.generation !== generation.current.value) return; setError(''); setSelectedId(value.id); setConsent(false); queryClient.invalidateQueries({ queryKey: listKey }) },
    onError: (caught, input) => { if (input.generation === generation.current.value) setError(getApiErrorMessage(caught, 'Could not start the source check.')) },
  })
  const cancel = useMutation({
    mutationFn: (input: { generation: number; documentId: string; runId: string | undefined }) => api.post(`/documents/${input.documentId}/quality-runs/${input.runId}/cancel`),
    onSuccess: (_value, input) => {
      if (input.generation !== generation.current.value) return
      setError('')
      queryClient.invalidateQueries({ queryKey: listKey })
      queryClient.invalidateQueries({ queryKey: ['requirement-quality-run', documentId, shownId] })
    },
    onError: (caught, input) => { if (input.generation === generation.current.value) setError(getApiErrorMessage(caught, 'Could not cancel the source check.')) },
  })
  const findings = run?.findings?.filter(findingNeedsReview) || []
  return <section className="mb-4 rounded-lg border border-line bg-surface p-4" aria-label="Jev source checks">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold text-ink">Check requirements against the source</h2>
      {run && <span className="text-sm text-muted">{running(run.status) ? 'Checking source…' : run.status === 'completed'
        ? 'Checked with Jev' : run.status === 'partial' ? 'Check incomplete' : run.status.replace(/_/g, ' ')}</span>}
    </div>
    <p className="mt-2 text-sm text-muted">Check wording, obligation types, hierarchy and possible omissions. Rechecks produce findings for review and preserve your requirements.</p>
    {!hasSource && <p className="mt-2 text-sm text-muted">Source verification is unavailable because this set has no source PDF.</p>}
    {!enabled && <p className="mt-2 text-sm text-muted">Jev is optional. An installation operator can enable it in Settings; ordinary import and review remain available.</p>}
    {canManage && enabled && hasSource && !archived && <div className="mt-3 space-y-3">
      <label className="block text-sm">Requirements to check
        <select className="mt-1 block w-full px-3 py-2" value={selectedTarget} onChange={event => { setTarget(event.target.value); setConsent(false) }}>
          {!selectedTarget && <option value="">No completed requirements available</option>}
          {currentExtractionId && <option value={`extraction:${currentExtractionId}`}>Current extracted draft</option>}
          {versions?.items.map(version => <option key={version.id} value={`version:${version.id}`}>Version {version.version_number} · {version.status.replace(/_/g, ' ')}</option>)}
        </select>
      </label>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />
        <span>Allow source text and requirements to be sent to Jev for this check.</span></label>
      <Button size="sm" loading={create.isPending} disabled={!consent || !selectedTarget || !!(latest && running(latest.status)) || ['extracting', 'pending_extraction'].includes(documentStatus)} onClick={() => create.mutate({ generation: generation.current.value, documentId, target: selectedTarget, consent, revision })}>Check against source</Button>
    </div>}
    {(error || isError) && <p role="alert" className="mt-2 text-sm text-danger">{error || 'Source-check history could not be loaded. Your requirements remain available.'}</p>}
    {run && <div className="mt-3 space-y-2 text-sm">
      {canManage && !archived && running(run.status) && <Button size="sm" loading={cancel.isPending} onClick={() => cancel.mutate({ generation: generation.current.value, documentId, runId: shownId })}>Cancel source check</Button>}
      <p className="text-muted">{run.coverage.checked || 0} of {run.coverage.total || 0} requirements checked; {run.coverage.source_blocks_checked || 0} of {run.coverage.source_blocks_total || 0} source blocks checked.</p>
      {run.warnings.map((warning, index) => <p key={index} className="text-warning">{warning}</p>)}
      {findings.length > 0 && <details><summary className="cursor-pointer font-medium">{findings.length} findings to review</summary>
        <div className="mt-2 space-y-3">{findings.map(finding => <article key={finding.id} className="rounded border border-line p-3">
          <p className="font-medium">{finding.applied ? 'Automatically corrected · needs review' : 'Needs review'} · {finding.kind.replace(/_/g, ' ')}</p>
          {finding.source_page && <a className="text-accent underline" href={`${api.defaults.baseURL}/documents/${documentId}/source#page=${finding.source_page}`} target="_blank" rel="noopener noreferrer">Source page {finding.source_page}</a>}
          {finding.source_excerpt && <p className="mt-2 whitespace-pre-wrap break-words text-muted">{finding.source_excerpt}</p>}
          {Object.entries(finding.after).map(([field, value]) => <div key={field} className="mt-2 break-words">
            <span className="font-medium">{field.replace(/_/g, ' ')}:</span>{' '}
            {Object.prototype.hasOwnProperty.call(finding.before, field) && <span className="text-muted">{String(finding.before[field] ?? 'None')} → </span>}{String(value ?? 'None')}
          </div>)}
        </article>)}</div>
      </details>}
      {list && list.items.length > 1 && <label className="block text-muted">Previous source checks<select className="ml-2 px-2 py-1" value={shownId || ''} onChange={event => setSelectedId(event.target.value)}>{list.items.map((item, index) => <option key={item.id} value={item.id}>Check {list.items.length - index} · {item.status.replace(/_/g, ' ')}</option>)}</select></label>}
    </div>}
  </section>
}
