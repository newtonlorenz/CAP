import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { getApiErrorMessage } from '../../api/errors'
import { preparationApi } from '../../api/preparation'
import Button from '../ui/Button'
import Card from '../ui/Card'
import QuestionImport from './QuestionImport'
import RequirementsImport from './RequirementsImport'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import type {
  PreparationField,
  PreparationKind,
  PreparationStarter,
  PreparationTemplate,
} from '../../types/preparation'
import {
  PREPARATION_FIELD_TYPES,
  PREPARATION_SECTION_MAX_LENGTH,
  PREPARATION_KINDS,
  nextPreparationFieldKey,
  preparationLabel,
} from '../../types/preparation'

const emptyField = (key: string): PreparationField => ({
  key,
  label: '',
  section: 'General',
  help_text: null,
  type: 'text',
  required: true,
  options: [],
  reuse_key: null,
})
const emptyDraft = (kind: PreparationKind = 'questionnaire'): PreparationStarter => ({
  name: '',
  description: '',
  kind,
  fields: [emptyField('field_1')],
})
const fieldClass = 'mt-1 w-full px-3 py-2'

export default function TemplateBuilder({
  canManage,
  kindScope,
  embedded = false,
  initialName = '',
  jurisdictionId,
  initialImportSource,
  initialRequirementsDocumentId,
  onSaved,
  onDirtyChange,
}: {
  canManage: boolean
  kindScope?: PreparationKind
  embedded?: boolean
  initialName?: string
  jurisdictionId?: string
  initialImportSource?: 'excel' | 'requirements'
  initialRequirementsDocumentId?: string
  onSaved?: (template: PreparationTemplate) => void
  onDirtyChange?: (dirty: boolean) => void
}) {
  const queryClient = useQueryClient()
  const templates = useQuery({
    queryKey: ['preparation', 'templates'],
    queryFn: preparationApi.templates,
  })
  const starters = useQuery({
    queryKey: ['preparation', 'starters'],
    queryFn: preparationApi.starters,
    enabled: canManage,
  })
  const [templateSearch, setTemplateSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(Boolean(embedded || initialImportSource || initialName))
  const scopedTemplates = templates.data?.items.filter((item) => !kindScope || item.kind === kindScope) || []
  const scopedStarters = starters.data?.items.filter((item) => !kindScope || item.kind === kindScope) || []
  const visibleTemplates = scopedTemplates.filter(item => `${item.name} ${item.description || ''}`.toLowerCase().includes(templateSearch.trim().toLowerCase()))
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState<PreparationStarter>(() => ({ ...emptyDraft(kindScope), name: initialName }))
  const [editingRevision, setEditingRevision] = useState<number | null>(null)
  const [active, setActive] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [importDirty, setImportDirty] = useState(false)
  const [requirementsDirty, setRequirementsDirty] = useState(false)
  const [importKey, setImportKey] = useState(0)
  useDraftNavigationGuard(dirty || importDirty || requirementsDirty)
  useEffect(() => { onDirtyChange?.(dirty || importDirty || requirementsDirty) }, [dirty, importDirty, requirementsDirty, onDirtyChange])
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || importDirty || requirementsDirty) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, importDirty, requirementsDirty])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const selected = templates.data?.items.find(
    (template) => template.id === selectedId,
  )

  useEffect(() => {
    if (!selected || dirty) return
    setDraft({
      name: selected.name,
      description: selected.description,
      kind: selected.kind,
      fields: selected.fields,
    })
    setEditingRevision(selected.revision)
    setActive(selected.active)
  }, [selected, dirty])

  const choose = (template?: PreparationTemplate | PreparationStarter) => {
    if (busy) return
    if ((dirty || importDirty || requirementsDirty) && !window.confirm('Discard unsaved blank form changes?')) return
    setEditorOpen(true)
    setImportDirty(false)
    setRequirementsDirty(false)
    setImportKey((key) => key + 1)
    setSelectedId(template && 'id' in template ? template.id : '')
    setEditingRevision(
      template && 'revision' in template ? template.revision : null,
    )
    setDraft(
      template
        ? {
            name: template.name,
            description: template.description,
            kind: template.kind,
            fields: template.fields.map((field) => ({
              ...field,
              options: [...field.options],
            })),
          }
        : emptyDraft(kindScope),
    )
    setActive(template && 'active' in template ? template.active : true)
    setDirty(false)
    setError('')
    setMessage('')
  }
  const update = (patch: Partial<PreparationStarter>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setDirty(true)
  }
  const updateField = (index: number, patch: Partial<PreparationField>) => {
    update({
      fields: draft.fields.map((field, at) =>
        at === index ? { ...field, ...patch } : field,
      ),
    })
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (importDirty || requirementsDirty) { setError('Finish adding the previewed questions before saving, or clear the import.'); return }
    const keys = draft.fields.map((field) => field.key.trim())
    if (
      !draft.name.trim() ||
      !draft.fields.length ||
      draft.fields.length > 500 ||
      keys.some((key) => !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(key)) ||
      new Set(keys).size !== keys.length ||
      draft.fields.some(
        (field) =>
          !field.label.trim() ||
          (field.type === 'choice' &&
            (!field.options.length ||
              new Set(field.options).size !== field.options.length ||
              field.options.some((option) => !option.trim()))),
      )
    ) {
      setError(
        'Enter a name and 1–500 questions with unique identifier keys and labels. Choice options must be distinct and nonblank.',
      )
      return
    }
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const fields = draft.fields.map((field) => ({
        ...field,
        key: field.key.trim(),
        label: field.label.trim(),
        section: field.section.trim() || 'General',
        help_text: field.help_text?.trim() || null,
        reuse_key: field.reuse_key?.trim() || null,
        options:
          field.type === 'choice'
            ? field.options.map((option) => option.trim())
            : [],
      }))
      const saved =
        selectedId && editingRevision !== null
          ? await preparationApi.updateTemplate(selectedId, {
              name: draft.name.trim(),
              description: draft.description?.trim() || '',
              kind: draft.kind as PreparationKind,
              fields,
              active,
              expected_revision: editingRevision,
            })
          : await preparationApi.createTemplate({
              name: draft.name.trim(),
              description: draft.description?.trim() || '',
              kind: draft.kind as PreparationKind,
              fields,
            })
      setSelectedId(saved.id)
      setEditingRevision(saved.revision)
      setDirty(false)
      queryClient.setQueryData(
        ['preparation', 'templates'],
        (old: { items: PreparationTemplate[]; total: number } | undefined) =>
          old
            ? {
                ...old,
                items: [
                  saved,
                  ...old.items.filter((item) => item.id !== saved.id),
                ],
                total: old.items.some((item) => item.id === saved.id)
                  ? old.total
                  : old.total + 1,
              }
            : old,
      )
      setMessage('Blank form saved. Existing forms keep their original questions.')
      onSaved?.(saved)
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 409) {
        if (!selectedId) {
          setError(getApiErrorMessage(caught, 'The source questions changed. Clear the import, preview the latest source, then save again.'))
          return
        }
        const latest = await templates.refetch()
        const current = latest.data?.items.find(
          (item) => item.id === selectedId,
        )
        if (current) setEditingRevision(current.revision)
        setError(
          'The blank form changed elsewhere. Your edits remain here. Review the latest version before saving again.',
        )
      } else
        setError(getApiErrorMessage(caught, 'Could not save this blank form.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      {!embedded && <Card hidden={editorOpen && canManage} className="p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Templates</h2>
          {canManage && (
            <Button size="sm" onClick={() => choose()}>
              New blank form
            </Button>
          )}
          {canManage && !editorOpen && (dirty || importDirty || requirementsDirty) && (
            <Button onClick={() => setEditorOpen(true)}>Resume draft</Button>
          )}
        </div>
        <label className="mt-4 block max-w-md text-sm">Search templates<input type="search" className="mt-1 block w-full px-3 py-2" value={templateSearch} onChange={event => setTemplateSearch(event.target.value)} /></label>
        {templates.isLoading ? (
          <p role="status" className="mt-4 text-muted">
            Loading blank forms…
          </p>
        ) : templates.isError ? (
          <p role="alert" className="mt-4 text-danger">
            Templates could not be loaded.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => void templates.refetch()}
            >
              Retry
            </button>
          </p>
        ) : !visibleTemplates.length ? (
          <p className="mt-4 text-muted">
            {templateSearch ? 'No templates match your search. Try another name.' : 'No saved blank forms yet. Create a blank form to reuse its questions.'}
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-line">
            {visibleTemplates.map((template) => (
              <li key={template.id}>
                <button
                  type="button"
                  onClick={() => choose(template)}
                  className="w-full py-3 text-left focus-visible:outline-accent"
                >
                  <span className="block font-semibold text-ink">
                    {template.name}
                  </span>
                  <span className="text-xs text-muted">
                    {preparationLabel(template.kind)} · v{template.revision}
                    {!template.active ? ' · Inactive' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>}
      {canManage ? (
        <Card hidden={!editorOpen} className={embedded ? "border-0 shadow-none p-0" : "p-5 sm:p-7"}>
          {!embedded && <Button className="mb-4" disabled={busy} onClick={() => setEditorOpen(false)}>Back to templates{dirty || importDirty || requirementsDirty ? ' · Draft kept' : ''}</Button>}
          <h2 className="text-lg font-semibold">
            {selectedId ? 'Edit blank form' : embedded ? 'Set up form questions' : 'Save a reusable blank form'}
          </h2>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Keep the source form’s question numbers, wording and sections. Saved blank forms contain reusable questions shared across your organisation; enter confidential answers only in the completed form.
          </p>
          <form className="mt-6" onSubmit={submit}><fieldset disabled={busy} className="space-y-5">
            <RequirementsImport key={`requirements-${selectedId}-${importKey}`} existing={draft.fields.filter((field) => field.label.trim())} jurisdictionId={jurisdictionId} initialOpen={initialImportSource === 'requirements'} initialDocumentId={selectedId || importKey ? undefined : initialRequirementsDocumentId} disabled={busy} onDirtyChange={setRequirementsDirty} onImport={(fields, source) => update({ fields: [...draft.fields.filter((field) => field.label.trim()), ...fields], ...(!draft.name.trim() ? { name: source.name } : {}) })} />
            <QuestionImport key={`${selectedId}-${importKey}`} existing={draft.fields.filter((field) => field.label.trim())} initialOpen={initialImportSource === 'excel'} disabled={busy} onDirtyChange={setImportDirty} onImport={(fields) => update({ fields: [...draft.fields.filter((field) => field.label.trim()), ...fields] })} />
            <label className="block text-sm font-medium">
              Illustrative starter
              <select
                className={fieldClass}
                value=""
                onChange={(event) => {
                  const starter =
                    scopedStarters[Number(event.target.value)]
                  if (starter) choose(starter)
                }}
              >
                <option value="">Choose a starter (optional)</option>
                {scopedStarters.map((starter, index) => (
                  <option value={index} key={`${starter.name}-${index}`}>
                    {starter.name}
                  </option>
                ))}
              </select>
            </label>
            {starters.isError && (
              <p role="alert" className="text-sm text-danger">
                Starters could not be loaded. You can still build a blank
                template.
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium">
                {embedded ? 'Shared blank form name' : 'Blank form name'}
                <input
                  required
                  maxLength={255}
                  className={fieldClass}
                  value={draft.name}
                  onChange={(event) => update({ name: event.target.value })}
                />
              </label>
              <label className="text-sm font-medium">
                Kind
                <select
                  className={fieldClass}
                  value={draft.kind}
                  disabled={Boolean(kindScope)}
                  onChange={(event) =>
                    update({ kind: event.target.value as PreparationKind })
                  }
                >
                  {(kindScope ? [kindScope] : PREPARATION_KINDS).map((kind) => (
                    <option value={kind} key={kind}>
                      {preparationLabel(kind)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block text-sm font-medium">
              Description
              <textarea
                rows={2}
                className={fieldClass}
                value={draft.description ?? ''}
                onChange={(event) =>
                  update({ description: event.target.value })
                }
              />
            </label>
            {selectedId && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(event) => {
                    setActive(event.target.checked)
                    setDirty(true)
                  }}
                />
                Available for new forms
              </label>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
              <h3 className="font-semibold">Fields</h3>
              <Button
                size="sm"
                disabled={draft.fields.length >= 500}
                onClick={() =>
                  update({
                    fields: [
                      ...draft.fields,
                      emptyField(nextPreparationFieldKey(draft.fields)),
                    ],
                  })
                }
              >
                Add field
              </Button>
            </div>
            {draft.fields.map((field, index) => (
              <fieldset
                key={index}
                className="space-y-4 rounded-xl bg-subtle p-4"
              >
                <legend className="px-1 text-sm font-semibold">
                  Field {index + 1}
                </legend>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="text-sm font-medium">
                    Label
                    <textarea
                      required
                      rows={2}
                      maxLength={2000}
                      className={fieldClass}
                      value={field.label}
                      onChange={(event) =>
                        updateField(index, { label: event.target.value })
                      }
                    />
                  </label>
                  <label className="text-sm font-medium">
                    Section
                    <input
                      maxLength={PREPARATION_SECTION_MAX_LENGTH}
                      className={fieldClass}
                      value={field.section}
                      onChange={(event) =>
                        updateField(index, { section: event.target.value })
                      }
                    />
                  </label>
                  <label className="text-sm font-medium">
                    Input type
                    <select
                      className={fieldClass}
                      value={field.type}
                      onChange={(event) =>
                        updateField(index, {
                          type: event.target.value as PreparationField['type'],
                          options: [],
                        })
                      }
                    >
                      {PREPARATION_FIELD_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {preparationLabel(type)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className="block text-sm font-medium">
                  Help text
                  <textarea
                    maxLength={10000}
                    rows={2}
                    className={fieldClass}
                    value={field.help_text ?? ''}
                    onChange={(event) =>
                      updateField(index, { help_text: event.target.value })
                    }
                  />
                </label>
                {field.source && <p className="text-xs text-muted break-words">Source: {field.source.document_name} · {field.source.reference_id || 'Unnumbered point'} · {field.source.kind === 'extracted_requirement' ? 'Extracted PDF text, awaiting requirement review' : field.source.version_number !== null ? `v${field.source.version_number} (${preparationLabel(field.source.version_status || field.source.document_status)})` : preparationLabel(field.source.document_status)}. The original source remains linked when you edit this question.</p>}
                {field.type === 'choice' && (
                  <label className="block text-sm font-medium">
                    Choices, one per line
                    <textarea
                      required
                      rows={4}
                      className={fieldClass}
                      value={field.options.join('\n')}
                      onChange={(event) =>
                        updateField(index, {
                          options: event.target.value.split('\n'),
                        })
                      }
                    />
                  </label>
                )}
                <details className="rounded-lg border border-line bg-surface px-4 py-3">
                  <summary className="text-sm font-semibold">
                    Field references (advanced)
                  </summary>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <label className="text-sm font-medium">
                      Field key
                      <input
                        required
                        maxLength={64}
                        pattern="[A-Za-z](?:[A-Za-z0-9_]|-)*"
                        className={fieldClass}
                        value={field.key}
                        onInvalid={(event) =>
                          event.currentTarget
                            .closest('details')
                            ?.setAttribute('open', '')
                        }
                        onChange={(event) =>
                          updateField(index, { key: event.target.value })
                        }
                      />
                      <span className="mt-1 block text-xs text-muted">
                        Generated for new fields. Keep this stable once forms
                        use these questions.
                      </span>
                    </label>
                    <label className="text-sm font-medium">
                      Reuse key (optional)
                      <input
                        maxLength={100}
                        pattern="[A-Za-z](?:[A-Za-z0-9_]|-)*"
                        className={fieldClass}
                        value={field.reuse_key ?? ''}
                        onInvalid={(event) =>
                          event.currentTarget
                            .closest('details')
                            ?.setAttribute('open', '')
                        }
                        onChange={(event) =>
                          updateField(index, { reuse_key: event.target.value })
                        }
                      />
                      <span className="mt-1 block text-xs text-muted">
                        Matches possible answers across forms; reuse always
                        needs fresh review.
                      </span>
                    </label>
                  </div>
                </details>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(event) =>
                        updateField(index, { required: event.target.checked })
                      }
                    />
                    Required
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" disabled={index === 0} aria-label={`Move field ${index + 1} up`} onClick={() => { const fields = [...draft.fields]; [fields[index - 1], fields[index]] = [fields[index], fields[index - 1]]; update({ fields }) }}>Move up</Button>
                    <Button size="sm" disabled={index === draft.fields.length - 1} aria-label={`Move field ${index + 1} down`} onClick={() => { const fields = [...draft.fields]; [fields[index + 1], fields[index]] = [fields[index], fields[index + 1]]; update({ fields }) }}>Move down</Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      update({
                        fields: draft.fields.filter((_, at) => at !== index),
                      })
                    }
                  >
                    Remove field
                  </Button></div>
                </div>
              </fieldset>
            ))}
            {error && (
              <p
                role="alert"
                className="rounded-lg bg-danger-soft p-3 text-sm text-danger"
              >
                {error}
              </p>
            )}
            {message && (
              <p role="status" className="text-sm text-success">
                {message}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              loading={busy}
              disabled={!draft.fields.length}
            >
              {embedded ? 'Save questions and use blank form' : selectedId ? 'Save blank form' : 'Create blank form'}
            </Button>
          </fieldset></form>
        </Card>
      ) : (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Template details</h2>
          {selected ? (
            <>
              <p className="mt-3 text-muted">
                {selected.description || 'No description'}
              </p>
              <p className="mt-3 text-sm">
                {selected.fields.length} fields ·{' '}
                {preparationLabel(selected.kind)}
              </p>
            </>
          ) : (
            <p className="mt-3 text-muted">
              Select a saved blank form to see its questions.
            </p>
          )}
        </Card>
      )}
    </div>
  )
}
