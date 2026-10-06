import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getApiErrorMessage } from '../../api/errors'
import { preparationApi } from '../../api/preparation'
import { isEvidenceCurrent } from '../../types/preparation'
import Button from '../ui/Button'

/** Selected IDs are resolved individually, so archived and paginated-out evidence stays visible. */
export default function EvidenceAttachments({
  ids,
  onChange,
  disabled = false,
}: {
  ids: string[]
  onChange?: (ids: string[]) => void
  disabled?: boolean
}) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [search, setSearch] = useState('')
  const editable = Boolean(onChange)
  const matches = useQuery({
    queryKey: ['preparation', 'evidence', 'picker', search],
    queryFn: () => {
      const params = new URLSearchParams({ limit: '100' })
      if (search.trim()) params.set('q', search.trim())
      return preparationApi.evidence(params)
    },
    enabled: editable && pickerOpen,
  })
  const choices =
    matches.data?.items.filter((item) => !ids.includes(item.id)) ?? []

  return (
    <section aria-label="Attached evidence" className="max-w-2xl space-y-3">
      <h5 className="text-sm font-semibold">
        Attached evidence ({ids.length})
      </h5>
      {ids.length ? (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface px-3">
          {ids.map((id) => (
            <SelectedEvidence
              key={id}
              id={id}
              disabled={disabled}
              onRemove={
                onChange
                  ? () => onChange(ids.filter((selected) => selected !== id))
                  : undefined
              }
            />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">No evidence attached.</p>
      )}
      {editable && (
        <div>
          <Button
            size="sm"
            disabled={disabled}
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen(!pickerOpen)}
          >
            {pickerOpen ? 'Close evidence picker' : 'Add evidence'}
          </Button>
          {pickerOpen && (
            <div className="mt-3 rounded-xl bg-subtle p-4">
              <label className="block text-sm font-medium">
                Search shared evidence
                <input
                  type="search"
                  className="mt-1 w-full px-3 py-2"
                  value={search}
                  disabled={disabled}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              {matches.isLoading ? (
                <p role="status" className="mt-3 text-sm text-muted">
                  Loading evidence…
                </p>
              ) : matches.isError ? (
                <p role="alert" className="mt-3 text-sm text-danger">
                  Evidence search failed.{' '}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void matches.refetch()}
                  >
                    Retry
                  </button>
                </p>
              ) : choices.length ? (
                <ul className="mt-3 max-h-56 divide-y divide-line overflow-auto">
                  {choices.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-start justify-between gap-3 py-2 text-sm"
                    >
                      <div className="min-w-0">
                        <p className="break-words font-medium">{item.title}</p>
                        <p className="text-xs text-muted">
                          {item.kind} ·{' '}
                          {item.archived
                            ? 'Archived'
                            : isEvidenceCurrent(item)
                              ? 'Current'
                              : 'Outside validity dates'}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        disabled={disabled}
                        onClick={() => onChange?.([...ids, item.id])}
                        aria-label={`Attach ${item.title}`}
                      >
                        Add
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-muted">
                  No other evidence matches. Create or upload it in the evidence library.
                </p>
              )}
              <a href={`${import.meta.env.BASE_URL}licence-applications?tab=evidence`} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex min-h-11 items-center text-sm font-semibold text-accent underline">Open evidence library in a new tab</a>
              <p className="text-xs text-muted">Your form stays open. Return here after adding evidence, then search for it.</p>
              {matches.data && matches.data.total > 100 && (
                <p className="mt-2 text-xs text-muted">
                  Showing the first 100 matches. Narrow the search to find more.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function SelectedEvidence({
  id,
  disabled,
  onRemove,
}: {
  id: string
  disabled: boolean
  onRemove?: () => void
}) {
  const item = useQuery({
    queryKey: ['preparation', 'evidence', 'item', id],
    queryFn: () => preparationApi.getEvidence(id),
  })
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const evidence = item.data
  const safeLink =
    evidence?.link_url && /^https?:\/\//i.test(evidence.link_url)
      ? evidence.link_url
      : null
  const download = async () => {
    if (!evidence) return
    setDownloadBusy(true)
    setDownloadError('')
    try {
      await preparationApi.download(
        `evidence/${id}/download`,
        evidence.filename || evidence.title,
      )
    } catch (caught) {
      setDownloadError(
        getApiErrorMessage(caught, 'Evidence download failed. Try again.'),
      )
    } finally {
      setDownloadBusy(false)
    }
  }

  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {item.isLoading ? (
            <p role="status" className="text-muted">
              Loading evidence…
            </p>
          ) : item.isError ? (
            <p className="text-warning">
              Evidence {id} could not be loaded.{' '}
              <button
                type="button"
                className="underline"
                onClick={() => void item.refetch()}
              >
                Retry
              </button>
            </p>
          ) : evidence ? (
            <>
              <p className="break-words font-semibold">{evidence.title}</p>
              <p className="mt-1 text-xs text-muted">
                {evidence.kind}
                {evidence.filename ? ` · ${evidence.filename}` : ''} ·{' '}
                {evidence.archived
                  ? 'Archived'
                  : isEvidenceCurrent(evidence)
                    ? 'Current'
                    : 'Outside validity dates'}
                {evidence.valid_from
                  ? ` · Valid from ${evidence.valid_from}`
                  : ''}
                {evidence.valid_until
                  ? ` · Valid until ${evidence.valid_until}`
                  : ''}
              </p>
            </>
          ) : null}
        </div>
        <div className="flex gap-2">
          {evidence?.kind === 'file' && (
            <Button
              size="sm"
              disabled={disabled}
              loading={downloadBusy}
              onClick={() => void download()}
            >
              Download
            </Button>
          )}
          {onRemove && (
            <Button
              size="sm"
              variant="ghost"
              disabled={disabled}
              onClick={onRemove}
              aria-label={`Remove ${evidence?.title || id}`}
            >
              Remove
            </Button>
          )}
        </div>
      </div>
      {evidence?.body && (
        <details className="mt-2">
          <summary className="text-accent underline">
            View note or description
          </summary>
          <p className="mt-2 max-w-prose whitespace-pre-wrap break-words text-muted">
            {evidence.body}
          </p>
        </details>
      )}
      {safeLink && (
        <a
          className="mt-2 inline-block break-all text-accent underline"
          href={safeLink}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open evidence link
        </a>
      )}
      {downloadError && (
        <p role="alert" className="mt-2 text-danger">
          {downloadError}
        </p>
      )}
    </li>
  )
}
