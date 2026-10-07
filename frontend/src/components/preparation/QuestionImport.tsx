import { useEffect, useRef, useState } from 'react'
import { preparationApi } from '../../api/preparation'
import { getApiErrorMessage } from '../../api/errors'
import type { ImportEnhancement, PreparationField, PreparationFieldType } from '../../types/preparation'
import { nextPreparationFieldKey, preparationLabel, PREPARATION_SECTION_MAX_LENGTH } from '../../types/preparation'
import Button from '../ui/Button'

type Preview = Awaited<ReturnType<typeof preparationApi.importPreview>>
const columns = ['question', 'reference', 'section', 'type', 'options', 'required', 'help'] as const
type Column = typeof columns[number]
const labels: Record<Column, string> = { question: 'Question text', reference: 'Question number', section: 'Section', type: 'Answer type', options: 'Choices', required: 'Required', help: 'Instructions' }
const aliases: Record<Column, string[]> = {
  question: ['question', 'question text', 'label', 'point', 'requirement'],
  reference: ['number', 'no', 'no.', 'reference', 'question number', 'ref'],
  section: ['section', 'heading', 'category'], type: ['type', 'input type', 'answer type'],
  options: ['options', 'choices'], required: ['required', 'mandatory'], help: ['help', 'help text', 'instructions', 'guidance'],
}
const typeNames: Record<string, PreparationFieldType> = {
  text: 'text', 'short text': 'text', multiline: 'multiline', textarea: 'multiline', 'long text': 'multiline',
  yes_no: 'yes_no', 'yes/no': 'yes_no', boolean: 'yes_no', checkbox: 'yes_no',
  date: 'date', number: 'number', choice: 'choice', select: 'choice', dropdown: 'choice', evidence: 'evidence',
}
function guess(headers: string[]) {
  return Object.fromEntries(columns.map((key) => [key, headers.findIndex((header) => aliases[key].includes(header.trim().toLowerCase()))])) as Record<Column, number>
}

