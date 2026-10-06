import { useEffect, useState } from 'react'
import api from '../../api/client'
import type { ReviewItemWithRequirement } from '../../types'
import { formatDate } from '../../utils/dateFormat'
import { buildReviewItemEvidencePreviewUrl, isImageEvidenceFilename } from '../../utils/reviewEvidence'
import type { ReviewDraft } from '../../hooks/review/useReviewItemDrafts'
import { useReviewEvidenceFiles } from '../../hooks/review/useReviewEvidenceFiles'

function EvidenceThumbnailImage(props: { previewUrl: string; alt: string }) {
  const { previewUrl, alt } = props
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    let isActive = true
    let nextBlobUrl: string | null = null
    const apiPrefix = `${import.meta.env.BASE_URL}api/v1`
    const apiPath = previewUrl.startsWith(apiPrefix)
      ? previewUrl.slice(apiPrefix.length)
      : previewUrl

    setBlobUrl(null)
    setLoadFailed(false)

    void api
      .get(apiPath, { responseType: 'blob' })
      .then((response) => {
        if (!isActive) return
        nextBlobUrl = window.URL.createObjectURL(response.data)
        setBlobUrl(nextBlobUrl)
      })
      .catch(() => {
        if (!isActive) return
        setLoadFailed(true)
      })

    return () => {
      isActive = false
      if (nextBlobUrl) {
        window.URL.revokeObjectURL(nextBlobUrl)
      }
    }
  }, [previewUrl])

  if (blobUrl) {
    return (
      <img
        src={blobUrl}
        alt={alt}
        loading="lazy"
        className="h-28 w-full object-cover"
      />
    )
  }

  return (
    <div className="flex h-28 w-full items-center justify-center bg-subtle text-[11px] text-muted">
      {loadFailed ? 'Preview unavailable' : 'Loading preview…'}
    </div>
  )
}

function EvidenceFiles({ item, cycleId, active, files }: { item: ReviewItemWithRequirement; cycleId: string; active: boolean; files: ReturnType<typeof useReviewEvidenceFiles> }) {
    const attachments = item.evidence_files || []
    const imageFiles = attachments.filter((file) => isImageEvidenceFilename(file.filename))
    const otherFiles = attachments.filter((file) => !isImageEvidenceFilename(file.filename))

    if (!imageFiles.length && !otherFiles.length) {
      return <p className="text-xs text-muted">No files uploaded.</p>
  }

    return (
      <div className="space-y-3">
        {imageFiles.length ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {imageFiles.map((file) => {
              const previewUrl = buildReviewItemEvidencePreviewUrl(cycleId, item.id, file.id)

              return (
                <div
                  key={file.id}
                  className="relative overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
                >
                  <a
                    href={previewUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="block bg-subtle"
                    aria-label={`Open preview for ${file.filename}`}
                  >
                    <EvidenceThumbnailImage previewUrl={previewUrl} alt={file.filename} />
                  </a>
                  <button
                    type="button"
                    onClick={() =>
                      files.deleteFile({
                        itemId: item.id,
                        fileId: file.id,
                      })
                    }
                    disabled={!active || files.deletingFileId === file.id}
                    aria-label={`Delete ${file.filename}`}
                    className="absolute right-2 top-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-surface/95 text-sm font-semibold text-ink shadow-sm ring-1 ring-line-strong transition hover:bg-surface hover:text-danger disabled:opacity-50"
                  >
                    ×
                  </button>
                  <div className="space-y-1 px-3 py-2 text-xs">
                    <div className="truncate font-medium text-ink">{file.filename}</div>
                    <div className="text-faint">
                      {formatDate(file.uploaded_at)}
                    </div>
                    <div className="flex items-center gap-3">
                      <a
                        href={previewUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-ink hover:text-ink"
                      >
                        Open
                      </a>
                      <button
                        type="button"
                        onClick={() => files.downloadFile(item.id, file.id, file.filename)}
                        className="text-ink hover:text-ink"
                      >
                        Download
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : null}
        {otherFiles.length ? (
          <div className="divide-y divide-line rounded-md border border-line bg-surface">
            {otherFiles.map((file) => (
              <div
                key={file.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs"
              >
                <div className="min-w-0">
                  <div className="break-all text-ink">{file.filename}</div>
                  <div className="text-faint">
                    {formatDate(file.uploaded_at)}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => files.downloadFile(item.id, file.id, file.filename)}
                    className="text-ink hover:text-ink"
                  >
                    Download
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      files.deleteFile({
                        itemId: item.id,
                        fileId: file.id,
                      })
                    }
                    disabled={!active || files.deletingFileId === file.id}
                    className="text-danger hover:text-danger disabled:opacity-50"
                  >
                    {files.deletingFileId === file.id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    )
  }

export default function ReviewEvidenceEditor({ item, cycleId, active, draft, changeEvidence, saveEvidence, files }: {
  item: ReviewItemWithRequirement
  cycleId: string
  active: boolean
  draft: ReviewDraft
  changeEvidence: (item: ReviewItemWithRequirement, value: string) => void
  saveEvidence: (item: ReviewItemWithRequirement) => void
  files: ReturnType<typeof useReviewEvidenceFiles>
}) {
  const uploadId = `evidence-upload-${item.id}`
  return (
    <div data-testid={`review-item-extra-fields-${item.id}`} className="review-evidence">
      <label className="review-field-label" htmlFor={`evidence-text-${item.id}`}>
        {draft.requirement_status === 'not_applicable' || item.requirement.requirement_type === 'not_applicable' ? 'Applicability rationale' : 'Evidence'}
      </label>
      <textarea
        id={`evidence-text-${item.id}`}
        disabled={!active}
        aria-label={`Evidence for ${item.requirement.reference_id}`}
        value={draft.review_evidence}
        onChange={(e) => changeEvidence(item, e.target.value)}
        onPaste={(event) => files.handlePaste(item.id, event)}
        onBlur={() => saveEvidence(item)}
        rows={3}
        className="review-evidence-text"
        placeholder="Add a reference, link or explanation…"
      />
      <div className="review-upload"
        tabIndex={active ? 0 : -1}
        aria-disabled={!active}
        onPaste={(event) => files.handlePaste(item.id, event)}
        data-testid={`evidence-paste-zone-${item.id}`}
        aria-label={`Paste screenshot for ${item.requirement.reference_id}`}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="review-upload-icon">
          <path strokeLinecap="round" strokeLinejoin="round" d="m8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l8-8m-5 12 8-8" />
        </svg>
        <div className="review-upload-copy">
          <span className="font-medium text-ink">Supporting files</span>
          <span>Choose files or click here to paste a screenshot.</span>
        </div>
        <label htmlFor={uploadId} className={`review-upload-button ${!active ? 'opacity-50' : ''}`}>Attach files</label>
        <input
          id={uploadId}
          type="file"
          aria-label={`Attach evidence for ${item.requirement.reference_id}`}
          disabled={!active}
          multiple
          onChange={(event) => {
            files.queueFiles(item.id, Array.from(event.target.files || []))
            event.currentTarget.value = ''
          }}
          className="review-upload-input"
        />
      </div>
      {files.uploadingCounts[item.id] ? <p role="status" className="text-xs text-muted">Uploading {files.uploadingCounts[item.id]}…</p> : null}
      <EvidenceFiles item={item} cycleId={cycleId} active={active} files={files} />
    </div>
  )
}
