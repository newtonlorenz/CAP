import './workflow-pages.css'
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { applicationsApi } from '../api/applications'
import { getApiErrorMessage } from '../api/errors'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import type { MarketProfile, MarketProfileItem } from '../types/applications'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { Field, inputClass } from '../components/applications/Fields'

const blankItem = (): MarketProfileItem => ({ key: `item-${crypto.randomUUID()}`, name: '', kind: 'form', required: true, condition: null, repeat_for: null, source_url: null, guidance: null })
const questionLabels: Record<string, string> = { foreign_applicant: 'Applicant registered abroad', foreign_people: 'People without Finnish ID', representative_used: 'Representative used', people: 'People requiring declarations' }
const isWebUrl = (value: string) => { try { return ['http:', 'https:'].includes(new URL(value).protocol) } catch { return false } }

export default function MarketSetup() {
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, registerChangeGuard } = useJurisdiction()
  const canManage = user?.role === 'admin' || user?.role === 'manager'
  const code = jurisdictionById[jurisdictionId || '']?.code?.toUpperCase() || ''
  const isSweden = ['SE', 'SWE'].includes(code)
  const isFinland = ['FI', 'FIN'].includes(code)
  const supportedQuestions = Object.keys(questionLabels).filter((key) => key !== 'foreign_people' || isFinland)
  const client = useQueryClient()
  const profile = useQuery({ queryKey: ['applications', 'market-profile', jurisdictionId], queryFn: () => applicationsApi.marketProfile(jurisdictionId!), enabled: Boolean(jurisdictionId) && canManage, retry: false })
  const [draft, setDraft] = useState<MarketProfile | null>(null)
  const [baseline, setBaseline] = useState<MarketProfile | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [reloadRequested, setReloadRequested] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const editor = useRef<HTMLFieldSetElement>(null)
  const currentJurisdiction = useRef(jurisdictionId)
  currentJurisdiction.current = jurisdictionId
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline)
  const navigationGuarded = useDraftNavigationGuard(dirty || busy)
  useEffect(() => {
    if (navigationGuarded || !(dirty || busy)) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [navigationGuarded, dirty, busy])
  useEffect(() => registerChangeGuard?.(() => !(dirty || busy) || window.confirm('Discard unsaved market setup changes and switch markets? A save already sent may still complete.')), [registerChangeGuard, dirty, busy])
  useEffect(() => { setDraft(null); setBaseline(null); setMessage(''); setConflict(false); setFailed(false); setErrors({}) }, [jurisdictionId])
  useEffect(() => {
    if (profile.data && !dirty && !busy && !conflict) { setDraft(profile.data); setBaseline(profile.data) }
  }, [profile.data, dirty, busy, conflict])
  const set = (patch: Partial<MarketProfile>) => { setDraft((old) => old ? { ...old, ...patch } : old); setMessage('') }
  const setItem = (index: number, patch: Partial<MarketProfileItem>) => set({ items: draft!.items.map((item, i) => i === index ? { ...item, ...patch } : item) })
  const errorProps = (key: string) => ({ 'aria-invalid': Boolean(errors[key]), 'aria-describedby': errors[key] ? `market-error-${key}` : undefined, 'data-field': key })
  const error = (key: string) => errors[key] && <p id={`market-error-${key}`} className="mt-1 text-sm text-danger">{errors[key]}</p>
  const save = async () => {
    if (!draft || !jurisdictionId || busy || conflict) return
    const nextErrors: Record<string, string> = {}
    if (!draft.label.trim()) nextErrors.label = 'Enter a profile label.'
    if (!draft.authority.trim()) nextErrors.authority = 'Enter the authority name.'
    if (draft.source_urls.some((url) => url.trim() && !isWebUrl(url.trim()))) nextErrors.sources = 'Use a complete http or https URL on each line.'
    const keys = new Set<string>()
    draft.items.forEach((item, index) => {
      if (!item.name.trim()) nextErrors[`name-${index}`] = 'Enter an item name.'
      if (!item.key.trim() || keys.has(item.key.trim())) nextErrors[`key-${index}`] = 'Enter a unique stable key.'
      keys.add(item.key.trim())
      if (item.source_url && !isWebUrl(item.source_url)) nextErrors[`url-${index}`] = 'Use a complete http or https URL.'
    })
    draft.setup_questions.forEach((question, index) => { if (!String(question.label || '').trim()) nextErrors[`question-${index}`] = 'Enter the question text.' })
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      setFailed(true); setMessage('Correct the highlighted fields before saving.')
      requestAnimationFrame(() => {
        const field = editor.current?.querySelector<HTMLElement>(`[data-field="${Object.keys(nextErrors)[0]}"]`)
        const details = field?.closest('details'); if (details) details.open = true
        field?.focus()
      })
      return
    }
    setBusy(true); setMessage(''); setFailed(false)
    try {
      const updated = await applicationsApi.updateMarketProfile({ jurisdiction_id: jurisdictionId, expected_revision: draft.revision, status: isSweden ? 'draft' : draft.status, label: draft.label.trim(), authority: draft.authority.trim(), setup_questions: draft.setup_questions, items: draft.items.map((item) => ({ ...item, key: item.key.trim(), name: item.name.trim() })), guidance: draft.guidance.map((line) => line.trim()).filter(Boolean), source_urls: draft.source_urls.map((url) => url.trim()).filter(Boolean), checked_at: draft.checked_at })
      client.setQueryData(['applications', 'market-profile', jurisdictionId], updated)
      if (currentJurisdiction.current !== jurisdictionId) return
      setDraft(updated); setBaseline(updated); setMessage('Market profile saved.')
    } catch (caught) { if (currentJurisdiction.current !== jurisdictionId) return; setConflict(axios.isAxiosError(caught) && caught.response?.status === 409); setFailed(true); setMessage(getApiErrorMessage(caught, 'Market profile could not be saved. Your changes remain here. Try saving again.')) }
    finally { setBusy(false) }
  }
  const reload = async () => {
    setReloadRequested(false); setBusy(true)
    const latest = await profile.refetch()
    if (currentJurisdiction.current !== jurisdictionId) { setBusy(false); return }
    if (latest.data && !latest.isError) { setDraft(latest.data); setBaseline(latest.data); setConflict(false); setFailed(false); setErrors({}); setMessage('Latest profile loaded. Local changes discarded.') }
    else { setFailed(true); setMessage('Latest profile could not be loaded. Your changes remain here. Try again.') }
    setBusy(false)
  }
  if (!canManage) return <Card className="p-5"><p role="alert">Only organization managers can edit market setup.</p><Link to="/licence-applications" className="text-accent underline">Return to licence packs</Link></Card>
  return <div className="workflow-page market-setup-page space-y-5 pb-10">
    <div className="workflow-heading"><Link to="/jurisdictions" className="text-sm text-accent underline">Jurisdictions</Link><h1 className="mt-2 text-3xl font-semibold">Market setup</h1><p className="mt-2 max-w-prose text-sm text-muted">Maintain the proposed checklist and authority sources for {jurisdictionById[jurisdictionId || '']?.name || 'the selected market'}. This is not a legal form definition.</p></div>
    {!jurisdictionId && <p>Select a market to continue.</p>}
    {profile.isLoading && <p role="status">Loading market profile…</p>}
    {profile.isError && <p role="alert">Market profile could not be loaded. <Button onClick={() => void profile.refetch()}>Retry</Button></p>}
    {draft && <Card className="p-5 sm:p-7">
      <fieldset ref={editor} disabled={busy} className="min-w-0 space-y-5">
        <section aria-label="Authority and source details" className="market-source-section"><h2 className="mb-4 text-lg font-semibold">Authority and source details</h2><div className="grid gap-4 sm:grid-cols-2">
          <Field label="Profile label"><input {...errorProps('label')} className={inputClass} value={draft.label} onChange={(e) => set({ label: e.target.value })} />{error('label')}</Field>
          <Field label="Authority"><input {...errorProps('authority')} className={inputClass} value={draft.authority} onChange={(e) => set({ authority: e.target.value })} />{error('authority')}</Field>
          <Field label="Status"><select className={inputClass} value={isSweden ? 'draft' : draft.status} disabled={isSweden} onChange={(e) => set({ status: e.target.value as MarketProfile['status'] })}><option value="draft">Draft</option><option value="published">Published</option></select>{isSweden && <span className="text-xs text-muted">Sweden remains a blank custom setup until its checklist is verified.</span>}</Field>
          <Field label="Source checked on"><input type="date" className={inputClass} value={draft.checked_at || ''} onChange={(e) => set({ checked_at: e.target.value || null })} /></Field>
        </div>
        <Field label="Authority source URLs, one per line"><textarea {...errorProps('sources')} className={inputClass} rows={3} value={draft.source_urls.join('\n')} onChange={(e) => set({ source_urls: e.target.value.split('\n') })} />{error('sources')}</Field>
        <Field label="Guidance, one paragraph per line"><textarea className={inputClass} rows={3} value={draft.guidance.join('\n')} onChange={(e) => set({ guidance: e.target.value.split('\n') })} /></Field>
        </section><section className="market-questions-section space-y-3"><h2 className="text-lg font-semibold">Setup questions</h2><p className="text-sm text-muted">Choose the questions shown when a pack starts. Answers shape the proposed checklist.</p>
          {draft.setup_questions.map((question, index) => <div key={`${String(question.key)}-${index}`} className="flex flex-wrap items-end gap-3"><Field label="Question"><input {...errorProps(`question-${index}`)} className={inputClass} value={String(question.label || '')} onChange={(event) => set({ setup_questions: draft.setup_questions.map((current, i) => i === index ? { ...current, label: event.target.value } : current) })} />{error(`question-${index}`)}</Field><Button size="sm" onClick={() => set({ setup_questions: draft.setup_questions.filter((_, i) => i !== index) })}>Remove question</Button></div>)}
          <Field label="Add supported question"><select className={inputClass} value="" onChange={(event) => { const key = event.target.value; if (key) set({ setup_questions: [...draft.setup_questions, { key, label: questionLabels[key], type: key === 'people' ? 'people' : 'boolean' }] }) }}><option value="">Choose question</option>{supportedQuestions.filter((key) => !draft.setup_questions.some((question) => question.key === key)).map((key) => <option key={key} value={key}>{questionLabels[key]}</option>)}</select></Field>
        </section>
        <section className="space-y-4"><h2 className="text-lg font-semibold">Proposed items</h2>
          {draft.items.map((item, index) => <div key={index} className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
            <Field label="Name"><input {...errorProps(`name-${index}`)} className={inputClass} value={item.name} onChange={(e) => setItem(index, { name: e.target.value })} />{error(`name-${index}`)}</Field>
            <Field label="Type"><select className={inputClass} value={item.kind} onChange={(e) => setItem(index, { kind: e.target.value as MarketProfileItem['kind'] })}><option value="form">Form</option><option value="annex">Annex</option><option value="document">Document</option></select></Field>
            <Field label="When to propose"><select className={inputClass} value={item.condition || ''} onChange={(e) => setItem(index, { condition: (e.target.value || null) as MarketProfileItem['condition'] })}><option value="">Always</option><option value="foreign_applicant">Foreign applicant</option>{(isFinland || item.condition === 'foreign_people') && <option value="foreign_people">{isFinland ? 'People without Finnish ID' : 'Existing custom people condition'}</option>}<option value="representative_used">Representative used</option></select></Field>
            <Field label="Repeat"><select className={inputClass} value={item.repeat_for || ''} onChange={(e) => setItem(index, { repeat_for: (e.target.value || null) as MarketProfileItem['repeat_for'] })}><option value="">Once</option><option value="people">For each person</option></select></Field>
            <Field label="Item source URL"><input {...errorProps(`url-${index}`)} className={inputClass} value={item.source_url || ''} onChange={(e) => setItem(index, { source_url: e.target.value || null })} />{error(`url-${index}`)}</Field>
            <label className="self-center text-sm"><input type="checkbox" checked={item.required} onChange={(e) => setItem(index, { required: e.target.checked })} /> Required by default</label>
            <details className="sm:col-span-2"><summary className="cursor-pointer text-sm text-muted">Advanced</summary><p className="my-2 text-sm text-muted">The stable key links this item to existing checklists. Keep it unchanged when renaming an item.</p><Field label="Stable key"><input {...errorProps(`key-${index}`)} className={inputClass} value={item.key} onChange={(e) => setItem(index, { key: e.target.value })} />{error(`key-${index}`)}</Field></details>
            <div><Button size="sm" onClick={() => set({ items: draft.items.filter((_, i) => i !== index) })}>Remove item</Button></div>
          </div>)}
          <Button onClick={() => set({ items: [...draft.items, blankItem()] })}>Add proposed item</Button>
        </section>
      </fieldset>
      <div className="sticky bottom-0 mt-6 space-y-3 border-t border-line bg-surface py-4">
        {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
        {conflict && <p className="text-sm text-muted">Another editor saved a newer profile. Your draft is preserved. Loading the latest profile discards your local changes.</p>}
        <div className="flex flex-wrap items-center gap-3"><Button variant="primary" loading={busy} disabled={!dirty || busy || conflict} onClick={() => void save()}>Save market profile</Button><Button disabled={!dirty || busy} onClick={() => { if (conflict) setReloadRequested(true); else { setDraft(baseline); setErrors({}); setMessage('Changes discarded.'); setFailed(false) } }}>Discard changes</Button>{conflict && <Button disabled={busy} onClick={() => setReloadRequested(true)}>Load latest profile</Button>}<span role="status" className="text-sm text-muted">{busy ? 'Saving or loading…' : dirty ? 'Unsaved changes' : 'All changes saved'}</span></div>
      </div>
    </Card>}
    <ConfirmDialog open={reloadRequested} title="Discard changes and load latest profile?" description="Your unsaved changes will be lost. The latest saved profile will replace this draft." confirmLabel="Discard and load latest" onConfirm={() => void reload()} onClose={() => setReloadRequested(false)} />
  </div>
}
