import './workflow-pages.css'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { applicationsApi } from '../api/applications'
import { formatDate } from '../utils/dateFormat'
import type { Jurisdiction, PaginatedResponse } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { notifyApiError } from '../utils/notify'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import LoadError from '../components/ui/LoadError'
import Card from '../components/ui/Card'
import DropdownMenu from '../components/ui/DropdownMenu'
import Modal from '../components/ui/Modal'
import { Table, TBody, TD, TH, THead, TR, TableEmpty } from '../components/ui/Table'

type JurisdictionPayload = {
  code: string
  name: string
  regulator_name?: string | null
  report_header_text?: string | null
  active?: boolean
}

const normalizeOptionalText = (value: FormDataEntryValue | null) => {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

export default function Jurisdictions() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { setJurisdictionId } = useJurisdiction()
  const canManageMarketSetup = user?.role === 'admin' || user?.role === 'manager'
  const canManageSharedJurisdictions = user?.role === 'admin' && user.installation_operator === true
  const queryClient = useQueryClient()
  const toast = useToast()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingJurisdiction, setEditingJurisdiction] = useState<Jurisdiction | null>(null)
  const [search, setSearch] = useState('')

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['jurisdictions', canManageSharedJurisdictions ? 'all' : 'active'],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      if (canManageSharedJurisdictions) {
        params.set('include_inactive', 'true')
      }
      const response = await api.get<PaginatedResponse<Jurisdiction>>(
        `/jurisdictions?${params.toString()}`
      )
      return response.data
    },
  })

  const jurisdictions = useMemo(() => {
    const list = data?.items ?? []
    const q = search.trim().toLowerCase()
    if (!q) return list
    return list.filter((j) => {
      const hay = `${j.code} ${j.name} ${j.regulator_name || ''}`.toLowerCase()
      return hay.includes(q)
    })
  }, [data?.items, search])

  const profiles = useQueries({ queries: jurisdictions.map((jurisdiction) => ({
    queryKey: ['applications', 'market-profile', jurisdiction.id],
    queryFn: () => applicationsApi.marketProfile(jurisdiction.id),
    enabled: jurisdiction.active,
    staleTime: 60_000,
    retry: false,
  })) })
  const profileSummary = (jurisdiction: Jurisdiction, index: number) => {
    if (!jurisdiction.active) return <span className="text-muted">Unavailable while inactive</span>
    const profile = profiles[index]
    if (profile?.isError) return <button className="text-accent underline" onClick={() => void profile.refetch()}>Retry checklist summary</button>
    if (!profile?.data?.status) return <span className="text-muted">Loading checklist…</span>
    return <div className="space-y-1"><span>{profile.data.status === 'published' ? 'Published checklist' : 'Draft checklist'}</span><p className="text-xs text-muted">{profile.data.checked_at ? `Sources checked ${formatDate(profile.data.checked_at)}` : 'Sources not checked'}</p></div>
  }

  const createMutation = useMutation({
    mutationFn: async (payload: JurisdictionPayload) => {
      await api.post('/jurisdictions', payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jurisdictions'] })
      setShowCreateModal(false)
      toast.success('Jurisdiction created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create jurisdiction')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({
      id,
      payload,
    }: {
      id: string
      payload: Partial<JurisdictionPayload>
    }) => {
      await api.put(`/jurisdictions/${id}`, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jurisdictions'] })
      setEditingJurisdiction(null)
      toast.success('Jurisdiction updated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update jurisdiction')
    },
  })

  const handleCreate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const rawCode = (formData.get('code') as string) || ''
    const payload: JurisdictionPayload = {
      code: rawCode.trim().toLowerCase(),
      name: ((formData.get('name') as string) || '').trim(),
      regulator_name: normalizeOptionalText(formData.get('regulator_name')),
      report_header_text: normalizeOptionalText(formData.get('report_header_text')),
      active: formData.get('active') === 'on',
    }
    if (!payload.code || !payload.name) {
      toast.error('Code and name are required.')
      return
    }
    createMutation.mutate(payload)
  }

  const handleUpdate = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!editingJurisdiction) return
    const formData = new FormData(e.currentTarget)
    const payload: Partial<JurisdictionPayload> = {
      name: ((formData.get('name') as string) || '').trim(),
      regulator_name: normalizeOptionalText(formData.get('regulator_name')),
      report_header_text: normalizeOptionalText(formData.get('report_header_text')),
      active: formData.get('active') === 'on',
    }
    if (!payload.name) {
      toast.error('Name is required.')
      return
    }
    updateMutation.mutate({ id: editingJurisdiction.id, payload })
  }

  const marketSetupAction = (j: Jurisdiction) => canManageMarketSetup && j.active ? (
    <button type="button" onClick={() => { setJurisdictionId(j.id); navigate('/market-setup') }} className="text-sm text-accent underline" aria-label={`Market setup for ${j.name}`}>
      Market setup
    </button>
  ) : null

  const renderActions = (j: Jurisdiction) => {
    if (!canManageSharedJurisdictions) return null
    return (
      <DropdownMenu
        ariaLabel={`Actions for ${j.name}`}
        disabled={updateMutation.isPending}
        items={[
          { key: 'edit', label: 'Edit', onSelect: () => setEditingJurisdiction(j) },
          {
            key: 'toggle',
            label: j.active ? 'Deactivate' : 'Activate',
            onSelect: () => updateMutation.mutate({ id: j.id, payload: { active: !j.active } }),
          },
        ]}
      />
    )
  }

  return (
    <div data-tour="jurisdictions-page" className="workflow-page jurisdictions-page min-w-0 space-y-4">
      <header className="py-1">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-ink">Jurisdictions</h1>
            <p className="mt-1 text-sm text-muted">
              Manage the authority, report header and availability for each jurisdiction. Licence checklist settings are in Market setup.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex flex-col gap-1">
              <label htmlFor="jurisdictions-field-1" className="text-xs font-medium uppercase tracking-wide text-muted">
                Search
              </label>
              <input id="jurisdictions-field-1"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Code, name, regulator..."
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none sm:w-64"
              />
            </div>
            {canManageSharedJurisdictions ? (
              <Button variant="primary" onClick={() => setShowCreateModal(true)} className="sm:mb-[2px]">
                Create jurisdiction
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      {isError ? <LoadError subject="Jurisdictions" onRetry={() => refetch()} /> : isLoading ? (
        <Card className="p-6 text-sm text-muted">Loading...</Card>
      ) : (
        <Card className="overflow-hidden"><div className="workflow-table-heading"><h2>Markets and authorities</h2><p>Open market setup to maintain a licence checklist.</p></div>
          <div className="hidden overflow-x-auto lg:block">
            <Table>
              <THead>
                <tr>
                  <TH>Code</TH>
                  <TH>Name</TH>
                  <TH>Authority</TH>
                  <TH>Status</TH>
                  <TH>Report header preview</TH>
                  <TH>Checklist</TH>
                  <TH className="w-[1%]">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {jurisdictions.map((j, index) => (
                  <TR key={j.id}>
                    <TD className="font-semibold text-ink">{j.code.toUpperCase()}</TD>
                    <TD className="text-ink">{j.name}</TD>
                    <TD className="text-muted">{j.regulator_name || '-'}</TD>
                    <TD>
                      <Badge tone={j.active ? 'green' : 'slate'}>{j.active ? 'active' : 'inactive'}</Badge>
                    </TD>
                    <TD className="text-muted">{j.report_header_text?.trim() || j.regulator_name?.trim() || j.name}</TD>
                    <TD>{profileSummary(j, index)}</TD>
                    <TD><div className="flex items-center justify-end gap-3 whitespace-nowrap">{marketSetupAction(j)}{renderActions(j)}</div></TD>
                  </TR>
                ))}
                {jurisdictions.length === 0 ? <TableEmpty colSpan={7}>No jurisdictions found.</TableEmpty> : null}
              </TBody>
            </Table>
          </div>

          <div className="divide-y divide-line lg:hidden">
            {jurisdictions.map((j, index) => (
              <div key={j.id} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-ink">{j.code.toUpperCase()}</span>
                      <span className="text-sm text-ink break-words">{j.name}</span>
                      <Badge tone={j.active ? 'green' : 'slate'}>{j.active ? 'active' : 'inactive'}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted break-words">
                      Authority: {j.regulator_name || '-'}
                    </div>
                    <div className="mt-2 text-xs text-muted break-words">Report header: {j.report_header_text?.trim() || j.regulator_name?.trim() || j.name}</div>
                    <div className="mt-2 text-sm">{profileSummary(j, index)}</div>
                    <div className="mt-3">{marketSetupAction(j)}</div>
                  </div>
                  <div className="shrink-0">{renderActions(j)}</div>
                </div>
              </div>
            ))}
            {jurisdictions.length === 0 ? (
              <div className="px-6 py-10 text-center text-sm text-muted">No jurisdictions found.</div>
            ) : null}
          </div>
        </Card>
      )}

      <Modal
        open={showCreateModal && canManageSharedJurisdictions}
        title="Create jurisdiction"
        onClose={() => setShowCreateModal(false)}
        size="lg"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="jurisdictions-field-2" className="mb-1 block text-sm font-medium text-ink">Code</label>
              <input id="jurisdictions-field-2"
                type="text"
                name="code"
                placeholder="area-1"
                required
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
              <p className="mt-1 text-xs text-muted">
                Lowercase slug (e.g. <span className="font-mono">dk</span>, <span className="font-mono">uk</span>).
              </p>
            </div>
            <div>
              <label htmlFor="jurisdictions-field-3" className="mb-1 block text-sm font-medium text-ink">Name</label>
              <input id="jurisdictions-field-3"
                type="text"
                name="name"
                placeholder="Jurisdiction name"
                required
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label htmlFor="jurisdictions-field-4" className="mb-1 block text-sm font-medium text-ink">Authority or certification body</label>
            <input id="jurisdictions-field-4"
              type="text"
              name="regulator_name"
              placeholder="Authority or certification body"
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="jurisdictions-field-5" className="mb-1 block text-sm font-medium text-ink">Report header text</label>
            <textarea id="jurisdictions-field-5"
              name="report_header_text"
              rows={3}
              placeholder="Header text for exported PDFs"
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" aria-label="Active jurisdiction" name="active" defaultChecked />
            Active
          </label>

          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" loading={createMutation.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!editingJurisdiction && canManageSharedJurisdictions}
        title="Edit jurisdiction"
        onClose={() => setEditingJurisdiction(null)}
        size="lg"
      >
        {editingJurisdiction ? (
          <form onSubmit={handleUpdate} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-ink">Code</label>
                <input aria-label="Jurisdiction code" id="jurisdictions-field-6"
                  type="text"
                  value={editingJurisdiction.code}
                  disabled
                  className="w-full cursor-not-allowed rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
                />
                <p className="mt-1 text-xs text-muted">
                  The code is fixed here to keep jurisdiction references and built-in market profiles consistent.
                </p>
              </div>
              <div>
                <label htmlFor="jurisdictions-field-7" className="mb-1 block text-sm font-medium text-ink">Name</label>
                <input id="jurisdictions-field-7"
                  type="text"
                  name="name"
                  defaultValue={editingJurisdiction.name}
                  required
                  className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label htmlFor="jurisdictions-field-8" className="mb-1 block text-sm font-medium text-ink">Authority or certification body</label>
              <input id="jurisdictions-field-8"
                type="text"
                name="regulator_name"
                defaultValue={editingJurisdiction.regulator_name || ''}
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>

            <div>
              <label htmlFor="jurisdictions-field-9" className="mb-1 block text-sm font-medium text-ink">Report header text</label>
              <textarea id="jurisdictions-field-9"
                name="report_header_text"
                rows={3}
                defaultValue={editingJurisdiction.report_header_text || ''}
                className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink shadow-sm focus:border-line-strong focus:outline-none"
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" aria-label="Active jurisdiction" name="active" defaultChecked={editingJurisdiction.active} />
              Active
            </label>

            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={() => setEditingJurisdiction(null)}>
                Cancel
              </Button>
              <Button variant="primary" type="submit" loading={updateMutation.isPending}>
                Save
              </Button>
            </div>
          </form>
        ) : null}
      </Modal>
    </div>
  )
}
