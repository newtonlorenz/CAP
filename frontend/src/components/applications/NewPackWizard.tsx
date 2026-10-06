import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Jurisdiction, UserMention } from '../../types'
import type { ApplicationMetadata, GuidedApplicationInput, GuidedItem, MarketProfile, SetupAnswers } from '../../types/applications'
import { applicationsApi } from '../../api/applications'
import { visibilityDescriptions, visibilityLabels, type Visibility } from '../../types/access'
import Button from '../ui/Button'
import { Field, OwnerField, inputClass } from './Fields'

type Choice = Pick<GuidedItem, 'included' | 'required' | 'owner_id' | 'due_date'> & { name?: string }
type SafeDraft = { name: string; applicant: string; description: string; due_date: string; owner_id: string; visibility: Visibility; step: number; foreign_applicant: boolean; foreign_people: boolean; representative_used: boolean; people_count: number; choices: Record<string, Choice> }
const emptyDraft: SafeDraft = { name: '', applicant: '', description: '', due_date: '', owner_id: '', visibility: 'secret', step: 0, foreign_applicant: false, foreign_people: false, representative_used: false, people_count: 0, choices: {} }
function safeRead(key: string): SafeDraft {
  try { return { ...emptyDraft, ...JSON.parse(sessionStorage.getItem(key) || '{}') } } catch { return emptyDraft }
}
function proposedItems(profile: MarketProfile | undefined, answers: SetupAnswers, choices: Record<string, Choice>): GuidedItem[] {
  return (profile?.items || []).flatMap((item) => {
    if (item.condition && !answers[item.condition]) return []
    const names = item.repeat_for === 'people' ? answers.people : [null]
    return names.map((person, index) => {
      const choice = choices[`${item.key}:${index}`]
      return { name: person ? `${item.name} — ${person}` : choice?.name || item.name, kind: item.kind, required: choice?.required ?? item.required, included: choice?.included ?? true, owner_id: choice?.owner_id || null, due_date: choice?.due_date || null, profile_item_key: item.key }
    })
  })
}
export default function NewPackWizard({ jurisdictionId, jurisdiction, userId, users, busy, onCreate }: {
  jurisdictionId: string; jurisdiction?: Jurisdiction; userId: string; users: UserMention[]; busy: boolean
  onCreate: (body: GuidedApplicationInput) => Promise<boolean>
}) {
  const storageKey = `licence-pack-draft:${userId}:${jurisdictionId}`
  const [draft, setDraft] = useState<SafeDraft>(() => safeRead(storageKey))
  const [people, setPeople] = useState('')
  const [items, setItems] = useState<GuidedItem[] | null>(null)
  const [reviewed, setReviewed] = useState(false)
  const [error, setError] = useState('')
  const isSweden = ['SE', 'SWE'].includes(jurisdiction?.code?.toUpperCase() || '')
  const profile = useQuery({ queryKey: ['applications', 'market-profile', jurisdictionId], queryFn: () => applicationsApi.marketProfile(jurisdictionId), enabled: Boolean(jurisdictionId), retry: false })
  const questions = isSweden ? [] : (profile.data?.setup_questions || []).filter((question) =>
    (question.key === 'people' && question.type === 'people') ||
    (question.type === 'boolean' && typeof question.key === 'string' && ['foreign_applicant', 'foreign_people', 'representative_used'].includes(question.key))
  )
  const steps = [0, ...(questions.length ? [1] : []), ...(isSweden ? [] : [2]), 3]
  const step = steps.includes(draft.step) ? draft.step : steps.find((value) => value > draft.step) ?? 0
  const stepLabels: Record<number, string> = { 0: 'Pack details', 1: 'Market questions', 2: 'Proposed contents', 3: 'Owners and access' }
  useEffect(() => { setDraft(safeRead(storageKey)); setItems(null); setPeople(''); setReviewed(false) }, [storageKey])
  useEffect(() => { sessionStorage.setItem(storageKey, JSON.stringify({ ...draft, applicant: '', description: '' })) }, [storageKey, draft])
  const answers = useMemo<SetupAnswers>(() => ({ foreign_applicant: draft.foreign_applicant, foreign_people: draft.foreign_people, representative_used: draft.representative_used, people: people.split(/\n/).map((name) => name.trim()).filter(Boolean) }), [draft.foreign_applicant, draft.foreign_people, draft.representative_used, people])
  const proposal = useMemo(() => proposedItems(isSweden ? undefined : profile.data, answers, draft.choices), [isSweden, profile.data, answers, draft.choices])
  const chosen = items ?? proposal
  const change = <K extends keyof SafeDraft>(key: K, value: SafeDraft[K]) => setDraft((old) => ({ ...old, [key]: value }))
  const setQuestion = (key: keyof SetupAnswers, value: boolean | string) => { if (key === 'people') { setPeople(String(value)); change('people_count', String(value).split(/\n/).map((name) => name.trim()).filter(Boolean).length) } else change(key, Boolean(value)); setItems(null); setReviewed(false) }
  const advance = (step: number) => { setError(''); change('step', step) }
  const updateItem = (index: number, patch: Partial<GuidedItem>) => {
    if ('name' in patch || 'included' in patch || 'required' in patch) setReviewed(false)
    const updated = chosen.map((item, i) => i === index ? { ...item, ...patch } : item)
    setItems(updated)
    const item = updated[index]
    const siblingIndex = updated.slice(0, index).filter((candidate) => candidate.profile_item_key === item.profile_item_key).length
    if (item.profile_item_key) {
      const safeChoice: Choice = { included: item.included, required: item.required, owner_id: item.owner_id, due_date: item.due_date }
      if (!profile.data?.items.find(candidate => candidate.key === item.profile_item_key)?.repeat_for) safeChoice.name = item.name
      setDraft((old) => ({ ...old, choices: { ...old.choices, [`${item.profile_item_key}:${siblingIndex}`]: safeChoice } }))
    }
  }
  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (step !== 3 || (!isSweden && !reviewed)) { setError('Review the proposed checklist before creating the pack.'); return }
    if (!draft.name.trim()) { advance(0); setError('Enter a pack name before creating the pack.'); return }
    if (!profile.data || (profile.data.status !== 'published' && !isSweden)) { setError('The market checklist is unavailable for creation.'); return }
    if (draft.people_count !== answers.people.length) { setError('Return to Market questions and re-enter the people needing individual forms.'); return }
    const metadata: ApplicationMetadata = { name: draft.name.trim(), scope: 'full_pack', jurisdiction_id: jurisdictionId, applicant: draft.applicant.trim() || null, authority: profile.data.authority || jurisdiction?.regulator_name || null, description: draft.description.trim() || null, owner_id: draft.owner_id || null, due_date: draft.due_date || null, visibility: draft.visibility }
    const success = await onCreate({ ...metadata, profile_version: profile.data.version, setup_answers: answers, items: chosen.filter((item) => item.name.trim()).map((item) => ({ ...item, name: item.name.trim() })) })
    if (success) sessionStorage.removeItem(storageKey)
  }
  if (!jurisdictionId) return <p className="text-sm text-muted">Select a market to start a licence pack.</p>
  return <form onSubmit={create} className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">{stepLabels[step]}</h2><span className="text-sm text-muted">Step {steps.indexOf(step) + 1} of {steps.length}</span></div>
    <ol className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted" aria-label="Setup steps">{steps.map((value, index) => <li key={value} aria-current={value === step ? 'step' : undefined} className={value === step ? 'font-semibold text-accent' : ''}>{index + 1}. {stepLabels[value]}</li>)}</ol>
    {!isSweden && <p className="text-sm text-muted">{jurisdiction?.name || 'Selected market'} · Confirm the proposed checklist for this application.</p>}
    {profile.isLoading && <p role="status">Loading market checklist…</p>}
    {profile.isError && <p role="alert" className="text-danger">The market checklist could not be loaded. <button type="button" className="underline" onClick={() => void profile.refetch()}>Retry</button></p>}
    {profile.data?.status === 'draft' && !isSweden && <p role="alert" className="text-warning">This market profile is still a draft. A manager must publish it before starting a pack.</p>}
    {isSweden && <p className="rounded-lg bg-info-soft p-3 text-sm text-info">Sweden starts with a blank custom checklist. Add forms and documents in the pack workspace after creation.</p>}
    {step === 0 && <fieldset disabled={busy} className="space-y-4"><div className="grid gap-4 sm:grid-cols-2">
      <Field label="Pack name"><input required maxLength={255} className={inputClass} value={draft.name} onChange={(e) => change('name', e.target.value)} /></Field>
      <Field label="Applicant"><input maxLength={255} className={inputClass} value={draft.applicant} onChange={(e) => change('applicant', e.target.value)} /><span className="text-xs text-muted">Applicant details are kept only in this page until creation.</span></Field>
      <Field label="Deadline"><input type="date" className={inputClass} value={draft.due_date} onChange={(e) => change('due_date', e.target.value)} /></Field>
    </div><Field label="Activities and scope"><textarea className={inputClass} rows={3} value={draft.description} onChange={(e) => change('description', e.target.value)} /></Field>
      {error && <p role="alert" className="text-danger">{error}</p>}
      <Button variant="primary" disabled={!draft.name.trim() || !profile.data || (profile.data.status !== 'published' && !isSweden)} onClick={() => advance(steps[1])}>{steps[1] === 1 ? 'Continue to market questions' : steps[1] === 2 ? 'Review proposed contents' : 'Continue to owners and access'}</Button>
    </fieldset>}
    {step === 1 && <fieldset disabled={busy} className="space-y-4"><div className="space-y-3">{questions.map((question, index) => {
      const key = question.key as keyof SetupAnswers
      const label = String(question.label || key)
      if (key === 'people' && question.type === 'people') return <Field key={`${key}-${index}`} label={label}><textarea className={inputClass} rows={3} value={people} onChange={(e) => setQuestion('people', e.target.value)} placeholder="One person per line" /><span className="text-xs text-muted">Names are kept only in this page until creation. Re-enter them after a refresh.</span></Field>
      if (question.type === 'boolean' && ['foreign_applicant', 'foreign_people', 'representative_used'].includes(key)) return <label key={`${key}-${index}`} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(draft[key as keyof Pick<SafeDraft, 'foreign_applicant' | 'foreign_people' | 'representative_used'>])} onChange={(e) => setQuestion(key, e.target.checked)} />{label}</label>
      return null
    })}</div><div className="flex gap-3"><Button onClick={() => advance(0)}>Back</Button><Button variant="primary" disabled={!profile.data} onClick={() => { setItems(null); advance(2) }}>Review proposed contents</Button></div></fieldset>}
    {draft.people_count !== answers.people.length && step > 1 && <p role="alert" className="text-warning">Re-enter the people in Market questions before creating this pack. Personal names are not retained after refresh.</p>}
    {step === 2 && <fieldset disabled={busy} className="space-y-4"><div className="text-xs text-muted">{profile.data?.label} · Checked {profile.data?.checked_at || 'date unavailable'} · Checklist revision {profile.data?.revision || 1}. Confirm against current authority guidance.</div>
      {profile.data?.guidance.map((note, index) => <p key={index} className="text-sm text-muted">{note}</p>)}
      {profile.data?.source_urls.map((url, index) => /^https?:\/\//.test(url) && <a key={`${url}-${index}`} href={url} target="_blank" rel="noreferrer" className="block break-all text-sm text-accent underline">Authority source {index + 1}</a>)}
      {chosen.length === 0 ? <p className="text-sm text-muted">No items are proposed. Add blank forms and documents once the pack is created.</p> : <div className="divide-y divide-line rounded-xl border border-line">{chosen.map((item, index) => <div key={`${item.profile_item_key || 'custom'}-${index}`} className="grid items-center gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_7rem_6rem]">
        <Field label={`Item ${index + 1}`}><input className={inputClass} value={item.name} onChange={(e) => updateItem(index, { name: e.target.value })} />{profile.data?.items.find((candidate) => candidate.key === item.profile_item_key)?.guidance && <span className="text-xs text-muted">{profile.data.items.find((candidate) => candidate.key === item.profile_item_key)?.guidance}</span>}{(() => { const url = profile.data?.items.find((candidate) => candidate.key === item.profile_item_key)?.source_url; return url && /^https?:\/\//.test(url) ? <a href={url} target="_blank" rel="noreferrer" className="ml-2 text-xs text-accent underline">Source</a> : null })()}</Field>
        <span className="text-sm text-muted">{item.kind === 'annex' ? 'Supplementary form' : item.kind === 'form' ? 'Application form' : 'Document'}</span><div className="space-y-1 text-xs"><label className="block"><input type="checkbox" checked={item.included} onChange={(e) => updateItem(index, { included: e.target.checked })} /> Include</label><label className="block"><input type="checkbox" checked={item.required} onChange={(e) => updateItem(index, { required: e.target.checked })} /> Required</label></div>
      </div>)}</div>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />I have reviewed this proposed checklist for this application.</label>
      <div className="flex gap-3"><Button onClick={() => advance(questions.length ? 1 : 0)}>Back</Button><Button variant="primary" disabled={!reviewed} onClick={() => advance(3)}>Continue to owners and access</Button></div>
    </fieldset>}
    {step === 3 && <fieldset disabled={busy} className="space-y-4"><div className="grid gap-4 sm:grid-cols-2"><OwnerField users={users} value={draft.owner_id} onChange={(value) => change('owner_id', value)} /><Field label="Access"><select className={inputClass} value={draft.visibility} onChange={(e) => change('visibility', e.target.value as Visibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className="text-xs text-muted">{visibilityDescriptions[draft.visibility]} {draft.visibility !== 'organisation' && 'Choose recipients in the access controls after creation.'}</span></Field></div>
      {chosen.some((item) => item.included) && <details className="border-t border-line pt-4"><summary className="font-semibold">Assign individual items <span className="text-xs font-normal text-muted">(optional)</span></summary><p className="mt-2 text-sm text-muted">Set separate owners and due dates now, or assign them from the pack later.</p><div className="mt-3 divide-y divide-line">{chosen.map((item, index) => item.included && <div key={`${item.profile_item_key || 'custom'}-${index}`} className="grid items-center gap-3 py-3 sm:grid-cols-[minmax(0,1fr)_12rem_10rem]"><span className="break-words text-sm font-medium">{item.name}</span><OwnerField users={users} value={item.owner_id || ''} onChange={(owner_id) => updateItem(index, { owner_id: owner_id || null })} /><Field label="Due date"><input type="date" className={inputClass} value={item.due_date || ''} onChange={(e) => updateItem(index, { due_date: e.target.value || null })} /></Field></div>)}</div></details>}
      {error && <p role="alert" className="text-danger">{error}</p>}<div className="flex gap-3"><Button onClick={() => advance(isSweden ? 0 : 2)}>Back</Button><Button type="submit" variant="primary" disabled={(!isSweden && !reviewed) || busy || !profile.data || draft.people_count !== answers.people.length}>{busy ? 'Creating…' : 'Create licence pack'}</Button></div>
    </fieldset>}
  </form>
}
