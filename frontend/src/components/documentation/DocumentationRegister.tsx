import { useEffect, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import api from '../../api/client'
import type { PaginatedResponse, UserMention } from '../../types'
import { documentationApi } from '../../api/documentation'
import { getApiErrorMessage } from '../../api/errors'
import type { DocumentationExpectation, DocumentationRegister as RegisterRecord, ProcessTarget } from '../../types/documentation'
import { Field, inputClass } from '../applications/Fields'
import SectionNav from '../ui/SectionNav'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import LoadError from '../ui/LoadError'
import { Table, THead, TBody, TH, TR, TableEmpty } from '../ui/Table'
import AccessPanel from '../access/AccessPanel'
import ExpectationEditor from './ExpectationEditor'
import RegisterRowEditor from './RegisterRowEditor'
import RegisterEntryRow from './RegisterEntryRow'
import RegisterOwnerPicker from './RegisterOwnerPicker'
import RowReviewPicker from './RowReviewPicker'
import { invalidateDocumentationRow } from './cache'
import RegisterProcessPicker from './RegisterProcessPicker'
import ProcessTargetPicker from './ProcessTargetPicker'
import ProcessDocumentsModal from './ProcessDocumentsModal'
import EvidenceMapping from './EvidenceMapping'
import RegisterDocumentPreview from './RegisterDocumentPreview'
import SpreadsheetImport from './SpreadsheetImport'
import AuditorRequests from './AuditorRequests'
import RegisterHandover from './RegisterHandover'
import DocumentationSuggestions from './DocumentationSuggestions'
import EvidenceVersions from './EvidenceVersions'
import { expectationReasons } from './model'
import { useLocalDraftGuard } from '../../hooks/useLocalDraftGuard'

export default function DocumentationRegister({ jurisdictionId, canEdit, projectId, requirementId, auditorView = false, heading = 'Documentation register', showIntroduction = true }: {
  jurisdictionId: string; canEdit: boolean; projectId?: string; requirementId?: string; auditorView?: boolean; heading?: string; showIntroduction?: boolean
}) {
  const [params, setParams] = useSearchParams()
  const { user } = useAuth()
  const location = useLocation()
  const cache = useQueryClient()
  const [processOpen, setProcessOpen] = useState(false)
  const [assignmentRow, setAssignmentRow] = useState<DocumentationExpectation | null>(null)
  const [reviewRow, setReviewRow] = useState<DocumentationExpectation | null>(null)
  const [matchRow, setMatchRow] = useState<DocumentationExpectation | null>(null)
  const [processDocuments, setProcessDocuments] = useState<{ rowId: string; target: ProcessTarget; returnTo: string } | null>(null)
  const restoredRow = useRef('')
  const [creating, setCreating] = useState(false)
  const [registerName, setRegisterName] = useState('')
  const [createError, setCreateError] = useState('')
  const [busy, setBusy] = useState(false)
  const [rowEditor, setRowEditor] = useState<DocumentationExpectation | 'new' | null>(null)
  const [previewEvidence, setPreviewEvidence] = useState<string | null>(null)
  const [documentRow, setDocumentRow] = useState<DocumentationExpectation | null>(null)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [sectionOpen, setSectionOpen] = useState(false)
  const [sectionName, setSectionName] = useState('')
  const [sectionError, setSectionError] = useState('')
  const registerDraft = useLocalDraftGuard(creating && Boolean(registerName), creating && busy, () => setCreating(false))
  const sectionDraft = useLocalDraftGuard(sectionOpen && Boolean(sectionName), sectionOpen && busy, () => setSectionOpen(false))
  const requestedRow = params.get('docRow')
  const owner = params.get('docOwner') || ''
  const update = (key: string, value: string) => setParams(current => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next })
  const registers = useQuery({ queryKey: ['documentation', 'registers', jurisdictionId], queryFn: () => documentationApi.registers(jurisdictionId), enabled: Boolean(jurisdictionId) })
  const requested = params.get('register')
  const register = registers.data?.items.find(item => item.id === requested) || (!requested ? registers.data?.items[0] : undefined)
  const sections = useQuery({ queryKey: ['documentation', 'sections', register?.id], queryFn: () => documentationApi.sections(register!.id), enabled: Boolean(register) })
  const activeSection = auditorView ? 'all' : params.get('docSection') || sections.data?.items[0]?.id || 'all'
  const search = params.get('docSearch') || ''
  const category = params.get('docCategory') || ''
  const expectations = useInfiniteQuery({ queryKey: ['documentation', 'expectations', register?.id, projectId, requirementId, activeSection, search, category, owner], queryFn: ({ pageParam }) => documentationApi.expectations(register!.id, { skip: String(pageParam), q: search, ...(category ? { category } : {}), ...(owner === 'unassigned' ? { unassigned: 'true' } : owner ? { owner_id: owner } : {}), ...(!['all', 'unsectioned'].includes(activeSection) ? { section_id: activeSection } : activeSection === 'unsectioned' ? { unsectioned: 'true' } : {}), ...(projectId ? { project_id: projectId } : {}), ...(requirementId ? { requirement_id: requirementId } : {}) }), initialPageParam: 0, getNextPageParam: (lastPage, pages) => { const count = pages.reduce((sum, page) => sum + page.items.length, 0); return count < lastPage.total ? count : undefined }, enabled: Boolean(!auditorView && register && sections.isSuccess) })
  const users = useQuery({ queryKey: ['documentation', 'users'], queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data, enabled: toolsOpen })
  const permittedEdit = canEdit && Boolean(register?.access.permissions.includes('edit'))
  const coverage = params.get('docCoverage') || ''
  const view = params.get('view') === 'documents' ? 'documents' : 'obligations'
  const all = useMemo(() => expectations.data?.pages.flatMap(page => page.items) || [], [expectations.data])
  const returnedRow = useQuery({ queryKey: ['documentation', 'returned-row', register?.id, requestedRow], queryFn: async () => (await api.get<DocumentationExpectation>(`/documentation/expectations/${requestedRow}`)).data, enabled: Boolean(requestedRow && register && !all.some(item => item.id === requestedRow)) })
  const returned = returnedRow.data?.register_id === register?.id ? returnedRow.data : undefined
  const scoped = useMemo(() => [...all, ...(returned && !all.some(item => item.id === returned.id) ? [returned] : [])].filter(item => (!projectId || item.project_id === projectId || !item.project_id) && (!requirementId || item.requirements.some(link => link.requirement_id === requirementId)) && (activeSection === 'all' || (activeSection === 'unsectioned' ? !item.section_id : item.section_id === activeSection))), [all, returned, projectId, requirementId, activeSection])
  const filtered = useMemo(() => scoped.filter(item => `${item.required_documentation ?? item.title} ${item.description || ''} ${item.source_reference || ''} ${item.document_name || ''}`.toLowerCase().includes(search.toLowerCase()) && (!category || item.category === category) && (!owner || (owner === 'unassigned' ? !item.owner_id : item.owner_id === owner)) && (!coverage || (['unreviewed', 'partial', 'sufficient'].includes(coverage) ? (item.effective_coverage_status || item.coverage_status) === coverage : expectationReasons(item).includes(coverage)))), [scoped, search, category, owner, coverage])
  const selectedId = params.get('expectation')
  const selectedRecord = useQuery({ queryKey: ['documentation', 'expectation-detail', selectedId], queryFn: async () => (await api.get<DocumentationExpectation>(`/documentation/expectations/${selectedId}`)).data, enabled: Boolean(selectedId && register && !all.some(item => item.id === selectedId)) })
  const selectedFallback = selectedRecord.data?.register_id === register?.id && (!projectId || !selectedRecord.data?.project_id || selectedRecord.data.project_id === projectId) && (!requirementId || selectedRecord.data?.requirements.some(link => link.requirement_id === requirementId)) ? selectedRecord.data : undefined
  const selected = scoped.find(item => item.id === selectedId) || selectedFallback
  const returnToRow = (rowId: string) => { const query = new URLSearchParams(params); if (register) query.set('register', register.id); query.set('docSection', activeSection); query.set('docRow', rowId); query.delete('expectation'); return `${location.pathname}?${query}#documentation-row-${rowId}` }
  const refresh = () => cache.invalidateQueries({ queryKey: ['documentation'] })
  const documents = useMemo(() => {
    const groups = new Map<string, { title: string; items: DocumentationExpectation[]; rowIds: Set<string> }>()
    if (view !== 'documents') return groups
    for (const item of filtered) {
    const links = [...item.coverage.map(link => ({ key: `library:${link.evidence_id}`, title: link.evidence?.title || link.title || 'Linked document' })), ...(item.process_targets || []).filter(target => target.available).flatMap(target => [...(target.collection?.items || []).map(link => ({ key: link.evidence_id ? `library:${link.evidence_id}` : `review:${link.file_id}`, title: link.title })), ...(target.collection?.has_review_notes ? [{ key: `notes:${target.review_cycle_id}:${target.review_item_id}`, title: `Assessment notes · ${target.reference_id}` }] : []), ...(target.collection?.warning && !target.collection.items.length ? [{ key: `unavailable:${target.id}`, title: 'Unavailable process evidence' }] : [])])]
    if (item.process_targets?.some(target => !target.available)) links.push({ key: `unavailable:${item.id}`, title: 'Unavailable process evidence' })
    for (const link of links) { const group = groups.get(link.key) || { title: link.title, items: [], rowIds: new Set<string>() }; if (!group.rowIds.has(item.id)) { group.items.push(item); group.rowIds.add(item.id) } groups.set(link.key, group) }
    }
    return groups
  }, [filtered, view])
  const hasDocuments = (item: DocumentationExpectation) => item.coverage.length > 0 || item.process_targets?.some(target => !target.available || target.collection?.items.length || target.collection?.has_review_notes || target.collection?.warning)
  useEffect(() => { if (!requestedRow || restoredRow.current === `${register?.id}:${requestedRow}`) return; const element = document.getElementById(`documentation-row-${requestedRow}`); if (element) { restoredRow.current = `${register?.id}:${requestedRow}`; element.scrollIntoView({ block: 'center' }); element.focus({ preventScroll: true }) } }, [requestedRow, register?.id, filtered])
  const table = (rows: DocumentationExpectation[]) => <div className="max-w-full overflow-x-auto rounded-md border border-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" tabIndex={0} role="region" aria-label="Scrollable documentation table">
    <Table aria-label="Documentation register entries" className="w-full table-fixed" style={{ minWidth: 1120 }}><THead><TR><TH className="w-[32%] !text-sm normal-case">Document / record required</TH><TH className="w-[14%] !text-sm normal-case">SCP reference</TH><TH className="w-[22%] !text-sm normal-case">Comment/explanation</TH><TH className="w-[18%] !text-sm normal-case">Document</TH><TH className="w-[14%] !text-sm normal-case">Actions</TH></TR></THead><TBody>
      {rows.map(item => <RegisterEntryRow key={item.id} row={item} bound={Boolean(item.process ?? register?.process)} canEdit={permittedEdit} returnTo={returnToRow(item.id)} onDetails={() => update('expectation', item.id)} onEdit={() => setRowEditor(item)} onAssign={() => setAssignmentRow(item)} onReview={() => setReviewRow(item)} onMatch={() => setMatchRow(item)} onManage={target => setProcessDocuments({ rowId: item.id, target, returnTo: returnToRow(item.id) })} onStandalone={() => setDocumentRow(item)} onPreview={setPreviewEvidence} />)}
      {!rows.length && <TableEmpty colSpan={5}>{coverage && expectations.hasNextPage ? 'No loaded rows match this coverage filter. Load more rows to continue.' : search || category || coverage || owner ? 'No rows match these filters.' : 'This section has no rows. Add a row or import a spreadsheet.'}</TableEmpty>}
    </TBody></Table>
  </div>
  if (!jurisdictionId) return <p className="text-sm text-muted">Select a jurisdiction to open its documentation registers.</p>
  return <section className="space-y-5 min-w-0" aria-label={auditorView ? 'Auditor requests and gaps' : 'Documentation register'}>
    {registerDraft.confirmation}{sectionDraft.confirmation}
    <header className="flex flex-wrap items-start justify-between gap-3"><div className="space-y-1"><h2 className="text-xl font-semibold">{auditorView ? 'Auditor requests and gaps' : heading}</h2>{showIntroduction && <p className="max-w-prose text-sm text-muted">Keep required records, source references, comments, and documents together.</p>}</div>{canEdit && <Button onClick={() => setCreating(true)}>New register</Button>}</header>
    {registers.isLoading && <p role="status">Loading registers…</p>}{registers.isError && <LoadError subject="Documentation registers" onRetry={() => void registers.refetch()} />}
    {registers.isSuccess && !registers.data.items.length && <p className="border-y border-line py-6 text-sm text-muted">No registers are available. Create a register to add sections and rows.</p>}
    {!!registers.data?.items.length && <div className="flex flex-wrap items-end gap-3"><div className="min-w-0 flex-1"><Field label="Documentation register"><select className={inputClass} value={register?.id || ''} onChange={event => setParams(current => { const next = new URLSearchParams(current); next.set('register', event.target.value); next.delete('expectation'); next.delete('docSection'); return next })}><option value="" disabled>Select a register</option>{registers.data.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field></div>{register && <Button onClick={() => setToolsOpen(true)}>Register tools</Button>}</div>}
    {requested && registers.isSuccess && !register && <p role="alert">This register is unavailable. Select an available register.</p>}
    {register && <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"><span className="text-muted">Register default process:</span><span>{register.process ? register.process.available ? `${register.process.project_name ? register.process.project_name + ' · ' : ''}${register.process.name}` : 'Unavailable' : 'None'}</span>{permittedEdit && <Button variant="ghost" size="sm" onClick={() => setProcessOpen(true)}>{register.process ? 'Change process' : 'Link process'}</Button>}</div>
      {auditorView ? <AuditorRequests key={register.id} register={register} projectId={projectId} canEdit={permittedEdit} /> : <>
        {sections.isLoading && <p role="status">Loading sections…</p>}{sections.isError && <LoadError subject="Register sections" onRetry={() => void sections.refetch()} />}
        <div className="flex flex-wrap items-end justify-between gap-3"><div className="min-w-0 max-w-full flex-1 overflow-x-auto [&_nav]:w-max [&_nav]:flex-nowrap [&_button]:whitespace-nowrap"><SectionNav label="Register sections" value={activeSection} items={[{ id: 'all', label: 'All sections' }, ...(sections.data?.items || []).map(section => ({ id: section.id, label: section.name })), { id: 'unsectioned', label: 'Unsectioned' }]} onChange={value => setParams(current => { const next = new URLSearchParams(current); next.set('docSection', value); next.delete('expectation'); return next })} /></div>{permittedEdit && <Button onClick={() => { setSectionOpen(true); setSectionError('') }}>New section</Button>}</div>
        <div className="flex flex-wrap items-end justify-between gap-3"><div className="w-full sm:max-w-sm"><Field label="Search rows"><input type="search" maxLength={255} className={inputClass} value={search} onChange={event => update('docSearch', event.target.value)} /></Field></div><div className="flex flex-wrap gap-2">{permittedEdit && !requirementId && <Button variant="primary" disabled={!expectations.isSuccess} onClick={() => setRowEditor('new')}>Add row</Button>}{requirementId && <Link className="inline-flex items-center text-sm font-semibold text-accent underline" to={`/library?section=documentation&register=${encodeURIComponent(register.id)}`}>Open register</Link>}{permittedEdit && <Button onClick={() => setImportOpen(true)}>Import spreadsheet</Button>}</div></div>
        {(category || coverage || owner) && <p className="text-sm text-muted">Additional filters are active. <Button size="sm" onClick={() => setParams(current => { const next = new URLSearchParams(current); ['docCategory', 'docCoverage', 'docOwner'].forEach(key => next.delete(key)); return next })}>Clear filters</Button></p>}
        {expectations.isLoading && <p role="status">Loading rows…</p>}{expectations.isError && <LoadError subject="Register rows" onRetry={() => void expectations.refetch()} />}
        {expectations.isSuccess && <><p className="text-sm text-muted" role="status">{filtered.length} {coverage ? 'matching loaded ' : ''}{filtered.length === 1 ? 'row' : 'rows'}{(expectations.data.pages[0]?.total || 0) > all.length ? ` · ${all.length} of ${expectations.data.pages[0]?.total} loaded` : ''}</p>{view === 'documents' ? <div className="space-y-5">{[...documents.entries()].map(([id, group]) => <section className="space-y-2" key={id}><h3 className="font-semibold">{group.title}</h3>{table(group.items)}</section>)}{filtered.some(item => !hasDocuments(item)) && <section className="space-y-2"><h3 className="font-semibold">Rows without linked documents</h3>{table(filtered.filter(item => !hasDocuments(item)))}</section>}</div> : table(filtered)}</>}
        {coverage && <p className="text-sm text-muted">Coverage filters apply to the rows loaded in this view.{expectations.hasNextPage ? ' Load more rows to check the rest of the register.' : ' All rows for this section and other filters are loaded.'}</p>}
        {expectations.hasNextPage && <Button loading={expectations.isFetchingNextPage} onClick={() => void expectations.fetchNextPage()}>Load more rows</Button>}
        {returnedRow.isError && <LoadError subject="Returned register row" onRetry={() => void returnedRow.refetch()} />}
        {selectedRecord.isError && <LoadError subject="Selected row" onRetry={() => void selectedRecord.refetch()} />}
        {selected && <Modal open title="Row details" size="lg" onClose={() => update('expectation', '')}><ExpectationEditor key={selected.id} expectation={selected} jurisdictionId={jurisdictionId} projectId={projectId} canEdit={permittedEdit} canReview={Boolean(register.access.permissions.includes('approve')) && ['admin', 'manager', 'approver'].includes(user?.role || '')} onSaved={() => void refresh()} /></Modal>}
        {rowEditor && <RegisterRowEditor key={rowEditor === 'new' ? `new-${register.id}-${activeSection}` : rowEditor.id} row={rowEditor === 'new' ? undefined : rowEditor} registerId={register.id} projectId={projectId} sectionId={!['all', 'unsectioned'].includes(activeSection) ? activeSection : undefined} sections={sections.data?.items || []} onClose={() => setRowEditor(null)} onSaved={() => { setRowEditor(null); void refresh() }} />}
        {documentRow && <EvidenceMapping key={documentRow.id} expectation={documentRow} simple onClose={() => setDocumentRow(null)} onSaved={() => { setDocumentRow(null); void refresh() }} />}
      </>}
      <Modal open={toolsOpen} title="Register tools" size="lg" onClose={() => setToolsOpen(false)}><div className="space-y-5"><Link className="text-sm text-accent underline" to={`/library?section=evidence&returnTo=${encodeURIComponent(location.pathname + location.search)}`}>Open evidence library</Link><RegisterHandover register={register} projectId={projectId} />{register.access.permissions.includes('manage_access') && <AccessPanel type="documentation_register" id={register.id} />}<SectionNav label="Documentation views" value={view} items={[{ id: 'obligations', label: 'By section' }, { id: 'documents', label: 'By document' }]} onChange={value => update('view', value)} /><div className="grid gap-3 sm:grid-cols-2"><Field label="Category"><input maxLength={100} className={inputClass} list={`documentation-categories-${register.id}`} value={category} placeholder="All categories" onChange={event => update('docCategory', event.target.value)} /><datalist id={`documentation-categories-${register.id}`}>{[...new Set(scoped.map(item => item.category).filter(Boolean))].map(value => <option key={value} value={value!} />)}</datalist><p className="mt-1 text-xs text-muted">Exact category; suggestions come from loaded rows.</p></Field><Field label="Coverage"><select className={inputClass} value={coverage} onChange={event => update('docCoverage', event.target.value)}><option value="">All coverage</option>{['unreviewed', 'partial', 'sufficient', 'missing', 'stale', 'expired'].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></Field><Field label="Owner"><select className={inputClass} value={owner} onChange={event => update('docOwner', event.target.value)}><option value="">All owners</option><option value="unassigned">Unassigned</option>{users.data?.items.map(value => <option key={value.id} value={value.id}>{value.full_name}</option>)}</select></Field></div><EvidenceVersions registerId={register.id} canEdit={permittedEdit} />{permittedEdit && filtered.length > 0 && <DocumentationSuggestions expectation={filtered[0]} selectedExpectations={filtered} canEdit={permittedEdit} mappingOnly onSaved={() => void refresh()} />}</div></Modal>
      {processOpen && <RegisterProcessPicker register={register} onClose={() => setProcessOpen(false)} onSaved={updated => { const key = ['documentation', 'registers', jurisdictionId]; cache.setQueryData<PaginatedResponse<RegisterRecord>>(key, current => current ? { ...current, items: current.items.map(item => item.id === updated.id ? updated : item) } : { items: [updated], total: 1 }); setProcessOpen(false); void refresh() }} />}
      {assignmentRow && <RegisterOwnerPicker key={assignmentRow.id} row={assignmentRow} onClose={() => setAssignmentRow(null)} onSaved={saved => { setAssignmentRow(null); void invalidateDocumentationRow(cache, saved) }} />}
      {reviewRow && <RowReviewPicker key={reviewRow.id} row={reviewRow} registerProcess={register.process} onClose={() => setReviewRow(null)} onSaved={saved => { setReviewRow(null); void invalidateDocumentationRow(cache, saved); if (saved.process?.available) setMatchRow(saved) }} />}
      {matchRow && <ProcessTargetPicker row={matchRow} onClose={() => setMatchRow(null)} onSaved={() => { setMatchRow(null); void refresh() }} />}
      {processDocuments && <ProcessDocumentsModal {...processDocuments} onClose={() => setProcessDocuments(null)} />}
      {previewEvidence && <RegisterDocumentPreview id={previewEvidence} onClose={() => setPreviewEvidence(null)} />}
      {importOpen && <SpreadsheetImport register={register} onClose={() => setImportOpen(false)} onImported={() => void refresh()} />}
      <Modal open={sectionOpen} title="New section" onClose={sectionDraft.requestClose}><form className="space-y-4" onSubmit={async event => { event.preventDefault(); setBusy(true); setSectionError(''); try { const section = await documentationApi.createSection(register.id, sections.data?.revision || register.revision, sectionName.trim()); const sectionKey = ['documentation', 'sections', register.id]; await cache.cancelQueries({ queryKey: sectionKey, exact: true }); cache.setQueryData<{ items: typeof section[]; total: number; revision: number }>(sectionKey, current => ({ items: [...(current?.items || []), section], total: (current?.total || 0) + 1, revision: section.register_revision || register.revision + 1 })); void refresh(); setParams(current => { const next = new URLSearchParams(current); next.set('docSection', section.id); next.delete('expectation'); return next }); setSectionOpen(false); setSectionName('') } catch (caught) { setSectionError(getApiErrorMessage(caught, 'The section could not be created. Your name is preserved.')) } finally { setBusy(false) } }}><Field label="Section name"><input required maxLength={255} className={inputClass} value={sectionName} onChange={event => setSectionName(event.target.value)} /></Field>{sectionError && <p role="alert" className="text-sm text-danger">{sectionError}</p>}<Button variant="primary" type="submit" loading={busy} disabled={!sectionName.trim()}>Create section</Button></form></Modal>
    </>}
    <Modal open={creating} title="New documentation register" description="Registers start highly confidential. Share access explicitly after creation." onClose={registerDraft.requestClose}><form className="space-y-4" onSubmit={async event => { event.preventDefault(); setBusy(true); setCreateError(''); try { const item = await documentationApi.createRegister({ name: registerName.trim(), jurisdiction_id: jurisdictionId, visibility: 'secret' }); const registerKey = ['documentation', 'registers', jurisdictionId]; await cache.cancelQueries({ queryKey: registerKey, exact: true }); cache.setQueryData<PaginatedResponse<RegisterRecord>>(registerKey, current => ({ items: [item, ...(current?.items || []).filter(value => value.id !== item.id)], total: (current?.total || 0) + (current?.items.some(value => value.id === item.id) ? 0 : 1) })); setParams(current => { const next = new URLSearchParams(current); next.set('register', item.id); next.delete('expectation'); next.delete('docSection'); return next }); setCreating(false); setRegisterName(''); void cache.invalidateQueries({ queryKey: registerKey, exact: true }) } catch (error) { setCreateError(getApiErrorMessage(error, 'The register could not be created. Your name is preserved.')) } finally { setBusy(false) } }}><Field label="Register name"><input required maxLength={200} className={inputClass} value={registerName} onChange={event => setRegisterName(event.target.value)} /></Field>{createError && <p role="alert" className="text-danger">{createError}</p>}<Button variant="primary" type="submit" loading={busy} disabled={!registerName.trim()}>Create register</Button></form></Modal>
  </section>
}
