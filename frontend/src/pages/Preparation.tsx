import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import type {
  CertificationProject,
  PaginatedResponse,
  UserMention,
} from '../types'
import { preparationApi } from '../api/preparation'
import SectionNav from '../components/ui/SectionNav'
import CasePortfolio from '../components/preparation/CasePortfolio'
import CaseDetail from '../components/preparation/CaseDetail'
import TemplateBuilder from '../components/preparation/TemplateBuilder'
import { EvidenceLibrary } from '../components/preparation/EvidenceLibrary'

const tabs = [
  { id: 'cases', label: 'Existing forms' },
  { id: 'templates', label: 'Saved blank forms' },
  { id: 'evidence', label: 'Evidence library' },
] as const

export default function Preparation({
  licenceApplications = false,
}: {
  licenceApplications?: boolean
}) {
  const kindScope = licenceApplications ? 'licence_application' : undefined
  const title = licenceApplications ? 'Licence Applications' : 'Existing forms'
  const backLabel = licenceApplications ? 'All applications' : 'All forms'
  const sectionTabs = licenceApplications
    ? tabs.map((item) => item.id === 'cases' ? { ...item, label: 'Applications' } : item)
    : tabs
  const { user } = useAuth()
  const {
    jurisdictionId,
    jurisdictions,
    jurisdictionById,
    error: jurisdictionError,
    retry: retryJurisdictions,
  } = useJurisdiction()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const caseId = params.get('case')
  const returnProject = params.get('return_project')
  const tab = tabs.some((item) => item.id === params.get('tab'))
    ? params.get('tab')!
    : 'cases'
  const canManage = user?.role === 'admin' || user?.role === 'manager'
  const canEdit = canManage || user?.role === 'contributor'
  const caseQuery = useQuery({
    queryKey: ['preparation', 'case', caseId],
    queryFn: () => preparationApi.getCase(caseId!),
    enabled: Boolean(caseId),
  })
  const usersQuery = useQuery({
    queryKey: ['preparation', 'users'],
    queryFn: async () =>
      (
        await api.get<PaginatedResponse<UserMention>>(
          '/users/mentions?limit=1000',
        )
      ).data,
    staleTime: 300000,
  })
  const projectsQuery = useQuery({
    queryKey: ['preparation', 'projects'],
    queryFn: async () =>
      (
        await api.get<PaginatedResponse<CertificationProject>>(
          '/certification-projects?limit=1000',
        )
      ).data,
    staleTime: 300000,
  })
  const navigateCase = (id: string | null) => {
    const next = new URLSearchParams(params)
    if (id) {
      next.set('case', id)
      next.delete('tab')
    } else next.delete('case')
    setParams(next)
  }
  const navigateTab = (value: string) => {
    const next = new URLSearchParams(params)
    next.delete('case')
    if (value === 'cases') next.delete('tab')
    else next.set('tab', value)
    setParams(next)
  }
  const jurisdictionName = (id: string) =>
    jurisdictionById[id]?.name || 'Jurisdiction unavailable'
  return (
    <div className="space-y-6 pb-10">
      <header>
        <h1 className="text-3xl font-semibold">{title}</h1>
        <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">
          {licenceApplications
            ? 'Prepare licence applications across jurisdictions, track owners and deadlines, and collect supporting evidence.'
            : 'Open existing certification, audit and evidence collection forms.'}
        </p>
      </header>
      {jurisdictionError && (
        <p
          role="alert"
          className="rounded-lg bg-warning-soft p-3 text-sm text-warning"
        >
          {jurisdictionError}{' '}
          <button
            type="button"
            className="underline"
            onClick={retryJurisdictions}
          >
            Retry
          </button>
        </p>
      )}
      {!caseId && (
        <SectionNav
          label={`${title} sections`}
          value={tab}
          items={sectionTabs}
          onChange={navigateTab}
        />
      )}
      {caseId ? (
        caseQuery.isLoading ? (
          <p role="status" className="text-muted">
            Loading form…
          </p>
        ) : caseQuery.isError ? (
          <div
            role="alert"
            className="rounded-lg bg-danger-soft p-5 text-danger"
          >
            Case could not be loaded.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => void caseQuery.refetch()}
            >
              Retry
            </button>{' '}
            <button
              type="button"
              className="ml-3 underline"
              onClick={() => navigateCase(null)}
            >
              {backLabel}
            </button>
          </div>
        ) : caseQuery.data && kindScope && caseQuery.data.kind !== kindScope ? (
          <div role="alert" className="rounded-lg bg-warning-soft p-5 text-warning">
            This form is not a licence application.{' '}
            <Link className="underline" to={`/preparation?case=${encodeURIComponent(caseId)}`}>
              Open form
            </Link>{' '}
            <button type="button" className="ml-3 underline" onClick={() => navigateCase(null)}>
              {backLabel}
            </button>
          </div>
        ) : caseQuery.data ? (
          <CaseDetail
            key={caseId}
            item={caseQuery.data}
            canEdit={canEdit}
            canManage={canManage}
            users={usersQuery.data?.items || []}
            projects={projectsQuery.data?.items || []}
            jurisdictionName={jurisdictionName}
            backLabel={returnProject && caseQuery.data.project_id === returnProject ? 'Return to certification project' : backLabel}
            onBack={() => returnProject && caseQuery.data?.project_id === returnProject ? navigate(`/certification-projects?project=${encodeURIComponent(returnProject)}&section=forms`) : navigateCase(null)}
          />
        ) : null
      ) : tab === 'templates' ? (
        <TemplateBuilder jurisdictionId={jurisdictionId || undefined} canManage={canManage} kindScope={kindScope} />
      ) : tab === 'evidence' ? (
        <EvidenceLibrary canEdit={canEdit} />
      ) : (
        <CasePortfolio
            spaceJurisdictionId={licenceApplications ? jurisdictionId : undefined}
          kindScope={kindScope}
          onTemplates={() => navigateTab('templates')}
          jurisdictions={jurisdictions}
          users={usersQuery.data?.items || []}
          projects={projectsQuery.data?.items || []}
          canManage={canManage}
          onOpen={(id) => navigateCase(id)}
        />
      )}
      {(usersQuery.isError || projectsQuery.isError) && (
        <p role="alert" className="text-sm text-warning">
          {usersQuery.isError ? 'Owner names could not be loaded. ' : ''}
          {projectsQuery.isError
            ? 'Certification projects could not be loaded. '
            : ''}
          <button
            type="button"
            className="underline"
            onClick={() => {
              if (usersQuery.isError) void usersQuery.refetch()
              if (projectsQuery.isError) void projectsQuery.refetch()
            }}
          >
            Retry
          </button>
        </p>
      )}
    </div>
  )
}