export default function QuestionImport({ existing, onImport, disabled = false, initialOpen = false, onDirtyChange }: {
  existing: PreparationField[]; onImport: (fields: PreparationField[]) => void; disabled?: boolean; initialOpen?: boolean; onDirtyChange?: (dirty: boolean) => void
}) {
  const [open, setOpen] = useState(initialOpen)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [paste, setPaste] = useState('')
  const [headerRow, setHeaderRow] = useState(0)
  const [mapping, setMapping] = useState<Record<Column, number>>(guess([]))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const request = useRef(0)
  const qualityGeneration = useRef({ value: 0 })
  const [jev, setJev] = useState<{ enabled: boolean; revision: number } | null>(null)
  const [consent, setConsent] = useState(false)
  const [checking, setChecking] = useState(false)
  const [quality, setQuality] = useState<ImportEnhancement | null>(null)
  const invalidateQuality = () => { qualityGeneration.current.value++; setQuality(null); setChecking(false) }
  useEffect(() => {
    let mounted = true
    const generation = qualityGeneration.current
    void preparationApi.importCapabilities().then((value) => { if (mounted) setJev(value.jev || null) }).catch(() => {})
    return () => { mounted = false; generation.value++ }
  }, [])
  const enhance = async () => {
    if (!preview || !jev || !consent) return
    const generation = ++qualityGeneration.current.value
    setChecking(true); setQuality(null)
    try {
      const rows = preview.rows.slice(headerRow + 1).map((row, index) => ({
        row_index: headerRow + 1 + index,
        question: (row[mapping.question] || '').trim(), help: (row[mapping.help] || '').trim().startsWith('=') ? '' : (row[mapping.help] || '').trim(),
        explicit_type: !!(row[mapping.type] || '').trim(), explicit_required: !!(row[mapping.required] || '').trim(),
      })).filter((row) => row.question && !row.question.startsWith('=')).slice(0, 100)
      const result = await preparationApi.enhanceImport({ headers: (preview.rows[headerRow] || []).map((value) => value.trim().startsWith('=') ? '' : value), rows, header_row: headerRow, mapping, external_processing_confirmed: true, settings_revision: jev.revision })
      if (generation === qualityGeneration.current.value) setQuality(result)
    } catch (caught) { if (generation === qualityGeneration.current.value) setError(getApiErrorMessage(caught, 'Jev check unavailable. You can still import the questions.')) }
    finally { if (generation === qualityGeneration.current.value) setChecking(false) }
  }
  const load = async (input: File, sheet?: string) => {
    invalidateQuality()
    const generation = ++request.current
    setBusy(true); setError(''); setMessage(''); setPreview(null)
    onDirtyChange?.(true)
    try {
      const result = await preparationApi.importPreview(input, sheet)
      if (generation !== request.current) return
      const first = Math.max(0, result.rows.findIndex((row) => row.some((cell) => cell.trim())))
      setPreview(result); setHeaderRow(first); setMapping(guess(result.rows[first] || [])); setFile(input)
    } catch (caught) { if (generation === request.current) setError(getApiErrorMessage(caught, 'Could not read the spreadsheet. Use an .xlsx, UTF-8 CSV or tab-separated file.')) }
    finally { if (generation === request.current) setBusy(false) }
  }
  const fields: PreparationField[] = []
  const errors: string[] = []
  let skipped = 0
  let section = 'General'
  if (preview && mapping.question >= 0) {
    for (let i = headerRow + 1; i < preview.rows.length; i++) {
      const row = preview.rows[i]
      const cell = (key: Column) => (row[mapping[key]] || '').trim()
      if (cell('section')) section = cell('section')
      if (!cell('question')) { if (row.some((value) => value.trim())) skipped++; continue }
      const label = [cell('reference'), cell('question')].filter(Boolean).join(' ')
      const rawType = cell('type').toLowerCase()
      const suggestion = quality?.field_suggestions.find((item) => item.row_index === i && item.confidence >= .98)
      const type = rawType ? typeNames[rawType] : suggestion?.type || 'text'
      const required = cell('required').toLowerCase()
      const options = cell('options').split(/\r?\n|\|/).map((value) => value.trim()).filter(Boolean)
      const problem = !type ? `unknown answer type “${cell('type')}”` :
        label.length > 2000 ? 'question exceeds 2,000 characters; move longer instructions to the Instructions column' :
        section.length > PREPARATION_SECTION_MAX_LENGTH ? 'section exceeds 1,000 characters' :
        cell('help').length > 10000 ? 'instructions exceed 10,000 characters' :
        required && !['yes', 'true', '1', 'required', 'no', 'false', '0', 'optional'].includes(required) ? `unknown Required value “${cell('required')}”` :
        type === 'choice' && (!options.length || options.length > 50 || new Set(options).size !== options.length || options.some((value) => value.length > 255)) ? 'use 1–50 distinct choices, separated by | or line breaks' : ''
      if (problem) errors.push(`Row ${i + 1}: ${problem}.`)
      fields.push({ key: nextPreparationFieldKey([...existing, ...fields]), label, section, type: type || 'text', required: required ? !['no', 'false', '0', 'optional'].includes(required) : suggestion?.required ?? true, options: type === 'choice' ? options : [], help_text: cell('help') || null, reuse_key: null })
    }
  }
  if (fields.length + existing.length > 500) errors.push(`This would create ${fields.length + existing.length} questions. Split the form into sections of at most 500 questions.`)
  const headers = preview?.rows[headerRow] || []
  return <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="rounded-lg border border-line px-4 py-3">
    <summary className="cursor-pointer font-semibold text-accent">Import questions from Excel</summary>
    <div className="mt-4 space-y-4">
      <p className="max-w-prose text-sm text-muted">Upload a spreadsheet or paste cells from Excel. Match your columns, review the questions, then add them to this form. Import blank questions only. Keep personal answers in the completed form.</p>
      <Button size="sm" loading={downloading} disabled={disabled} onClick={async () => {
        setDownloading(true); setDownloadError('')
        try { await preparationApi.download('templates/import-template', 'CAP-question-import-template.xlsx') }
        catch (caught) { setDownloadError(getApiErrorMessage(caught, 'Could not download the Excel template. Try again.')) }
        finally { setDownloading(false) }
      }}>Download Excel template</Button>
      {downloadError && <p role="alert" className="text-sm text-danger">{downloadError}</p>}
      <label className="block text-sm font-medium">Question spreadsheet
        <input type="file" accept=".xlsx,.csv,.tsv" disabled={disabled || busy} className="mt-2 block w-full text-sm" onChange={(event) => { const selected = event.target.files?.[0]; if (selected) void load(selected); event.target.value = '' }} />
      </label>
      <details><summary className="cursor-pointer text-sm font-medium">Or paste cells from Excel</summary><label className="mt-3 block text-sm">Copied cells, including column headings<textarea rows={4} className="mt-1 w-full px-3 py-2" value={paste} disabled={disabled || busy} onChange={(event) => { setPaste(event.target.value); onDirtyChange?.(true) }} placeholder={'Section\tQuestion\tType\nApplicant\tCompany name\ttext'} /></label><Button className="mt-2" disabled={disabled || busy || !paste.trim()} onClick={() => void load(new File([paste], 'questions.tsv', { type: 'text/tab-separated-values' }))}>Preview pasted questions</Button></details>
      {busy && <p role="status" className="text-sm">Reading spreadsheet…</p>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {preview && <>
        {preview.sheets.length > 1 && <label className="block text-sm font-medium">Worksheet<select className="mt-1 w-full px-3 py-2" value={preview.sheet_name} disabled={disabled || busy} onChange={(event) => { if (file) void load(file, event.target.value) }}>{preview.sheets.map((sheet) => <option key={sheet}>{sheet}</option>)}</select></label>}
        <label className="block text-sm font-medium">Column headings on row<select className="mt-1 w-full px-3 py-2" value={headerRow} disabled={disabled} onChange={(event) => { invalidateQuality(); const row = Number(event.target.value); setHeaderRow(row); setMapping(guess(preview.rows[row] || [])) }}>{preview.rows.map((row, index) => <option key={index} value={index}>{index + 1}: {row.filter(Boolean).join(' · ').slice(0, 90) || '(blank row)'}</option>)}</select></label>
        <div className="grid gap-3 sm:grid-cols-2">{columns.map((key) => <label key={key} className="text-sm font-medium">{labels[key]} column{key === 'question' ? ' (required)' : ''}<select className="mt-1 w-full px-3 py-2" value={mapping[key]} disabled={disabled} onChange={(event) => { invalidateQuality(); setMapping({ ...mapping, [key]: Number(event.target.value) }) }}><option value={-1}>{key === 'question' ? 'Choose column' : key === 'type' ? 'Default: short text' : key === 'required' ? 'Default: required' : 'Not used'}</option>{headers.map((header, index) => <option key={index} value={index}>{index + 1}: {header || '(unnamed)'}</option>)}</select></label>)}</div>
        <p className="text-xs text-muted">Types: text, multiline, yes/no (or checkbox), choice, date, number, evidence. Yes/no requires an explicit answer. Separate choices with | or a line break. Blank section cells continue the previous section.</p>
        {jev?.enabled && <div className="space-y-2">
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={consent} disabled={disabled || checking} onChange={(event) => { invalidateQuality(); setConsent(event.target.checked) }} />I agree to send column headings and mapped question wording and instructions to Jev for this preview check. Applicant answers and unused columns are excluded.</label>
          <Button disabled={disabled || checking || !consent} onClick={() => void enhance()}>{checking ? 'Checking preview…' : 'Enhance preview'}</Button>
        </div>}
        {quality && <div className="space-y-2 text-sm" role="status">
          <p>{quality.status === 'completed' ? 'Preview checked with Jev. Review inferred answer types and requiredness before adding questions.' : 'Preview check incomplete. Normal import remains available.'}</p>
          {Object.entries(quality.suggested_mapping).filter(([key, value]) => value !== mapping[key as Column]).map(([key, value]) => <p key={key}>Suggested {labels[key as Column]} column: {(value ?? -1) + 1}. Select it above to apply.</p>)}
          {quality.field_suggestions.filter((item) => item.duplicate_of != null).map((item) => <p key={item.row_index}>Review rows {item.row_index + 1} and {item.duplicate_of! + 1}: possible duplicate. Both are retained.</p>)}
          {quality.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>}
        {preview.warnings.map((warning, index) => <p key={index} className="text-sm text-warning">{warning}</p>)}
        {skipped > 0 && <p className="text-sm text-warning">{skipped} non-empty row(s) have no question and will be skipped. Check your column mapping.</p>}
        {errors.length > 0 && <div role="alert" className="text-sm text-danger"><p>Fix these rows before importing:</p><ul className="list-disc pl-5">{errors.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
        {fields.length > 0 && <div><h4 className="font-semibold">Preview · {fields.length} questions</h4><ol className="mt-2 max-h-80 divide-y divide-line overflow-auto" aria-label="Imported question preview">{fields.map((field) => <li key={field.key} className="py-3"><p className="text-xs text-muted">{field.section} · {preparationLabel(field.type)} · {field.required ? 'Required' : 'Optional'}</p><p className="mt-1 break-words text-sm">{field.label}</p>{field.help_text && <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{field.help_text}</p>}</li>)}</ol></div>}
        <Button disabled={disabled || busy || !fields.length || errors.length > 0} onClick={() => { invalidateQuality(); onImport(fields); setPreview(null); setPaste(''); setMessage(`${fields.length} questions added. Review them and save the form questions.`); onDirtyChange?.(false) }}>Add {fields.length || ''} questions to form</Button>
      </>}
      {(preview || paste || error) && <Button size="sm" variant="ghost" disabled={busy} onClick={() => { invalidateQuality(); setPreview(null); setPaste(''); setError(''); setMessage(''); onDirtyChange?.(false) }}>Clear import</Button>}
      {message && <p role="status" className="text-sm text-success">{message}</p>}
    </div>
  </details>
}
