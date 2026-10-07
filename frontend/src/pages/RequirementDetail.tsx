import './workflow-pages.css'
import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import type { RequirementWithStatus } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import LoadError from '../components/ui/LoadError'
import DraftSaveStatus from '../components/ui/DraftSaveStatus'
import CopyButton from '../components/ui/CopyButton'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import { useSourceDrafts } from '../hooks/source/useSourceDrafts'
import RichTextEditor from '../components/RichTextEditor'
import { normalizeRichText, stripHtml } from '../utils/richText'

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  return <RequirementContent key={id} id={id} />
}

function RequirementContent({ id }: { id: string | undefined }) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()

  const { data: requirement, isLoading, isError, refetch } = useQuery({
    queryKey: ['requirement', id],
    queryFn: async () => {
      const response = await api.get<RequirementWithStatus>(`/requirements/${id}`)
      return response.data
    },
  })

  const initialDraft = {
    reference_id: requirement?.reference_id || '',
    title: requirement?.title || '',
    text: requirement?.text || '',
    requirement_type: requirement?.requirement_type || '',
  }
  const autosave = useSourceDrafts({
    scopeId: id,
    originals: requirement && id ? { [id]: initialDraft } : {},
    normalise: (draft: typeof initialDraft) => ({ ...draft, reference_id: draft.reference_id.trim(), title: draft.title.trim(), text: normalizeRichText(draft.text) }),
    validate: (draft) => !draft.reference_id ? 'Enter a reference, then retry saving.' : undefined,
    persist: async (requirementId, draft) => {
      await api.put(`/requirements/${requirementId}`, { ...draft, title: draft.title || null, requirement_type: draft.requirement_type || null })
      await queryClient.invalidateQueries({ queryKey: ['requirement', requirementId] })
      void queryClient.invalidateQueries({ queryKey: ['requirements'] })
    },
  })
  useDraftNavigationGuard(autosave.hasUnsavedChanges)
  const editForm = (id && autosave.drafts[id]) || initialDraft
  const updateForm = (patch: Partial<typeof initialDraft>) => {
    if (id && user?.role === 'admin') autosave.update(id, patch)
  }
  const handleAutoSave = () => {
    if (id && user?.role === 'admin') void autosave.save(id)
  }

  useEffect(() => {
    if (!requirement?.jurisdiction_id) return
    if (jurisdictionId && requirement.jurisdiction_id !== jurisdictionId) {
      setJurisdictionId(requirement.jurisdiction_id)
    }
  }, [requirement?.jurisdiction_id, jurisdictionId, setJurisdictionId])

  if (isError) return <LoadError subject="This requirement" onRetry={() => refetch()} />

  if (isLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!requirement) {
    return <div className="text-center py-8">Requirement not found</div>
  }

  return (
    <div className="workflow-page requirement-detail-page min-w-0">
      <Link to={`/requirements/sets/${requirement.document_id}`} className="mb-4 inline-flex text-sm text-accent hover:underline">← Back to requirement set</Link>
      <section data-tour="requirement-wording" className="requirement-reading-surface mb-6" aria-label="Requirement wording">
        <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold text-ink">{requirement.reference_id}</h1><CopyButton value={`${editForm.reference_id}\n${stripHtml(editForm.text)}`} label="Copy requirement" /></div>
        <div className="mt-1 text-sm text-muted">
          Jurisdiction:{' '}
          {jurisdictionById[requirement.jurisdiction_id]?.name || requirement.jurisdiction_id}
        </div>
        {requirement.title &&
          requirement.title !== stripHtml(requirement.text || '') && (
          <p className="mt-1 font-medium text-ink">{requirement.title}</p>
        )}
        <div
          className="mt-2 space-y-2 break-words leading-relaxed text-ink [&_li]:mb-1 [&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6"
          dangerouslySetInnerHTML={{ __html: normalizeRichText(requirement.text) }}
        />
      </section>

      <div className="requirement-detail-grid space-y-6">
        <div className="app-surface app-surface-default rounded-2xl p-6">
          <h2 className="mb-4 text-lg font-semibold">Source details</h2>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-muted">Type</dt>
              <dd className="text-sm text-ink">{requirement.requirement_type}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-muted">Version</dt>
              <dd className="text-sm text-ink">{requirement.version}</dd>
            </div>
          </dl>
        </div>

        <div className="app-surface app-surface-default rounded-2xl p-6">
          <h2 className="text-lg font-semibold">Edit Requirement</h2>
          <p className="mb-4 mt-1 text-sm text-muted">Drafts save automatically. Submit and approve the requirement set separately.</p>
          {user?.role === 'admin' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleAutoSave()
              }}
              className="space-y-4"
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Reference ID
                  </label>
                  <input
                    type="text"
                    aria-label="Reference ID"
                    value={editForm.reference_id}
                    onChange={(e) => updateForm({ reference_id: e.target.value })}
                    onBlur={() => handleAutoSave()}
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Title
                  </label>
                  <input
                    type="text"
                    aria-label="Title"
                    value={editForm.title}
                    onChange={(e) => updateForm({ title: e.target.value })}
                    onBlur={() => handleAutoSave()}
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-ink">
                    Requirement Type
                  </label>
                  <select
                    aria-label="Requirement Type"
                    value={editForm.requirement_type}
                    onChange={(e) => updateForm({ requirement_type: e.target.value })}
                    onBlur={() => handleAutoSave()}
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2"
                  >
                    <option value="mandatory">Mandatory</option>
                    <option value="recommended">Recommended</option>
                    <option value="informational">Informational</option>
                    <option value="not_applicable">Not Applicable</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-ink">
                  Requirement Text
                </label>
                <RichTextEditor
                  ariaLabel="Requirement Text"
                  value={editForm.text}
                  onChange={(value) => updateForm({ text: value })}
                  onBlur={handleAutoSave}
                  className="shadow-sm"
                  editorClassName="min-h-[140px] text-base"
                />
              </div>
              {id && <DraftSaveStatus state={autosave.state(id)} message={autosave.error(id)} onRetry={() => { void autosave.save(id, true) }} />}
            </form>
          ) : (
            <p className="text-sm text-muted">Editing is restricted to admins.</p>
          )}
        </div>
      </div>
    </div>
  )
}
