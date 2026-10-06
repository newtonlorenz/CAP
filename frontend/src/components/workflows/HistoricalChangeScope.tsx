import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../api/client'
import type { ChangeEntry, ManagedComponent } from '../../types'
import type { RegulatoryScope, ResponsibilityRole } from '../../types/changeManagement'
import { getApiErrorMessage } from '../../api/errors'
import { useDraftNavigationGuard } from '../../hooks/useDraftNavigationGuard'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'

export default function HistoricalChangeScope({ change, components, responsibilityRole }: { change: ChangeEntry; components: ManagedComponent[]; responsibilityRole?: ResponsibilityRole }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [reference, setReference] = useState('')
  const [evidence, setEvidence] = useState('')
  const [role, setRole] = useState<ResponsibilityRole>(responsibilityRole || 'unknown')
  const [rows, setRows] = useState(() => change.components.map(link => {
    const current = components.find(item => item.id === link.component_id)
    return {component_id:link.component_id,component_uid:current?.component_uid || '', version:link.version_at_proposal || '',checksum_hash:'',planned_checksum_hash:link.planned_checksum_hash || '',implemented_checksum_hash:link.implemented_checksum_hash || '',regulatory_scope:'unknown' as RegulatoryScope,confidentiality_code:current?.confidentiality_code || 1,integrity_code:current?.integrity_code || 1,availability_code:current?.availability_code || 1,accountability_code:current?.accountability_code || 1}
  }))
  const initialRows = useRef(JSON.stringify(rows))
  const dirty = Boolean(reference || evidence || JSON.stringify(rows) !== initialRows.current || role !== (responsibilityRole || 'unknown'))
  const save = useMutation({mutationFn: () => api.post(`/change-management/changes/${change.id}/historical-scope-attestation`,{evidence_reference:reference,evidence,responsibility_role:role,components:rows}),onSuccess: () => {setReference('');setEvidence('');setOpen(false);void client.invalidateQueries({queryKey:['change-management']})}})
  useDraftNavigationGuard(open && (dirty || save.isPending))
  const close = () => {if (save.isPending) return;if (dirty) setDiscard(true);else setOpen(false)}
  const field = 'mt-1 block w-full rounded-lg border border-line bg-canvas px-3 py-2'
  return <><Button onClick={() => setOpen(true)}>Resolve historical component scope</Button><Modal open={open} title={`Historical scope: ${change.title}`} size="lg" onClose={close} description="Record the scope at original approval from contemporaneous evidence. Use the original, planned and observed hashes from the release dossier. Current inventory values are suggestions only. This does not create retrospective approval or certification.">
    <form className="space-y-4" onSubmit={event => {event.preventDefault();save.mutate()}}>
      <label className="block text-sm">Historical evidence reference<input required className={field} value={reference} onChange={event => setReference(event.target.value)} /></label>
      <label className="block text-sm">How the evidence establishes the approved scope<textarea required className={field} value={evidence} onChange={event => setEvidence(event.target.value)} /></label>
      <label className="block text-sm">Responsibility at approval<select required className={field} value={role} onChange={event => setRole(event.target.value as ResponsibilityRole)}><option value="unknown">Not assessed</option><option value="licensed_operator">Licensed operator</option><option value="licensed_game_supplier">Licensed game supplier</option><option value="unlicensed_subcontractor">Unlicensed base-platform subcontractor</option></select></label>
      {rows.map((row,index) => <fieldset key={row.component_id} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2"><legend className="text-sm font-semibold">{row.component_uid || row.component_id}</legend>{(['component_uid','version','checksum_hash','planned_checksum_hash','implemented_checksum_hash'] as const).map(key => <label key={key} className="text-sm">Historical {key.replace(/_/g,' ')}<input required={!key.includes('checksum_hash') || Math.max(row.confidentiality_code,row.integrity_code,row.availability_code,row.accountability_code) === 3} className={field} value={row[key]} onChange={event => setRows(current => current.map((item,i) => i === index ? {...item,[key]:event.target.value} : item))} /></label>)}<label className="text-sm">Historical regulatory scope<select className={field} value={row.regulatory_scope} onChange={event => setRows(current => current.map((item,i) => i === index ? {...item,regulatory_scope:event.target.value as RegulatoryScope} : item))}>{['unknown','base_platform','rng','game','game_platform','other'].map(scope => <option key={scope} value={scope}>{scope.replace(/_/g,' ')}</option>)}</select></label>{(['confidentiality_code','integrity_code','availability_code','accountability_code'] as const).map(key => <label key={key} className="text-sm">Historical {key.replace('_code','')}<select className={field} value={row[key]} onChange={event => setRows(current => current.map((item,i) => i === index ? {...item,[key]:Number(event.target.value)} : item))}><option value={1}>1 — No relevance</option><option value={2}>2 — Some relevance</option><option value={3}>3 — Substantial relevance</option></select></label>)}</fieldset>)}
      {save.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(save.error,'Scope could not be attested. Entries are preserved.')}</p>}<div className="flex gap-2"><Button variant="primary" type="submit" loading={save.isPending}>Record evidenced scope</Button><Button onClick={close}>Cancel</Button></div>
    </form>
  </Modal><ConfirmDialog open={discard} title="Discard historical scope entries?" description="No attestation has been saved." confirmLabel="Discard changes" onClose={() => setDiscard(false)} onConfirm={() => {setReference('');setEvidence('');setRows(JSON.parse(initialRows.current));setRole(responsibilityRole || 'unknown');setOpen(false);setDiscard(false)}} /></>
}
