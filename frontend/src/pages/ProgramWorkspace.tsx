import { formatDateTime, formatDate } from '../utils/dateFormat'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../api/client'
import type { ProgramWorkspaceSummary } from '../types'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'

const stageStateClass = (state: string) => {
  if (state === 'completed') return 'bg-success-soft text-success'
  if (state === 'in_progress') return 'bg-brand-soft text-accent'
  if (state === 'ready') return 'bg-info-soft text-info'
  if (state === 'blocked') return 'bg-danger-soft text-danger'
  return 'bg-subtle text-ink'
}

const checkStateClass = (passed: boolean) =>
  passed ? 'border-success-line bg-success-soft text-success' : 'border-danger-line bg-danger-soft text-danger'

export default function ProgramWorkspace() {
  const { jurisdictionId, jurisdictionById } = useJurisdiction()
  const [searchParams, setSearchParams] = useSearchParams()
  const projectParam = searchParams.get('project')

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['program-workspace-summary', jurisdictionId],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      const url = params.toString()
        ? `/program-workspace/summary?${params.toString()}`
        : '/program-workspace/summary'
      const response = await api.get<ProgramWorkspaceSummary>(url)
      return response.data
    },
    enabled: !!jurisdictionId,
  })

  const projects = useMemo(() => data?.items ?? [], [data?.items])
  const selectedProjectId = projectParam || projects[0]?.project_id || null
  const nextActions = (data?.next_actions ?? []).filter((action) => action.project_id === selectedProjectId)
  const setSelectedProjectId = (value: string) => {
    const next = new URLSearchParams(searchParams)
    next.set('project', value)
    setSearchParams(next)
  }
  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  )

  if (isLoading) {
    return <div className="py-8 text-center">Loading project readiness…</div>
  }

  if (error) {
    return <div className="space-y-3 py-8"><p role="alert" className="text-danger">Unable to load program readiness.</p><Button onClick={() => refetch()}>Try again</Button></div>
  }

  return (
    <div className="space-y-4">
      <header className="py-1">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-ink">Project readiness</h1>
            <p className="mt-1 text-sm text-muted">
              See what needs attention in each certification project and continue the next task. These checks guide internal preparation; they do not record regulator approval.
            </p>
            {jurisdictionId && jurisdictionById[jurisdictionId] ? (
              <div className="mt-1 text-xs text-muted">
                Jurisdiction: {jurisdictionById[jurisdictionId].name}
              </div>
            ) : null}
          </div>
          <div className="text-xs text-muted">
            Generated: {data ? formatDateTime(data.generated_at) : '-'}
          </div>
        </div>
      </header>

      {projects.length > 0 && <label className="block text-sm text-muted lg:hidden">Project
        <select aria-label="Project" className="mt-1 w-full px-3 py-2" value={selectedProjectId || ''} onChange={event => setSelectedProjectId(event.target.value)}>
          {!selectedProject && <option value="">Select a project</option>}
          {projects.map(project => <option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}
        </select>
      </label>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,240px)_minmax(0,1fr)]">
        <Card className="hidden self-start p-4 lg:block">
          <h2 className="text-sm font-semibold text-ink">Projects</h2>
          <div className="mt-3 space-y-2">
            {projects.length === 0 ? (
              <div className="rounded-md border border-dashed border-line-strong p-3 text-xs text-muted">
                No certification projects in this jurisdiction. Start a project to select requirements and plan certification.
              </div>
            ) : (
              projects.map((project) => (
                <button
                  key={project.project_id}
                  type="button"
                  aria-current={selectedProjectId === project.project_id ? 'page' : undefined}
                  onClick={() => setSelectedProjectId(project.project_id)}
                  className={[
                    'w-full rounded-lg border p-3 text-left transition-colors',
                    selectedProjectId === project.project_id
                      ? 'border-brand-line bg-brand-soft'
                      : 'border-line bg-surface hover:border-line-strong',
                  ].join(' ')}
                >
                  <div className="text-sm font-semibold text-ink">{project.project_name}</div>
                  <div className="mt-1 text-xs text-muted">
                    Stage: {project.stage.replace(/_/g, ' ')}
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    Target submission:{' '}
                    {project.target_submission_date
                      ? formatDate(project.target_submission_date)
                      : '-'}
                  </div>
                </button>
              ))
            )}
          </div>
          <Link to="/certification-projects" className="mt-4 inline-block text-sm text-accent underline">Manage certification projects</Link>
        </Card>

        <div className="min-w-0 space-y-4">
          {selectedProject && <div className="p-1">              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold text-ink">{selectedProject.project_name}</h2>
                  <div className="mt-1 text-xs text-muted">
                    Current stage: {selectedProject.stage.replace(/_/g, ' ')}
                  </div>
                </div>
                <Link
                  to={selectedProject.deep_links.project}
                  className="inline-flex items-center rounded-md border border-line-strong px-2.5 py-1.5 text-xs font-medium text-ink hover:border-brand-line hover:text-accent"
                >
                  Open project
                </Link>
              </div></div>}
          {projectParam && !selectedProject && <Card className="p-4"><p role="alert" className="text-sm text-muted">This project is not available in the selected jurisdiction. Choose a project or change jurisdiction.</p></Card>}
          {selectedProject && <Card className="p-4">
            <h2 className="text-sm font-semibold text-ink">Next actions</h2>
            <div className="mt-3 space-y-2">
              {nextActions.length === 0 ? (
                <div className="rounded-md border border-dashed border-line-strong p-3 text-xs text-muted">
                  No next actions are currently listed for your role in this project.
                </div>
              ) : (
                nextActions.slice(0, 8).map((action) => (
                  <div key={action.id} className="border-b border-line py-3 last:border-0">
                    <div className="text-sm font-semibold text-ink">{action.title}</div>
                    <div className="mt-1 text-xs text-muted">{action.summary}</div>
                    <div className="mt-2">
                      <Link
                        to={action.cta_path}
                        className="inline-flex items-center rounded-md border border-line-strong px-2 py-1 text-xs font-medium text-ink hover:border-brand-line hover:text-accent"
                      >
                        {action.cta_label}
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>}

          {selectedProject ? (
            <Card className="space-y-4 p-4">


              <div>
                <h3 className="text-sm font-semibold text-ink">Items needing attention</h3>
                <div className="mt-2 space-y-2">
                  {selectedProject.blockers.length === 0 ? (
                    <div className="rounded-md border border-success-line bg-success-soft p-3 text-xs text-success">
                      No listed readiness issues for this stage.
                    </div>
                  ) : (
                    selectedProject.blockers.map((blocker) => (
                      <div
                        key={`${selectedProject.project_id}-${blocker.code}`}
                        className="rounded-md border border-danger-line bg-danger-soft p-3 text-xs text-danger"
                      >
                        <div>{blocker.reason}</div>
                        {blocker.cta_path ? (
                          <div className="mt-1">
                            <Link to={blocker.cta_path} className="underline">
                              {blocker.cta_label || 'Open workflow'}
                            </Link>
                          </div>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-ink">Project stages</h3>
                <div className="mt-2 space-y-2">
                  {selectedProject.stage_states.map((stageState) => (
                    <details key={`${selectedProject.project_id}-${stageState.stage}`} className="border-b border-line py-3">
                      <summary className="cursor-pointer text-sm">
                        <span className="ml-1 inline-flex w-[calc(100%-2rem)] items-center justify-between gap-2">
                        <div className="text-sm font-medium text-ink">{stageState.title}</div>
                        <span
                          className={[
                            'rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide',
                            stageStateClass(stageState.state),
                          ].join(' ')}
                        >
                          {stageState.state.replace(/_/g, ' ')}
                        </span>
                        </span>
                      </summary>
                      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                        {stageState.checks.map((check) => (
                          <div
                            key={`${stageState.stage}-${check.code}`}
                            className={[
                              'rounded border px-2 py-1.5 text-xs',
                              checkStateClass(check.passed),
                            ].join(' ')}
                          >
                            <div className="font-semibold">{check.label}</div>
                            {!check.passed && check.reason ? (
                              <div className="mt-1">{check.reason}</div>
                            ) : null}
                            {!check.passed && check.cta_path ? (
                              <div className="mt-1">
                                <Link to={check.cta_path} className="underline">
                                  {check.cta_label || 'Open workflow'}
                                </Link>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              </div>


            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
