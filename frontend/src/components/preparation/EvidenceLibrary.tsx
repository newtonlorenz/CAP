import { visibilityLabels, type Visibility } from '../../types/access'
import AccessPanel from '../access/AccessPanel'
import { useRef, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getApiErrorMessage } from '../../api/errors'
import { preparationApi } from '../../api/preparation'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import {
  isEvidenceCurrent,
  type PreparationEvidence,
} from '../../types/preparation'
import Button from '../ui/Button'
import Card from '../ui/Card'

export function EvidenceLibrary({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [page, setPage] = useState(0)
  const [kind, setKind] = useState<'note' | 'link' | 'file'>('note')
  const [title, setTitle] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('secret')
  const [savedPreferences, setSavedPreferences] = useState<{ kind: typeof kind; visibility: Visibility }>({ kind: 'note', visibility: 'secret' })
  const [body, setBody] = useState('')
  const [linkUrl, setLinkUrl] = useState('')
  const [validFrom, setValidFrom] = useState('')
  const [validUntil, setValidUntil] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [actionId, setActionId] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const hasEvidenceDraft = Boolean(title.trim() || body.trim() || linkUrl.trim() ||
    validFrom || validUntil || file || kind !== savedPreferences.kind || visibility !== savedPreferences.visibility)
  useDraftNavigationGuard(busy || (canEdit && hasEvidenceDraft))
  const lock = useRef(false)
  const params = new URLSearchParams({
    skip: String(page * 100),
    limit: '100',
    include_archived: String(includeArchived),
  })
  if (search.trim()) params.set('q', search.trim())
  const evidence = useQuery({
    queryKey: ['preparation', 'evidence', search, includeArchived, page],
    queryFn: () => preparationApi.evidence(params),
  })
  const invalidate = () => {
    void queryClient.invalidateQueries({
      queryKey: ['preparation', 'evidence'],
    })
  }
  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (lock.current) return
    if (validFrom && validUntil && validUntil < validFrom) {
      setError('Valid until must be on or after valid from.')
      return
    }
    if (kind === 'file' && !file) {
      setError('Choose a file to upload.')
      return
    }
    lock.current = true
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const dates = {
        ...(validFrom ? { valid_from: validFrom } : {}),
        ...(validUntil ? { valid_until: validUntil } : {}),
      }
      if (kind === 'file' && file) {
        const form = new FormData()
        form.append('file', file)
        form.append('title', title.trim())
        form.append('visibility', visibility)
        if (body.trim()) form.append('body', body.trim())
        if (validFrom) form.append('valid_from', validFrom)
        if (validUntil) form.append('valid_until', validUntil)
        await preparationApi.uploadEvidence(form)
      } else if (kind === 'note') {
        await preparationApi.createEvidence({
          visibility,
          title: title.trim(),
          kind,
          body: body.trim(),
          ...dates,
        })
      } else {
        await preparationApi.createEvidence({
          visibility,
          title: title.trim(),
          kind: 'link',
          link_url: linkUrl.trim(),
          ...(body.trim() ? { body: body.trim() } : {}),
          ...dates,
        })
      }
      setEditorOpen(false)
      setTitle('')
      setBody('')
      setLinkUrl('')
      setFile(null)
      if (fileInput.current) fileInput.current.value = ''
      setValidFrom('')
      setValidUntil('')
      setSavedPreferences({ kind, visibility })
      setMessage('Evidence added with the selected visibility.')
      setPage(0)
      invalidate()
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          'Evidence could not be added. Check the details and try again.',
        ),
      )
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  const action = async (id: string, callback: () => Promise<unknown>) => {
    if (lock.current) return
    lock.current = true
    setActionId(id)
    setError('')
    try {
      await callback()
      invalidate()
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, 'The evidence action failed. Try again.'),
      )
    } finally {
      lock.current = false
      setActionId('')
    }
  }
  return (
    <div className="space-y-6">
      <Card hidden={editorOpen} className="p-5 sm:p-7">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Shared evidence library</h2>
            <p className="mt-1 text-sm text-muted">
              Files, notes and links can support cases in any jurisdiction.
            </p>
          </div>
          {canEdit && <Button variant="primary" onClick={() => setEditorOpen(true)}>{hasEvidenceDraft ? 'Resume evidence draft' : 'Add evidence'}</Button>}
          <label className="text-sm font-medium">
            Search evidence
            <input
              type="search"
              className="mt-1 block w-full px-3 py-2"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(0)
              }}
            />
          </label>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => {
              setIncludeArchived(event.target.checked)
              setPage(0)
            }}
          />
          Show archived evidence
        </label>
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger"
          >
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="mt-3 text-sm text-success">
            {message}
          </p>
        )}
        {evidence.isLoading ? (
          <p role="status" className="mt-6 text-muted">
            Loading evidence…
          </p>
        ) : evidence.isError ? (
          <p role="alert" className="mt-6 text-danger">
            Evidence could not be loaded.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => void evidence.refetch()}
            >
              Retry
            </button>
          </p>
        ) : !evidence.data?.items.length ? (
          <p className="mt-6 text-muted">{search.trim() ? 'No evidence matches your search. Try a different title.' : includeArchived ? 'No evidence has been added yet.' : 'No active evidence yet. Add a file, note or link, or show archived evidence.'}</p>
        ) : (
          <ul className="mt-6 divide-y divide-line">
            {evidence.data.items.map((item) => (
              <EvidenceRow
                key={item.id}
                item={item}
                canEdit={item.access ? canEdit && item.access.permissions.includes('edit') : canEdit}
                busy={Boolean(actionId)}
                onArchive={() =>
                  void action(item.id, () =>
                    preparationApi.archiveEvidence(item.id, !item.archived),
                  )
                }
                onDownload={() =>
                  void action(item.id, () =>
                    preparationApi.download(
                      `evidence/${item.id}/download`,
                      item.filename || item.title,
                    ),
                  )
                }
              />
            ))}
          </ul>
        )}
        {evidence.data && evidence.data.total > 100 && (
          <div className="mt-5 flex items-center gap-3">
            <Button
              size="sm"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <span className="text-sm text-muted">
              Page {page + 1} of {Math.ceil(evidence.data.total / 100)}
            </span>
            <Button
              size="sm"
              disabled={(page + 1) * 100 >= evidence.data.total}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </Card>
      {canEdit && (
        <Card hidden={!editorOpen} className="max-w-3xl p-5 sm:p-7">
          <Button className="mb-4" disabled={busy} onClick={() => setEditorOpen(false)}>Back to evidence{hasEvidenceDraft ? ' · Draft kept' : ''}</Button>
          <h2 className="text-lg font-semibold">Add evidence</h2>
          <form className="mt-5" onSubmit={create}>
            {error && <p role="alert" className="mb-4 text-danger">{error}</p>}
            <fieldset disabled={busy} className="space-y-4">
            <label className="block text-sm font-medium">Visibility<select className="mt-1 block w-full rounded-lg border border-line bg-surface p-2" value={visibility} onChange={(e) => setVisibility(e.target.value as Visibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className="text-xs text-muted">Highly confidential evidence stays private until explicitly shared.</span></label>
              <label className="block text-sm font-medium">
              Type
              <select
                className="mt-1 w-full px-3 py-2"
                value={kind}
                onChange={(event) => setKind(event.target.value as typeof kind)}
              >
                <option value="note">Note</option>
                <option value="link">Link</option>
                <option value="file">File upload</option>
              </select>
            </label>
            <label className="block text-sm font-medium">
              Title
              <input
                required
                maxLength={255}
                className="mt-1 w-full px-3 py-2"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            {kind === 'link' && (
              <label className="block text-sm font-medium">
                Link URL
                <input
                  required
                  type="url"
                  pattern="https?://.+"
                  placeholder="https://…"
                  className="mt-1 w-full px-3 py-2"
                  value={linkUrl}
                  onChange={(event) => setLinkUrl(event.target.value)}
                />
              </label>
            )}
            {kind === 'file' && (
              <label className="block text-sm font-medium">
                File
                <input
                  required
                  type="file"
                  ref={fileInput}
                  className="mt-1 block w-full"
                  onChange={(event) => setFile(event.target.files?.[0] || null)}
                />
              </label>
            )}
            <label className="block text-sm font-medium">
              {kind === 'note' ? 'Note' : 'Description (optional)'}
              <textarea
                required={kind === 'note'}
                rows={4}
                className="mt-1 w-full px-3 py-2"
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm font-medium">
                Valid from
                <input
                  type="date"
                  className="mt-1 w-full px-3 py-2"
                  value={validFrom}
                  onChange={(event) => setValidFrom(event.target.value)}
                />
              </label>
              <label className="block text-sm font-medium">
                Valid until
                <input
                  type="date"
                  className="mt-1 w-full px-3 py-2"
                  value={validUntil}
                  onChange={(event) => setValidUntil(event.target.value)}
                />
              </label>
            </div>
            <Button type="submit" variant="primary" loading={busy}>
              {kind === 'file' ? 'Upload file' : 'Add evidence'}
            </Button>
            </fieldset>
          </form>
        </Card>
      )}
    </div>
  )
}

function EvidenceRow({
  item,
  canEdit,
  busy,
  onArchive,
  onDownload,
}: {
  item: PreparationEvidence
  canEdit: boolean
  busy: boolean
  onArchive: () => void
  onDownload: () => void
}) {
  return (
    <li className="py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold break-words">{item.title}</p>
          <p className="mt-1 text-xs text-muted">
            {item.kind.toUpperCase()}
            {item.filename ? ` · ${item.filename}` : ''}
            {item.size_bytes !== null
              ? ` · ${(item.size_bytes / 1024).toFixed(1)} KB`
              : ''}{' '}
            · Added {item.created_at.slice(0, 10)}
          </p>
          <p className="mt-1 text-xs text-muted">
            {item.valid_from ? `Valid from ${item.valid_from} · ` : ''}
            {item.valid_until ? `Valid until ${item.valid_until} · ` : ''}
            {item.archived
              ? 'Archived'
              : isEvidenceCurrent(item)
                ? 'Current'
                : 'Outside validity dates'}
          </p>
          {item.body && (
            <p className="mt-2 max-w-prose whitespace-pre-wrap text-sm text-muted">
              {item.body}
            </p>
          )}
          {item.kind === 'link' && item.link_url && (
            <a
              href={item.link_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block break-all text-sm text-accent underline"
            >
              Open link
            </a>
          )}
        </div>
        <div className="flex gap-2">
          {item.kind === 'file' && (
            <Button size="sm" disabled={busy || Boolean(item.access && !item.access.permissions.includes('export'))} onClick={onDownload}>
              Download
            </Button>
          )}
          {canEdit && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={onArchive}
            >
              {item.archived ? 'Restore' : 'Archive'}
            </Button>
          )}
        </div>
      </div>
      {item.access?.permissions.includes('manage_access') && <AccessPanel type="preparation_evidence" id={item.id} />}
    </li>
  )
}
