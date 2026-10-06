import { Link } from 'react-router-dom'
import { useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { accessApi } from '../../api/access'
import api from '../../api/client'
import { useAuth } from '../../contexts/AuthContext'
import { getApiErrorMessage } from '../../api/errors'
import type { PaginatedResponse, UserMention } from '../../types'
import { permissionDescriptions, permissionLabels, visibilityLabels, type AccessPolicy, type Permission, type ResourceType, type Visibility } from '../../types/access'
import Button from '../ui/Button'
import Tooltip from '../ui/Tooltip'
import { Field, inputClass } from '../applications/Fields'

export default function AccessPanel({ type, id, initialOpen = false }: { type: ResourceType; id: string; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen)
  const panelId = useId()
  const policy = useQuery({ queryKey: ['access', type, id], queryFn: () => accessApi.get(type, id), enabled: open, staleTime: 0 })
  return <section className="rounded-xl border border-line p-4"><Button size="sm" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>{open ? 'Hide access settings' : 'Who can access this?'}</Button>{open && <div id={panelId} className="mt-4 space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Visibility and access</h3><Link to="/access-teams" className="text-sm font-semibold text-accent underline">Manage teams</Link></div><p className="text-sm text-muted">Choose people or teams, select their permissions and save an access change with a reason. The access owner controls sharing; assigning a work owner or account administrator does not grant content access.</p>{policy.isLoading ? <p role="status">Loading access…</p> : policy.isError ? <p role="alert">Access settings are unavailable. <Button onClick={() => void policy.refetch()}>Retry</Button></p> : policy.data && <PolicyEditor key={`${type}-${id}-${policy.data.revision}`} policy={policy.data} />}</div>}</section>
}
function PolicyEditor({ policy }: { policy: AccessPolicy }) {
  const { user } = useAuth()
  const [visibility, setVisibility] = useState(policy.visibility)
  const [grants, setGrants] = useState(policy.grants)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const canManage = policy.effective_permissions.includes('manage_access')
  const users = useQuery({ queryKey: ['access', 'users'], queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data })
  const teams = useQuery({ queryKey: ['access', 'teams'], queryFn: accessApi.teams })
  const save = async () => {
    setBusy(true); setError('')
    try {
      await accessApi.update(policy.resource_type, policy.resource_id, { expected_revision: policy.revision, visibility, grants, reason: reason.trim() })
      // A fresh document discards query caches and unsaved resource state after any access change.
      window.location.reload()
    } catch (caught) { setError(getApiErrorMessage(caught, 'Access could not be saved. Reload to check for changes.')); setBusy(false) }
  }
  return <div className="space-y-4"><p className="text-sm">Access owner: {users.data?.items.find((u) => u.id === policy.owner_id)?.full_name || policy.owner_id}. This is independent of the assigned work owner.</p>{policy.parent_id && <p className="text-sm text-muted">Parent access also applies. These settings can further restrict inherited access.</p>}<fieldset disabled={!canManage || busy} className="space-y-4"><Field label="Visibility"><select className={inputClass} value={visibility} onChange={(e) => setVisibility(e.target.value as Visibility)}>{Object.entries(visibilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field><p className="text-sm text-muted">Highly confidential work is hidden from people without explicit access. Highly confidential access is granted to named people only; choose Restricted to share with teams. Share summary access only when its name and status may be disclosed. Editing, approval, export and access management are separate choices; editing, approval and export also require View details.</p>{grants.map((grant, index) => <div key={index} className="space-y-3 rounded-lg border border-line p-3"><div className="flex flex-wrap gap-3"><Field label={`Recipient type ${index + 1}`}><select className={inputClass} value={grant.subject_type} onChange={(e) => setGrants(grants.map((g, i) => i === index ? { ...g, subject_type: e.target.value as 'user' | 'team', subject_id: '' } : g))}><option value="user">Person</option><option value="team" disabled={visibility === 'secret'}>Team</option></select></Field><Field label={`Recipient ${index + 1}`}><select required className={inputClass} value={grant.subject_id} onChange={(e) => setGrants(grants.map((g, i) => i === index ? { ...g, subject_id: e.target.value } : g))}><option value="">Select recipient</option>{grant.subject_type === 'user' ? users.data?.items.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>) : teams.data?.filter((team) => team.owner_id === user?.id).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field><Button onClick={() => setGrants(grants.filter((_, i) => i !== index))}>Remove recipient {index + 1}</Button></div><div className="flex flex-wrap gap-4">{(Object.keys(permissionLabels) as Permission[]).filter((p) => p !== 'summary' || policy.resource_type === 'application').map((permission) => <label key={permission} className="flex items-center gap-2 text-sm"><Tooltip content={permissionDescriptions[permission]}><input type="checkbox" checked={grant.permissions.includes(permission)} onChange={(e) => setGrants(grants.map((g, i) => i === index ? { ...g, permissions: e.target.checked ? [...g.permissions, permission] : g.permissions.filter((p) => p !== permission) } : g))} /></Tooltip>{permissionLabels[permission]}</label>)}</div></div>)}{visibility === 'secret' && grants.some((g) => g.subject_type === 'team') && <p role="alert" className="text-warning">Remove team grants or choose Restricted before saving.</p>}{canManage && <><Button onClick={() => setGrants([...grants, { subject_type: 'user', subject_id: '', permissions: policy.resource_type === 'application' ? ['summary', 'view'] : ['view'] }])}>{visibility === 'secret' ? 'Add person' : 'Add person or team'}</Button><Field label="Reason for access change"><textarea required className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} /></Field><Button variant="primary" disabled={!reason.trim() || grants.some((g) => !g.subject_id || !g.permissions.length || (visibility === 'secret' && g.subject_type === 'team'))} onClick={() => void save()}>Save access</Button></>}</fieldset>{error && <p role="alert" className="text-danger">{error}</p>}</div>
}
