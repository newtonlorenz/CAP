import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getApiErrorMessage } from '../../api/errors'
import { preparationApi } from '../../api/preparation'
import type { PreparationField, PreparationRequirementsPreview } from '../../types/preparation'
import { preparationLabel } from '../../types/preparation'
import Button from '../ui/Button'

type Source = PreparationRequirementsPreview['source']
type Selection = Record<string, { field: PreparationField; order: number }>
const pageSize = 100
const sourceIdentity = (source: Source) => JSON.stringify([source.document_id, source.kind, source.version_id, source.extraction_run_id])

export default function RequirementsImport({ existing, jurisdictionId, onImport, disabled = false, initialOpen = false, initialDocumentId = '', onDirtyChange }: {
  existing: PreparationField[]
  jurisdictionId?: string
  onImport: (fields: PreparationField[], source: Source) => void
  disabled?: boolean
  initialOpen?: boolean
  initialDocumentId?: string
  onDirtyChange?: (dirty: boolean) => void
}) {
  const [open, setOpen] = useState(initialOpen)
  const [search, setSearch] = useState('')
  const [documentId, setDocumentId] = useState(initialDocumentId)
  const [versionId, setVersionId] = useState('')
  const [skip, setSkip] = useState(0)
  const [selected, setSelected] = useState<Selection>({})
  const [message, setMessage] = useState('')
  const [selectionReady, setSelectionReady] = useState(false)
  const [selectionSource, setSelectionSource] = useState<string | null>(null)
  const [sourceNotice, setSourceNotice] = useState('')
  const capacity = Math.max(0, 500 - existing.length)
  const existingKeys = useMemo(() => new Set(existing.map((field) => field.key)), [existing])
  const selectedCount = Object.keys(selected).length

  useEffect(() => { onDirtyChange?.(Boolean(documentId)) }, [documentId, onDirtyChange])
  useEffect(() => { setDocumentId(initialDocumentId); setVersionId(''); setSkip(0); setSelected({}); setSelectionReady(false); setSelectionSource(null); setSourceNotice(''); setMessage('') }, [jurisdictionId, initialDocumentId])

  const sets = useQuery({
    queryKey: ['preparation', 'requirements-source', jurisdictionId, search],
    queryFn: () => preparationApi.requirementSets(jurisdictionId!, search),
    enabled: open && Boolean(jurisdictionId),
  })
  const versions = useQuery({
    queryKey: ['requirement-set-versions', documentId],
    queryFn: () => preparationApi.requirementVersions(documentId),
    enabled: open && Boolean(documentId),
  })
  const availableVersions = [...(versions.data?.items || [])].sort((a, b) => b.version_number - a.version_number)
  const latestVersion = availableVersions[0]
  const effectiveVersionId = versionId || latestVersion?.id
  const preview = useQuery({
    queryKey: ['preparation', 'requirements-preview', jurisdictionId, documentId, versionId || 'latest', effectiveVersionId, skip],
    queryFn: () => preparationApi.requirementsPreview({ document_id: documentId, jurisdiction_id: jurisdictionId!, version_id: versionId || undefined, skip, limit: pageSize }),
    enabled: open && Boolean(jurisdictionId && documentId && versions.data),
  })
  const previewSource = preview.data ? sourceIdentity(preview.data.source) : null
  const sourceChanged = selectionSource !== null && previewSource !== null && previewSource !== selectionSource

  useEffect(() => {
    if (!preview.data || preview.isFetching) return
    if (sourceChanged) {
      setSelected({})
      setSkip(0)
      setSelectionSource(previewSource)
      setSelectionReady(true)
      setSourceNotice('The source changed while you were browsing. Your selection has been cleared. Review the current points and select the questions again.')
      return
    }
    if (selectionReady) return
    // Small forms are ready to import; larger sets require an explicit subset.
    const available = preview.data.fields.filter((field) => !existingKeys.has(field.key))
    setSelected(preview.data.total <= capacity ? Object.fromEntries(available.map((field, index) => [field.key, { field, order: skip + index }])) : {})
    setSelectionSource(previewSource)
    setSelectionReady(true)
  }, [preview.data, preview.isFetching, previewSource, sourceChanged, selectionReady, capacity, existingKeys, skip])

  const resetSelection = () => { setSkip(0); setSelected({}); setSelectionReady(false); setSelectionSource(null); setSourceNotice(''); setMessage('') }
  const clear = () => { setDocumentId(''); setVersionId(''); resetSelection() }
  const toggle = (field: PreparationField, order: number, checked: boolean) => {
    setSelected((current) => {
      const next = { ...current }
      if (checked) next[field.key] = { field, order }
      else delete next[field.key]
      return next
    })
  }
  const rows = preview.data?.fields || []
  const unselectedOnPage = rows.filter((field) => !existingKeys.has(field.key) && !selected[field.key])
  const pageCanFit = selectedCount + unselectedOnPage.length <= capacity
  const add = () => {
    if (!preview.data || sourceChanged || preview.isFetching || !selectedCount || selectedCount > capacity) return
    const fields = Object.values(selected).sort((a, b) => a.order - b.order).map(({ field }) => field)
    onImport(fields, preview.data.source)
    clear()
    setMessage(`${fields.length} questions added. Review their wording and answer types, then save the form questions.`)
  }

  return <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="rounded-lg border border-line px-4 py-3">
    <summary className="cursor-pointer font-semibold text-accent">Use imported requirements</summary>
    <div className="mt-4 space-y-4">
      <p className="max-w-prose text-sm text-muted">Use questions already in Requirements, including text extracted from a PDF. Choose the points for this form, then check their wording and answer types. Answers, evidence and compliance decisions are not copied.</p>
      {!jurisdictionId ? <p className="text-sm text-muted">Choose a jurisdiction space to see its imported requirements.</p> : <>
        <label className="block text-sm font-medium">Search requirement sources
          <input type="search" className="mt-1 w-full px-3 py-2" value={search} disabled={disabled} placeholder="Annex A, application form…" onChange={(event) => setSearch(event.target.value)} />
        </label>
        <label className="block text-sm font-medium">Requirement set in this jurisdiction
          <select className="mt-1 w-full px-3 py-2" value={documentId} disabled={disabled || sets.isLoading} onChange={(event) => { setDocumentId(event.target.value); setVersionId(''); resetSelection() }}>
            <option value="">Choose requirement set</option>
            {documentId && !sets.data?.items.some((item) => item.document_id === documentId) && <option value={documentId}>{preview.data?.source.name || 'Selected requirement set'}</option>}
            {sets.data?.items.map((item) => <option key={item.document_id} value={item.document_id}>{item.name || item.filename || 'Unnamed requirement set'} · {preparationLabel(item.document_status)}</option>)}
          </select>
        </label>
        {sets.isLoading && <p role="status" className="text-sm">Loading requirement sources…</p>}
        {sets.isError && <p role="alert" className="text-sm text-danger">Requirement sources could not be loaded. <button type="button" className="underline" onClick={() => void sets.refetch()}>Retry</button></p>}
        {sets.isSuccess && !sets.data.items.length && <p className="text-sm text-muted">No matching requirement sets in this jurisdiction. Create a manual set or import a PDF in Requirements, or use an Excel question template.</p>}
        {(sets.data?.total || 0) > 1000 && <p className="text-xs text-muted">Showing the first 1,000 matches. Narrow your search to find another form.</p>}
        {documentId && <>
          {versions.isLoading && <p role="status" className="text-sm">Loading source versions…</p>}
          {versions.isError && <p role="alert" className="text-sm text-danger">Source versions could not be loaded. <button type="button" className="underline" onClick={() => void versions.refetch()}>Retry</button></p>}
          {availableVersions.length > 0 && <label className="block text-sm font-medium">Source version
            <select className="mt-1 w-full px-3 py-2" value={versionId} disabled={disabled} onChange={(event) => { setVersionId(event.target.value); resetSelection() }}>
              <option value="">Latest available · v{latestVersion.version_number} · {preparationLabel(latestVersion.status)}</option>
              {availableVersions.map((version) => <option key={version.id} value={version.id}>v{version.version_number} · {preparationLabel(version.status)}{version.is_current ? ' · Current baseline' : ''}</option>)}
            </select>
          </label>}
          {preview.isFetching && <p role="status" className="text-sm">Loading source questions…</p>}
          {preview.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(preview.error, 'Source questions could not be loaded.')} <button type="button" className="underline" onClick={() => void preview.refetch()}>Retry</button></p>}
          {preview.data && <>
            <div className="space-y-1 text-sm">
              <p className="font-semibold break-words">{preview.data.source.name}</p>
              <p className="text-xs text-muted">{preview.data.source.kind === 'extracted_requirements' ? `Extracted PDF text · ${preparationLabel(preview.data.source.extraction_status || 'extracted')} · Awaiting requirement review` : preview.data.source.version_number !== null ? `Source v${preview.data.source.version_number} · ${preparationLabel(preview.data.source.version_status || preview.data.source.status)}` : `${preparationLabel(preview.data.source.status)} · Current requirements`}</p>
              <p className="text-xs text-muted">Original references and the source {preview.data.source.kind === 'extracted_requirements' ? 'extraction' : 'version'} stay linked to the imported questions.</p>
            </div>
            {sourceNotice && <p role="status" className="text-sm text-warning">{sourceNotice}</p>}
            {preview.data.warnings.map((warning, index) => <p key={index} className="text-sm text-warning">{warning}</p>)}
            {preview.data.total > capacity && <p className="text-sm text-muted">This source has {preview.data.total} points. Select up to {capacity} questions for this form; add further sections as separate forms.</p>}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-semibold">{selectedCount} selected · {capacity} available spaces</h4>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={disabled || sourceChanged || !unselectedOnPage.length || !pageCanFit || preview.isFetching} onClick={() => setSelected((current) => ({ ...current, ...Object.fromEntries(unselectedOnPage.map((field) => [field.key, { field, order: skip + rows.findIndex((row) => row.key === field.key) }])) }))}>Select this page</Button>
                <Button size="sm" variant="ghost" disabled={disabled || !selectedCount} onClick={() => setSelected({})}>Deselect all</Button>
              </div>
            </div>
            <ul className="max-h-80 divide-y divide-line overflow-auto" aria-label="Requirement question preview">{rows.map((field, index) => {
              const alreadyAdded = existingKeys.has(field.key)
              return <li key={field.key} className="py-3"><label className="flex items-start gap-3 text-sm">
                <input type="checkbox" className="mt-1 shrink-0" checked={alreadyAdded || Boolean(selected[field.key])} disabled={disabled || sourceChanged || alreadyAdded || preview.isFetching || (!selected[field.key] && selectedCount >= capacity)} onChange={(event) => toggle(field, skip + index, event.target.checked)} />
                <span className="min-w-0"><span className="block text-xs text-muted">{field.section} · Multiline answer · {field.required ? 'Required' : 'Optional'}{alreadyAdded ? ' · Already in this form' : ''}</span><span className="mt-1 block whitespace-pre-wrap break-words">{field.label}</span>{field.help_text && <span className="mt-1 block whitespace-pre-wrap break-words text-xs text-muted">{field.help_text}</span>}</span>
              </label></li>
            })}</ul>
            {(preview.data.unavailable || []).map((item, index) => <p key={item.requirement_id || `${item.reference_id}-${index}`} className="text-sm text-warning">{item.reference_id || 'Source point'}: {item.reason}</p>)}
            {!preview.data.total && <p className="text-sm text-muted">No active questions in this source version. Choose another version or import the form’s questions from Excel.</p>}
            {preview.data.total > pageSize && <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted">Points {skip + 1}–{Math.min(skip + pageSize, preview.data.total)} of {preview.data.total}</p>
              <div className="flex gap-2"><Button size="sm" disabled={disabled || preview.isFetching || skip === 0} onClick={() => setSkip((current) => Math.max(0, current - pageSize))}>Previous points</Button><Button size="sm" disabled={disabled || preview.isFetching || skip + pageSize >= preview.data.total} onClick={() => setSkip((current) => current + pageSize)}>Next points</Button></div>
            </div>}
            <Button disabled={disabled || sourceChanged || preview.isFetching || !selectedCount || selectedCount > capacity} onClick={add}>Add {selectedCount || ''} selected questions to form</Button>
          </>}
          <Button size="sm" variant="ghost" disabled={disabled} onClick={clear}>Clear requirement selection</Button>
        </>}
      </>}
      {message && <p role="status" className="text-sm text-success">{message}</p>}
    </div>
  </details>
}
