import type { Dispatch, SetStateAction } from 'react'
import Badge from './ui/Badge'
import type { RegulatoryScope } from '../types/changeManagement'
export type ComponentDraft = {
  regulatory_scope: RegulatoryScope
  component_uid: string
  definition: string
  version: string
  identifying_characteristics: string
  change_owner_name: string
  confidentiality_code: number
  integrity_code: number
  availability_code: number
  accountability_code: number
  checksum_hash: string
  is_hardware: boolean
  geographic_location: string
  hosting_model: 'on_prem' | 'private_cloud' | 'public_cloud'
  virtualized: boolean
  public_cloud_provider: string
  public_cloud_certification: string | null
  public_cloud_independent: boolean
  public_cloud_redundancy: boolean
  status: 'active' | 'inactive' | 'retired'
}

export default function ComponentFields({ draft, setDraft, autoFocus = false }: { autoFocus?: boolean; draft: ComponentDraft; setDraft: Dispatch<SetStateAction<ComponentDraft>> }) {
  const classificationCode = Math.max(draft.confidentiality_code, draft.integrity_code, draft.availability_code, draft.accountability_code)
  return <>
    <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Regulatory scope *</span><select value={draft.regulatory_scope} onChange={event => setDraft(current => ({ ...current, regulatory_scope: event.target.value as RegulatoryScope }))} className="w-full rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm"><option value="unknown">Not assessed yet</option><option value="base_platform">Base platform</option><option value="rng">Random number generator (RNG)</option><option value="game">Game</option><option value="game_platform">Game platform</option><option value="other">Other component</option></select><span className="font-normal">This determines which certification checks apply. An unassessed scope cannot be used to bypass them.</span></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Component UID *</span><input autoFocus={autoFocus} aria-label="Component UID"
                    value={draft.component_uid}
                    onChange={(event) => setDraft((prev) => ({ ...prev, component_uid: event.target.value }))}
                    placeholder="Component UID"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                    required
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Version *</span><input aria-label="Version"
                    value={draft.version}
                    onChange={(event) => setDraft((prev) => ({ ...prev, version: event.target.value }))}
                    placeholder="Version"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                    required
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Definition *</span><textarea aria-label="Definition"
                    value={draft.definition}
                    onChange={(event) => setDraft((prev) => ({ ...prev, definition: event.target.value }))}
                    placeholder="Definition"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm "
                    required
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Identifying characteristics *</span><input aria-label="Identifying characteristics"
                    value={draft.identifying_characteristics}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, identifying_characteristics: event.target.value }))
                    }
                    placeholder="Identifying characteristics"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm "
                    required
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Change owner name</span><input aria-label="Change owner name"
                    value={draft.change_owner_name}
                    onChange={(event) => setDraft((prev) => ({ ...prev, change_owner_name: event.target.value }))}
                    placeholder="Change owner name"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Hosting model</span><select aria-label="Hosting model" value={draft.hosting_model}
                    onChange={(event) =>
                      setDraft((prev) => ({
                        ...prev,
                        hosting_model: event.target.value as ComponentDraft['hosting_model'],
                      }))
                    }
                    className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                  >
                    <option value="on_prem">On Prem</option>
                    <option value="private_cloud">Private Cloud</option>
                    <option value="public_cloud">Public Cloud</option>
                  </select></label>

                  <div className="md:col-span-2 flex items-center gap-2 text-xs">
                    <span className="font-semibold text-ink">CIAA Codes</span>
                    <button
                      type="button"
                      className="group relative inline-flex h-5 w-7 items-center justify-center rounded-full border border-line-strong text-[11px] font-semibold text-ink"
                      aria-label="CIAA code guide"
                    >
                      (i)
                      <span className="pointer-events-none absolute left-0 top-full z-20 mt-2 w-64 rounded-lg border border-line bg-surface p-2 text-left text-[11px] font-normal text-ink opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                        1 = no relevance, 2 = some relevance, 3 = substantial relevance. Final
                        classification is the highest CIAA code.
                      </span>
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-2 md:col-span-2 md:grid-cols-4">
                    {[
                      {
                        field: 'confidentiality_code',
                        label: 'C (Confidentiality)',
                        helper: 'Impact of unauthorized disclosure',
                      },
                      {
                        field: 'integrity_code',
                        label: 'I (Integrity)',
                        helper: 'Impact of unauthorized modification',
                      },
                      {
                        field: 'availability_code',
                        label: 'A (Availability)',
                        helper: 'Impact of outage/unavailability',
                      },
                      {
                        field: 'accountability_code',
                        label: 'Acc (Accountability)',
                        helper: 'Impact on traceability/non-repudiation',
                      },
                    ].map(({ field, label, helper }) => (
                      <label key={field} className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted">
                        <span>{label}</span>
                        <select
                          value={draft[field as keyof ComponentDraft] as number}
                          onChange={(event) =>
                            setDraft((prev) => ({
                              ...prev,
                              [field]: Number(event.target.value),
                            }))
                          }
                          className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        >
                          <option value={1}>1</option>
                          <option value={2}>2</option>
                          <option value={3}>3</option>
                        </select>
                        <p className="text-[11px] font-normal text-muted">{helper}</p>
                      </label>
                    ))}
                  </div>

                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Checksum/Hash</span><input aria-label="Checksum/Hash"
                    value={draft.checksum_hash}
                    onChange={(event) => setDraft((prev) => ({ ...prev, checksum_hash: event.target.value }))}
                    placeholder="Checksum/Hash"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                  /></label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Geographic location</span><input aria-label="Geographic location"
                    value={draft.geographic_location}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, geographic_location: event.target.value }))
                    }
                    placeholder="Geographic location"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                  /></label>

                  <div className="flex flex-wrap items-center gap-4 md:col-span-2">
                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={draft.is_hardware}
                        onChange={(event) =>
                          setDraft((prev) => ({ ...prev, is_hardware: event.target.checked }))
                        }
                      />
                      Hardware component
                    </label>

                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={draft.virtualized}
                        onChange={(event) => setDraft((prev) => ({ ...prev, virtualized: event.target.checked }))}
                      />
                      Virtualized
                    </label>

                    <Badge tone="blue">Classification preview: {classificationCode}</Badge>
                  </div>

                  {draft.hosting_model === 'public_cloud' && (
                    <div className="grid grid-cols-1 gap-3 rounded-xl border border-line bg-canvas/70 p-3 md:col-span-2 md:grid-cols-2">
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Public cloud provider</span><input aria-label="Public cloud provider"
                        value={draft.public_cloud_provider}
                        onChange={(event) =>
                          setDraft((prev) => ({ ...prev, public_cloud_provider: event.target.value }))
                        }
                        placeholder="Public cloud provider"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      /></label>
                      <div className="flex flex-wrap items-center gap-4 text-sm text-ink">
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted">
                          <span>Certification standard</span>
                          <input
                            type="text" maxLength={255}
                            className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                            aria-label="Cloud certification standard"
                            value={draft.public_cloud_certification || ''}
                            onChange={(event) =>
                              setDraft((prev) => ({ ...prev, public_cloud_certification: event.target.value }))
                            }
                          />
                        </label>
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={draft.public_cloud_independent}
                            onChange={(event) =>
                              setDraft((prev) => ({ ...prev, public_cloud_independent: event.target.checked }))
                            }
                          />
                          Independent checks
                        </label>
                        <label className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={draft.public_cloud_redundancy}
                            onChange={(event) =>
                              setDraft((prev) => ({ ...prev, public_cloud_redundancy: event.target.checked }))
                            }
                          />
                          Redundancy
                        </label>
                      </div>
                    </div>
                  )}

                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Component status</span><select aria-label="Component status" value={draft.status}
                    onChange={(event) =>
                      setDraft((prev) => ({
                        ...prev,
                        status: event.target.value as ComponentDraft['status'],
                      }))
                    }
                    className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                    <option value="retired">Retired</option>
                  </select></label>

  </>
}
