import SectionNav from '../components/ui/SectionNav'
import './workflow-pages.css'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import type { CertificationProject, PaginatedResponse, UserMention } from '../types'
import { PREPARATION_KINDS, type PreparationKind } from '../types/preparation'
import TemplateBuilder from '../components/preparation/TemplateBuilder'
import CasePortfolio from '../components/preparation/CasePortfolio'
import { EvidenceLibrary } from '../components/preparation/EvidenceLibrary'

const sections = [
  { id: 'requirements', label: 'Requirements' },
  { id: 'templates', label: 'Form templates' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'forms', label: 'Existing forms' },
]

export default function Library() {
  const { user } = useAuth()
  const { jurisdictionId, jurisdictions, jurisdictionById, error: jurisdictionError, retry } = useJurisdiction()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const requestedSection = params.get('section')
  const section = sections.some((item) => item.id === requestedSection) ? requestedSection! : 'templates'
  const kind = params.get('kind')
  const kindScope = PREPARATION_KINDS.includes(kind as PreparationKind) ? kind as PreparationKind : undefined
  const sourceDocument = params.get('sourceDocument') || undefined
  const sourceJurisdiction = params.get('jurisdiction') || jurisdictionId || undefined
  const returnTo = params.get('returnTo')
  const safeReturn = returnTo && /^\/(licence-applications|certification-projects|preparation)(?:[/?]|$)/.test(returnTo) ? returnTo : null
  const canManage = user?.role === 'admin' || user?.role === 'manager'
  const canEdit = canManage || user?.role === 'contributor'
  const users = useQuery({
    queryKey: ['preparation', 'users'],
    queryFn: async () => (await api.get<PaginatedResponse<UserMention>>('/users/mentions?limit=1000')).data,
    enabled: section === 'forms', staleTime: 300000,
  })
  const projects = useQuery({
    queryKey: ['preparation', 'projects'],
    queryFn: async () => (await api.get<PaginatedResponse<CertificationProject>>('/certification-projects?limit=1000')).data,
    enabled: section === 'forms', staleTime: 300000,
  })
  return <div className="workflow-page library-page space-y-6 pb-10">
    <header className="space-y-2">
      <h1 className="text-3xl font-semibold">{sections.find((item) => item.id === section)?.label}</h1>
      <p className="max-w-prose text-sm leading-relaxed text-muted">Requirements describe obligations. Saved blank forms define reusable questions. Completed forms contain answers and supporting evidence.</p>
      {safeReturn && <Link to={safeReturn} className="inline-block text-sm font-semibold text-accent underline">Return to your workspace</Link>}
    </header>

    <SectionNav label="Resource sections" value={section} items={sections} onChange={value => { const next = new URLSearchParams(params); next.set('section', value); next.delete('sourceDocument'); next.delete('kind'); navigate(`/library?${next.toString()}`) }} />
    {jurisdictionError && <p role="alert" className="text-sm text-warning">{jurisdictionError} <button type="button" className="underline" onClick={retry}>Retry</button></p>}
    {section === 'requirements' && <div className="space-y-3"><h2 className="text-xl font-semibold">Shared requirement sources</h2><p className="max-w-prose text-sm text-muted">Create or import requirements, check their source and wording, then use them in certification assessments or licence application forms.</p><Link className="font-semibold text-accent underline" to="/requirements">Open requirements</Link></div>}
    {section === 'templates' && <>
      {sourceDocument && <p className="text-sm text-muted">Using requirements from {jurisdictionById[sourceJurisdiction || '']?.name || 'the source jurisdiction'}. Draft sources can support form preparation; certification assessments require an approved baseline.</p>}
      <TemplateBuilder key={`${sourceDocument || ''}-${sourceJurisdiction || ''}-${kindScope || ''}`} canManage={canManage} kindScope={kindScope} jurisdictionId={sourceDocument ? sourceJurisdiction : jurisdictionId || undefined} initialImportSource={sourceDocument ? 'requirements' : undefined} initialRequirementsDocumentId={sourceDocument} />
    </>}
    {section === 'evidence' && <><p className="max-w-prose text-sm text-muted">Reuse files, notes and links in forms across the workflows. Evidence recorded against a requirement assessment remains with that assessment and its approved history.</p><EvidenceLibrary canEdit={canEdit} /></>}
    {section === 'forms' && <>
      <p className="max-w-prose text-sm text-muted">Work on standalone annexes, audit forms and questionnaires, or link a form to a certification project. Application packs organise their forms in Licence Applications.</p>
      {(users.isError || projects.isError) && <p role="alert" className="text-sm text-warning">Some owners or projects could not be loaded. <button type="button" className="underline" onClick={() => { void users.refetch(); void projects.refetch() }}>Retry</button></p>}
      <CasePortfolio canManage={canManage} users={users.data?.items || []} projects={projects.data?.items || []} jurisdictions={jurisdictions} spaceJurisdictionId={jurisdictionId} kindScope={kindScope} onTemplates={() => {
        const next = new URLSearchParams(params)
        next.set('section', 'templates')
        next.delete('sourceDocument'); next.delete('jurisdiction'); next.delete('kind')
        navigate(`/library?${next.toString()}`)
      }} onOpen={(id, formKind) => navigate(`${formKind === 'licence_application' ? '/licence-applications' : '/preparation'}?case=${encodeURIComponent(id)}`)} />
    </>}
  </div>
}
