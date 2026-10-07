import './workflow-pages.css'
import ProjectForms from '../components/workflows/ProjectForms'
import ProjectMaintenance from '../components/workflows/ProjectMaintenance'
import CertificationEngagement, { type EngagementUpdate } from '../components/workflows/CertificationEngagement'
import AccessPanel from '../components/access/AccessPanel'
import SubmissionChecklistEditor from '../components/SubmissionChecklistEditor'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { getApiErrorMessage } from '../api/errors'
import { formatDate } from '../utils/dateFormat'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import type {
  BaselineMigrationExecuteResponse,
  BaselineMigrationPreviewResponse,
  CertificationProjectBaselineUpdateResponse,
  CertificationProject,
  CertificationProjectSubmissionCycleResponse,
  CertificationProjectMilestone,
  ExportManifest,
  Jurisdiction,
  PaginatedResponse,
  RequirementSetSummary,
  ReviewCycle,
  SubmissionChecklist,
  SubmissionPackage,
  SubmissionPackageArtifact,
  SubmissionPackageGateCheck,
} from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { notifyApiError } from '../utils/notify'
import SectionNav from '../components/ui/SectionNav'
import Badge from '../components/ui/Badge'
import LoadError from '../components/ui/LoadError'
import Button from '../components/ui/Button'
import LinkButton from '../components/ui/LinkButton'
import Card from '../components/ui/Card'
import DecisionModal from '../components/ui/DecisionModal'
import Modal from '../components/ui/Modal'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { Table, TBody, TD, TH, THead, TR, TableEmpty } from '../components/ui/Table'

const stageLabel: Record<string, string> = {
  intake: 'Intake',
  scoping: 'Scoping',
  gap_assessment: 'Gap Assessment',
  remediation: 'Remediation',
  pre_audit: 'Pre-audit',
  submission: 'Submission',
  follow_up: 'Follow-up',
}

const stageOrder = [
  'intake',
  'scoping',
  'gap_assessment',
  'remediation',
  'pre_audit',
  'submission',
  'follow_up',
]

const stageTone = (stage: string): 'slate' | 'blue' | 'amber' | 'green' => {
  if (stage === 'submission' || stage === 'follow_up') return 'green'
  if (stage === 'gap_assessment' || stage === 'remediation') return 'amber'
  if (stage === 'intake') return 'slate'
  return 'blue'
}

const statusTone = (status: string): 'green' | 'amber' | 'slate' => {
  if (status === 'completed') return 'green'
  if (status === 'on_hold') return 'amber'
  return 'slate'
}

const packageStatusTone = (status: string): 'green' | 'amber' | 'slate' | 'blue' => {
  if (status === 'approved' || status === 'locked') return 'green'
  if (status === 'pending_approval') return 'amber'
  if (status === 'draft') return 'slate'
  return 'blue'
}

function formatStage(stage: string) {
  return stageLabel[stage] || stage.replace(/_/g, ' ')
}


function dateInputValue(value: string | null) {
  if (!value) return ''
  return new Date(value).toISOString().slice(0, 10)
}

type MilestoneDraft = {
  status: string
  due_at: string
  notes: string
}

type ArtifactDraft = {
  artifact_type: string
  name: string
  file_path: string
  link_url: string
  required: boolean
  included: boolean
  notes: string
}

const submissionChecklistItems = [
  {
    id: 'review-cycle-closed',
    label: 'Submission assessment is closed',
    required: true,
  },
  {
    id: 'snapshot-bound',
    label: 'Submission package is bound to the assessment snapshot',
    required: true,
  },
  {
    id: 'required-artifacts',
    label: 'All required documents are included',
    required: true,
  },
  {
    id: 'approver-ready',
    label: 'Approver notes are ready',
    required: false,
  },
]

function buildSubmissionChecklist(completedById: Record<string, boolean>): SubmissionChecklist {
  return {
    sections: [
      {
        id: 'submission-readiness',
        title: 'Submission readiness',
        items: submissionChecklistItems.map((item) => ({
          ...item,
          completed: Boolean(completedById[item.id]),
        })),
      },
    ],
  }
}

export default function CertificationProjects() {
  const toast = useToast()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [returnPackageId, setReturnPackageId] = useState<string | null>(null)
  const [returnReason, setReturnReason] = useState('')
  const [projectToDelete, setProjectToDelete] = useState<CertificationProject | null>(null)
  const selectedProjectId = searchParams.get('project')
  const sectionAliases: Record<string, string> = { baseline: 'requirements', review: 'requirements', forms: 'requirements', milestones: 'testing', packages: 'reports', maintenance: 'history' }
  const requestedSection = searchParams.get('section') || 'overview'
  const projectSection = sectionAliases[requestedSection] || (['overview', 'requirements', 'testing', 'reports', 'history'].includes(requestedSection) ? requestedSection : 'overview')
  const [milestonesExpanded, setMilestonesExpanded] = useState(requestedSection === 'milestones')
  useEffect(() => {
    if (requestedSection === 'milestones') setMilestonesExpanded(true)
  }, [requestedSection])
  const updateLocation = (key: string, value: string | null) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    })
  }
  const setSelectedProjectId = (value: string | null) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set('project', value)
      else next.delete('project')
      next.delete('section')
      return next
    })
  }
  const [projectDraft, setProjectDraft] = useState({ stage: 'intake', status: 'active' })
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null)
  const [createJurisdictionId, setCreateJurisdictionId] = useState<string>('')
  const [createBaselineSelection, setCreateBaselineSelection] = useState<string[]>([])
  const [baselineSelection, setBaselineSelection] = useState<string[]>([])
  const [baselineUpgrades, setBaselineUpgrades] = useState<Record<string, { id: string; number: number | null | undefined }>>({})
  const [confirmBaseline, setConfirmBaseline] = useState(false)
  const [migrationPreview, setMigrationPreview] = useState<BaselineMigrationPreviewResponse | null>(null)
  const [changedDecisions, setChangedDecisions] = useState<Record<string, 'reset_pending' | 'carry_forward'>>({})
  const [milestoneDrafts, setMilestoneDrafts] = useState<Record<string, MilestoneDraft>>({})
  const [artifactDrafts, setArtifactDrafts] = useState<Record<string, ArtifactDraft>>({})
  const [packageForm, setPackageForm] = useState({
    version: '',
  })
  const [packageChecklistState, setPackageChecklistState] = useState<Record<string, boolean>>({})
  const [artifactForm, setArtifactForm] = useState({
    artifact_type: 'report',
    name: '',
    file_path: '',
    link_url: '',
    required: false,
    included: true,
    notes: '',
  })
  const [manifestsByPackage, setManifestsByPackage] = useState<Record<string, ExportManifest>>({})

  const projectsQuery = useQuery({
    queryKey: ['certification-projects'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<CertificationProject>>(
        '/certification-projects?limit=1000'
      )
      return response.data
    },
  })

  const jurisdictionsQuery = useQuery({
    queryKey: ['jurisdictions', 'active'],
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<Jurisdiction>>('/jurisdictions?limit=1000')
      return response.data
    },
  })

  const requirementSetsQuery = useQuery({
    queryKey: ['requirements-sets', 'project-baselines'],
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      params.set('include_archived_documents', 'false')
      params.set('include_empty_sets', 'true')
      params.set('include_archived_sets', 'false')
      const response = await api.get<PaginatedResponse<RequirementSetSummary>>(
        `/requirements/sets?${params.toString()}`
      )
      return response.data
    },
  })

  const milestonesQuery = useQuery({
    queryKey: ['certification-project-milestones', selectedProjectId],
    enabled: !!selectedProjectId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<CertificationProjectMilestone>>(
        `/certification-projects/${selectedProjectId}/milestones`
      )
      return response.data
    },
  })

  const packagesQuery = useQuery({
    queryKey: ['submission-packages', selectedProjectId],
    enabled: !!selectedProjectId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<SubmissionPackage>>(
        `/submission-packages?project_id=${selectedProjectId}&limit=1000`
      )
      return response.data
    },
  })

  const artifactsQuery = useQuery({
    queryKey: ['submission-package-artifacts', selectedPackageId],
    enabled: !!selectedPackageId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<SubmissionPackageArtifact>>(
        `/submission-packages/${selectedPackageId}/artifacts`
      )
      return response.data
    },
  })

  const submissionCyclesQuery = useQuery({
    queryKey: ['review-cycles', 'project', selectedProjectId],
    enabled: !!selectedProjectId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<ReviewCycle>>(
        `/review-cycles?certification_project_id=${selectedProjectId}&limit=1000`
      )
      return response.data
    },
  })

  const selectedPackageGateCheckQuery = useQuery({
    queryKey: ['submission-package-gate-check', selectedPackageId],
    enabled: !!selectedPackageId,
    queryFn: async () => {
      const response = await api.get<SubmissionPackageGateCheck>(
        `/submission-packages/${selectedPackageId}/gate-check`
      )
      return response.data
    },
  })

  const createProjectMutation = useMutation({
    mutationFn: async (payload: {
      jurisdiction_id: string
      name: string
      description: string | null
      stage: string
      status: string
      target_submission_date: string | null
      requirement_set_ids: string[]
      assurance_type: 'test' | 'audit' | 'certification' | null
      provider_name: string | null
      assurance_scope: string | null
    }) => {
      const response = await api.post<CertificationProject>('/certification-projects', payload)
      return response.data
    },
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      if (project?.id) setSelectedProjectId(project.id)
      setShowCreateModal(false)
      setCreateBaselineSelection([])
      setBaselineSelection([])
      toast.success('Certification project created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create certification project')
    },
  })

  const ensureSubmissionCycleMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const response = await api.post<CertificationProjectSubmissionCycleResponse>(
        `/certification-projects/${projectId}/submission-cycle`
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles', 'project', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      if (data.created) {
        const count = data.review_items_created ?? 0
        toast.success(`Submission assessment created (${count} requirements)`)
        if (data.warning) {
          toast.info(data.warning)
        }
      } else {
        toast.info('Submission assessment already exists')
      }
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create submission assessment')
    },
  })

  const updateProjectMutation = useMutation({
    mutationFn: async (payload: {
      id: string
      stage: string
      status: string
    }) => {
      await api.patch(`/certification-projects/${payload.id}`, {
        stage: payload.stage,
        status: payload.status,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Project updated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update project')
    },
  })

  const updateEngagementMutation = useMutation({
    mutationFn: async (payload: { id: string; update: EngagementUpdate }) => {
      await api.patch(`/certification-projects/${payload.id}`, payload.update)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      toast.success('Engagement updated')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to update engagement'),
  })

  const deleteProjectMutation = useMutation({
    mutationFn: async (projectId: string) => {
      await api.delete(`/certification-projects/${projectId}`)
    },
    onSuccess: (_, projectId) => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      if (selectedProjectId === projectId) {
        setSelectedProjectId(null)
      }
      toast.success('Certification project deleted')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to delete certification project')
    },
  })

  const updateProjectBaselineMutation = useMutation({
    mutationFn: async (payload: { projectId: string; requirement_set_ids: string[]; target_version_ids: Record<string, string>; expected_baseline_version_ids: Record<string, string> }) => {
      const response = await api.put<CertificationProjectBaselineUpdateResponse>(
        `/certification-projects/${payload.projectId}/baseline`,
        { requirement_set_ids: payload.requirement_set_ids, target_version_ids: payload.target_version_ids, expected_baseline_version_ids: payload.expected_baseline_version_ids }
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles', 'project', selectedProjectId] })
      setBaselineSelection(data.project.requirement_set_ids || [])
      setBaselineUpgrades({})
      setConfirmBaseline(false)
      setMigrationPreview(null)
      setChangedDecisions({})
      if (data.warning) {
        toast.info(data.warning)
      } else {
        toast.success('Project baseline updated')
      }
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update project baseline')
    },
  })

  const previewBaselineMigrationMutation = useMutation({
    mutationFn: async (payload: { projectId: string; fromCycleId: string; requirement_set_ids: string[] }) => {
      const response = await api.post<BaselineMigrationPreviewResponse>(
        `/certification-projects/${payload.projectId}/baseline-migrations/preview`,
        {
          from_cycle_id: payload.fromCycleId,
          requirement_set_ids: payload.requirement_set_ids,
        }
      )
      return response.data
    },
    onSuccess: (data) => {
      setMigrationPreview(data)
      const nextDecisions: Record<string, 'reset_pending' | 'carry_forward'> = {}
      data.changed.forEach((item) => {
        if (item.new_requirement_id) nextDecisions[item.new_requirement_id] = 'reset_pending'
      })
      setChangedDecisions(nextDecisions)
      toast.success('Baseline migration preview generated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to preview baseline migration')
    },
  })

  const executeBaselineMigrationMutation = useMutation({
    mutationFn: async (payload: { projectId: string; migrationId: string }) => {
      const response = await api.post<BaselineMigrationExecuteResponse>(
        `/certification-projects/${payload.projectId}/baseline-migrations/execute`,
        {
          migration_id: payload.migrationId,
          changed_decisions: Object.entries(changedDecisions).map(([new_requirement_id, action]) => ({
            new_requirement_id,
            action,
          })),
        }
      )
      return response.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['review-cycles', 'project', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['review-cycles'] })
      setMigrationPreview(null)
      setChangedDecisions({})
      toast.success(`Successor assessment created (${data.migrated_items} items migrated)`)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to execute baseline migration')
    },
  })

  const updateMilestoneMutation = useMutation({
    mutationFn: async (payload: {
      project_id: string
      milestone_id: string
      status: string
      due_at: string | null
      notes: string | null
    }) => {
      await api.patch(
        `/certification-projects/${payload.project_id}/milestones/${payload.milestone_id}`,
        {
          status: payload.status,
          due_at: payload.due_at,
          notes: payload.notes,
        }
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certification-project-milestones', selectedProjectId] })
      toast.success('Milestone updated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update milestone')
    },
  })

  const createPackageMutation = useMutation({
    mutationFn: async (payload: {
      project_id: string
      review_cycle_id: string | null
      version: string
      status: string
      checklist: SubmissionChecklist
    }) => {
      return (await api.post<SubmissionPackage>('/submission-packages', payload)).data
    },
    onSuccess: (createdPackage) => {
      if (createdPackage?.id) setSelectedPackageId(createdPackage.id)
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      setPackageForm({ version: '' })
      setPackageChecklistState({})
      toast.success('Submission package created')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to create submission package')
    },
  })

  const saveChecklistMutation = useMutation({
    mutationFn: async (checklist: SubmissionChecklist) => { await api.patch(`/submission-packages/${selectedPackageId}`, { checklist }) },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      toast.success('Package checklist saved')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Checklist could not be saved'),
  })
  const returnPackageMutation = useMutation({
    mutationFn: async () => { await api.post(`/submission-packages/${returnPackageId}/return-to-draft`, { reason: returnReason.trim() }) },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      setReturnPackageId(null); setReturnReason('')
      toast.success('Package returned to draft', { description: 'Approval is cleared. Request a new approval after making changes.' })
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Package could not be returned to draft'),
  })

  const createArtifactMutation = useMutation({
    mutationFn: async (payload: {
      package_id: string
      artifact_type: string
      name: string
      file_path: string | null
      link_url: string | null
      required: boolean
      included: boolean
      notes: string | null
    }) => {
      await api.post(`/submission-packages/${payload.package_id}/artifacts`, {
        artifact_type: payload.artifact_type,
        name: payload.name,
        file_path: payload.file_path,
        link_url: payload.link_url,
        required: payload.required,
        included: payload.included,
        notes: payload.notes,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-package-artifacts', selectedPackageId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      setArtifactForm({
        artifact_type: 'report',
        name: '',
        file_path: '',
        link_url: '',
        required: false,
        included: true,
        notes: '',
      })
      toast.success('Document added')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to add document')
    },
  })

  const updateArtifactMutation = useMutation({
    mutationFn: async (payload: { package_id: string; artifact_id: string; draft: ArtifactDraft }) => {
      await api.patch(
        `/submission-packages/${payload.package_id}/artifacts/${payload.artifact_id}`,
        {
          artifact_type: payload.draft.artifact_type,
          name: payload.draft.name,
          file_path: payload.draft.file_path || null,
          link_url: payload.draft.link_url || null,
          required: payload.draft.required,
          included: payload.draft.included,
          notes: payload.draft.notes.trim() || null,
        }
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-package-artifacts', selectedPackageId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      toast.success('Document updated')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to update document')
    },
  })

  const createBundleManifestMutation = useMutation({
    mutationFn: async (packageId: string) => {
      const response = await api.post<ExportManifest>(`/submission-packages/${packageId}/bundle-manifest`)
      return response.data
    },
    onSuccess: (manifest, packageId) => {
      setManifestsByPackage((current) => ({ ...current, [packageId]: manifest }))
      toast.success('Bundle manifest generated')
      const url = URL.createObjectURL(new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a'); link.href = url; link.download = 'submission-manifest.json'; link.click(); URL.revokeObjectURL(url)
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to generate bundle manifest')
    },
  })

  const requestApprovalMutation = useMutation({
    mutationFn: async (packageId: string) => {
      await api.post(`/submission-packages/${packageId}/request-approval`)
    },
    onSuccess: (_, packageId) => {
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', packageId] })
      toast.success('Submission package moved to pending approval')
    },
    onError: (error: unknown, packageId) => {
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', packageId] })
      notifyApiError(toast, error, 'Failed to request approval')
    },
  })

  const approvePackageMutation = useMutation({
    mutationFn: async (packageId: string) => {
      await api.post(`/submission-packages/${packageId}/approve`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      toast.success('Submission package approved')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to approve submission package')
    },
  })

  const lockPackageMutation = useMutation({
    mutationFn: async (packageId: string) => {
      await api.post(`/submission-packages/${packageId}/lock`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['submission-packages', selectedProjectId] })
      queryClient.invalidateQueries({ queryKey: ['submission-package-gate-check', selectedPackageId] })
      queryClient.invalidateQueries({ queryKey: ['certification-projects'] })
      queryClient.invalidateQueries({ queryKey: ['program-workspace-summary'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      toast.success('Submission package locked and project handed over to maintenance')
    },
    onError: (error: unknown) => {
      notifyApiError(toast, error, 'Failed to lock submission package')
    },
  })

  const projects = useMemo(() => projectsQuery.data?.items ?? [], [projectsQuery.data?.items])
  const projectJurisdiction = searchParams.get('jurisdiction') || jurisdictionId
  const filteredProjects = projects.filter((project) =>
    project.name.toLowerCase().includes((searchParams.get('q') || '').toLowerCase()) &&
    (projectJurisdiction === 'all' || !projectJurisdiction || project.jurisdiction_id === projectJurisdiction) &&
    (!searchParams.get('status') || project.status === searchParams.get('status'))
  )
  const jurisdictionsById = useMemo(() => {
    const map: Record<string, Jurisdiction> = {}
    ;(jurisdictionsQuery.data?.items ?? []).forEach((j) => {
      map[j.id] = j
    })
    return map
  }, [jurisdictionsQuery.data?.items])
  const requirementSets = useMemo(() => requirementSetsQuery.data?.items ?? [], [requirementSetsQuery.data?.items])
  const requirementSetNameById = useMemo(() => {
    const map: Record<string, string> = {}
    requirementSets.forEach((set) => {
      map[set.document_id] = set.name || set.filename || 'Requirement set'
    })
    return map
  }, [requirementSets])

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  )
  const submissionCycle = useMemo(
    () =>
      (submissionCyclesQuery.data?.items ?? []).find(
        (cycle) => cycle.cycle_type === 'submission'
      ) || null,
    [submissionCyclesQuery.data?.items]
  )
  const submissionPackages = useMemo(() => packagesQuery.data?.items ?? [], [packagesQuery.data?.items])
  const selectedPackage = useMemo(
    () => submissionPackages.find((item) => item.id === selectedPackageId) || null,
    [submissionPackages, selectedPackageId]
  )
  const artifacts = useMemo(() => artifactsQuery.data?.items ?? [], [artifactsQuery.data?.items])
  const gateCheckData = selectedPackageGateCheckQuery.data
  const selectedPackageGateCheck = selectedPackageGateCheckQuery.isSuccess &&
    gateCheckData?.package_id === selectedPackage?.id &&
    gateCheckData?.project_id === selectedProjectId &&
    gateCheckData?.status === selectedPackage?.status ? gateCheckData : null
  // Requesting approval can bind an existing closed assessment and its snapshot.
  // Only those exact blockers are recoverable by that server action.
  const linkableSubmissionCycles = (submissionCyclesQuery.data?.items ?? []).filter(
    (cycle) => cycle.cycle_type === 'submission' && cycle.status !== 'archived'
  )
  const linkableSubmissionCycle = linkableSubmissionCycles.length === 1 ? linkableSubmissionCycles[0] : null
  const canAutoLinkAssessment = selectedPackage?.status === 'draft' && !selectedPackage.review_cycle_id &&
    submissionCyclesQuery.isSuccess && !submissionCyclesQuery.isFetching &&
    linkableSubmissionCycle?.status === 'closed' && !!linkableSubmissionCycle.snapshot_id &&
    (!selectedPackage.snapshot_id || selectedPackage.snapshot_id === linkableSubmissionCycle.snapshot_id)
  const canAutoBindSnapshot = selectedPackage?.status === 'draft' && !selectedPackage.snapshot_id && (
    canAutoLinkAssessment || (selectedPackageGateCheck?.review_cycle_linked &&
      selectedPackageGateCheck.review_cycle_closed && !!selectedPackageGateCheck.review_cycle_snapshot_id)
  )
  const approvalBlockingReasons = selectedPackageGateCheck?.blocking_reasons.filter((reason) =>
    !(canAutoLinkAssessment && reason === 'Submission package is not linked to a submission review cycle.') &&
    !(canAutoBindSnapshot && reason === 'Submission package is not bound to a snapshot.')
  ) ?? []
  const packageReadyForApproval = !!selectedPackageGateCheck && (
    selectedPackageGateCheck.checks_passed ||
    (selectedPackageGateCheck.blocking_reasons.length > 0 && approvalBlockingReasons.length === 0)
  )
  const packageReadinessBusy = selectedPackageGateCheckQuery.isFetching ||
    saveChecklistMutation.isPending || createArtifactMutation.isPending || updateArtifactMutation.isPending
  const assessmentRemediationId = selectedPackageGateCheck?.review_cycle_linked
    ? selectedPackage?.review_cycle_id : linkableSubmissionCycle?.id
  const focusPackageSection = (section: 'checklist' | 'documents') => {
    const target = document.getElementById(`package-${section}-${selectedPackageId}`)
    target?.focus()
    target?.scrollIntoView?.({ block: 'start' })
  }
  const canApprovePackages = selectedProject?.access ? (user?.role === 'approver' || user?.role === 'admin') && selectedProject.access.permissions.includes('approve') : user?.role === 'approver' || user?.role === 'admin'
  const canManageProjects = selectedProject?.access ? (user?.role === 'manager' || user?.role === 'admin') && selectedProject.access.permissions.includes('edit') : user?.role === 'manager' || user?.role === 'admin'
  const canManagePackages = canManageProjects
  const selectedProjectApprovedSets = useMemo(() => {
    if (!selectedProject) return []
    return requirementSets.filter(
      (set) =>
        set.document_status === 'approved' &&
        set.jurisdiction_id === selectedProject.jurisdiction_id
    )
  }, [requirementSets, selectedProject])
  const currentBaseline = selectedProject?.baseline_versions || []
  const currentBaselineIds = currentBaseline.map((item) => item.document_id)
  const baselineChanged = baselineSelection.length !== currentBaselineIds.length || baselineSelection.some((id) => !currentBaselineIds.includes(id)) || Object.keys(baselineUpgrades).some((id) => baselineSelection.includes(id))
  const baselineOptions = [
    ...selectedProjectApprovedSets,
    ...currentBaseline.filter((item) => !selectedProjectApprovedSets.some((set) => set.document_id === item.document_id)).map((item) => ({ document_id: item.document_id, name: item.set_name || requirementSetNameById[item.document_id], filename: '', current_version_id: null, current_version_number: null })),
  ]
  const staleBaselineUpgrade = Object.entries(baselineUpgrades).some(([id, version]) => baselineSelection.includes(id) && selectedProjectApprovedSets.find((set) => set.document_id === id)?.current_version_id !== version.id)
  const baselineChanges = baselineSelection.map((id) => {
    const current = currentBaseline.find((item) => item.document_id === id)
    const approved = selectedProjectApprovedSets.find((set) => set.document_id === id)
    const name = current?.set_name || approved?.name || approved?.filename || id
    return !current ? `Add ${name}: approved v${approved?.current_version_number ?? '?'}` : baselineUpgrades[id] ? `${name}: current v${current.version_number} → proposed v${baselineUpgrades[id].number ?? '?'}` : null
  }).filter((change): change is string => Boolean(change))
  currentBaseline.filter((item) => !baselineSelection.includes(item.document_id)).forEach((item) => baselineChanges.push(`Remove ${item.set_name || item.document_id} v${item.version_number}`))
  const canSaveBaseline = canManageProjects && baselineChanged && !staleBaselineUpgrade && baselineSelection.length > 0 && baselineSelection.every((id) => currentBaselineIds.includes(id) || selectedProjectApprovedSets.some((set) => set.document_id === id && set.current_version_id))
  const createModalSets = useMemo(() => {
    if (!createJurisdictionId) return []
    return requirementSets.filter(
      (set) =>
        set.document_status === 'approved' &&
        set.jurisdiction_id === createJurisdictionId
    )
  }, [createJurisdictionId, requirementSets])

  useEffect(() => {
    if (selectedProject && selectedProject.jurisdiction_id !== jurisdictionId) setJurisdictionId(selectedProject.jurisdiction_id)
  }, [selectedProject, jurisdictionId, setJurisdictionId])

  useEffect(() => {
    if (selectedProject) setProjectDraft({ stage: selectedProject.stage, status: selectedProject.status })
  }, [selectedProject])

  useEffect(() => {
    if (showCreateModal) return
    const first = jurisdictionId || jurisdictionsQuery.data?.items?.[0]?.id
    if (first) {
      setCreateJurisdictionId(first)
    }
  }, [jurisdictionId, jurisdictionsQuery.data?.items, showCreateModal])

  useEffect(() => {
    const allowedIds = new Set(createModalSets.map((set) => set.document_id))
    setCreateBaselineSelection((current) => current.filter((id) => allowedIds.has(id)))
  }, [createModalSets])

  useEffect(() => {
    setSelectedPackageId(null)
    setArtifactDrafts({})
    setMigrationPreview(null)
    setChangedDecisions({})
  }, [selectedProjectId])

  useEffect(() => {
    if (!selectedProjectId) return
    if (selectedPackageId && submissionPackages.some((pkg) => pkg.id === selectedPackageId)) return
    setSelectedPackageId(submissionPackages[0]?.id ?? null)
  }, [selectedPackageId, selectedProjectId, submissionPackages])

  useEffect(() => {
    setBaselineUpgrades({})
    setConfirmBaseline(false)
    if (!selectedProject) {
      setBaselineSelection([])
      return
    }
    if (selectedProject.requirement_set_ids?.length) {
      setBaselineSelection(selectedProject.requirement_set_ids)
      return
    }
    const fromVersions = (selectedProject.baseline_versions || []).map((item) => item.document_id)
    setBaselineSelection(fromVersions)
  }, [selectedProject])

  useEffect(() => {
    setMilestoneDrafts((current) => {
      const next: Record<string, MilestoneDraft> = {}
      ;(milestonesQuery.data?.items ?? []).forEach((milestone) => {
        const existing = current[milestone.id]
        next[milestone.id] = existing || {
          status: milestone.status,
          due_at: dateInputValue(milestone.due_at),
          notes: milestone.notes || '',
        }
      })
      return next
    })
  }, [milestonesQuery.data?.items])

  useEffect(() => {
    setArtifactDrafts((current) => {
      const next: Record<string, ArtifactDraft> = {}
      artifacts.forEach((artifact) => {
        const existing = current[artifact.id]
        next[artifact.id] = existing || {
          artifact_type: artifact.artifact_type,
          name: artifact.name,
          file_path: artifact.file_path || '',
          link_url: artifact.link_url || '',
          required: artifact.required,
          included: artifact.included,
          notes: artifact.notes || '',
        }
      })
      return next
    })
  }, [artifacts])

  const handleCreateProject = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formData = new FormData(e.currentTarget)
    const jurisdiction_id = String(formData.get('jurisdiction_id') || '')
    const name = String(formData.get('name') || '').trim()
    const descriptionRaw = String(formData.get('description') || '').trim()
    const targetSubmissionRaw = String(formData.get('target_submission_date') || '').trim()
    const requirement_set_ids = createBaselineSelection

    if (!jurisdiction_id || !name) {
      toast.error('Jurisdiction and project name are required.')
      return
    }
    createProjectMutation.mutate({
      jurisdiction_id,
      name,
      description: descriptionRaw || null,
      stage: 'intake',
      status: 'active',
      target_submission_date: targetSubmissionRaw ? new Date(targetSubmissionRaw).toISOString() : null,
      requirement_set_ids,
      assurance_type: (String(formData.get('assurance_type') || '') || null) as 'test' | 'audit' | 'certification' | null,
      provider_name: String(formData.get('provider_name') || '').trim() || null,
      assurance_scope: String(formData.get('assurance_scope') || '').trim() || null,
    })
  }

  const handleCreatePackage = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!selectedProjectId) {
      toast.error('Select a project first.')
      return
    }
    const version = packageForm.version.trim()
    if (!version) {
      toast.error('Package version is required.')
      return
    }
    createPackageMutation.mutate({
      project_id: selectedProjectId,
      review_cycle_id: submissionCycle?.id || null,
      version,
      status: 'draft',
      checklist: buildSubmissionChecklist(packageChecklistState),
    })
  }

  const handleCreateArtifact = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!selectedPackageId) {
      toast.error('Select a submission package first.')
      return
    }
    const name = artifactForm.name.trim()
    if (!name) {
      toast.error('Document name is required.')
      return
    }
    createArtifactMutation.mutate({
      package_id: selectedPackageId,
      artifact_type: artifactForm.artifact_type.trim() || 'report',
      name,
      file_path: artifactForm.file_path.trim() || null,
      link_url: artifactForm.link_url.trim() || null,
      required: artifactForm.required,
      included: artifactForm.included,
      notes: artifactForm.notes.trim() || null,
    })
  }

  const handleDeleteProject = (project: CertificationProject) => {
    if (!canManageProjects) return
    setProjectToDelete(project)
  }

  return (
    <div className="workflow-page certification-page min-w-0 space-y-4">
      {!selectedProjectId && <header className="py-1">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-ink">Certifications</h1>
            <p className="mt-1 text-sm text-muted">
              Track initial certification from intake through submission and follow-up.
            </p>
          </div>
          {canManageProjects && <Button
            variant="primary"
            onClick={() => {
              setCreateBaselineSelection([])
              setShowCreateModal(true)
            }}
          >
            Start certification
          </Button>}
        </div>
      </header>}

      {!selectedProjectId && <div className="workflow-toolbar flex flex-wrap items-end gap-3">
        <label className="w-full min-w-0 sm:w-auto sm:flex-1 text-sm text-muted">Search projects
          <input aria-label="Project name" value={searchParams.get('q') || ''} onChange={(e) => updateLocation('q', e.target.value)} placeholder="Project name" className="mt-1 block w-full px-3 py-2" />
        </label>
        <label className="w-full min-w-0 text-sm text-muted sm:w-auto">Jurisdiction
          <select value={searchParams.get('jurisdiction') || ''} onChange={(e) => updateLocation('jurisdiction', e.target.value)} className="mt-1 block w-full min-w-0 max-w-full px-3 py-2 sm:w-auto">
            <option value="">Current jurisdiction{jurisdictionId && jurisdictionById[jurisdictionId] ? `: ${jurisdictionById[jurisdictionId].name}` : ''}</option><option value="all">All jurisdictions</option>
            {(jurisdictionsQuery.data?.items ?? []).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
          </select>
        </label>
        <label className="w-full min-w-0 text-sm text-muted sm:w-auto">Project status
          <select value={searchParams.get('status') || ''} onChange={(e) => updateLocation('status', e.target.value)} className="mt-1 block w-full min-w-0 max-w-full px-3 py-2 sm:w-auto">
            <option value="">All statuses</option><option value="active">Active</option><option value="on_hold">On hold</option><option value="completed">Completed</option>
          </select>
        </label>
      </div>}
      {projectsQuery.isError ? <Card className="p-5"><p role="alert">Projects could not be loaded.</p><Button onClick={() => projectsQuery.refetch()}>Try again</Button></Card> : projectsQuery.isLoading ? (
        <Card className="p-6 text-sm text-muted">Loading projects...</Card>
      ) : !selectedProjectId ? (
        <Card className="overflow-hidden"><div className="workflow-table-heading"><h2>Certification projects</h2><p>{filteredProjects.length} matching {filteredProjects.length === 1 ? 'project' : 'projects'}</p></div>
          <div className="divide-y divide-line lg:hidden">{filteredProjects.map((project) => <article key={project.id} className="space-y-3 p-4"><button type="button" className="text-left text-base font-semibold text-accent" onClick={() => setSelectedProjectId(project.id)}>{project.name}</button><div className="flex flex-wrap gap-2"><Badge tone={stageTone(project.stage)}>{formatStage(project.stage)}</Badge><Badge tone={statusTone(project.status)}>{project.status.replace(/_/g, ' ')}</Badge></div><p className="text-sm text-muted">{jurisdictionsById[project.jurisdiction_id]?.name || 'Jurisdiction unavailable'} · Target {formatDate(project.target_submission_date)}</p><Button className="w-full" onClick={() => setSelectedProjectId(project.id)} aria-label={`Open ${project.name}`}>Open project</Button></article>)}{!filteredProjects.length && <p className="p-5 text-sm text-muted">{projects.length ? 'No projects match your filters.' : 'Create a certification project to select requirement sets and plan submission.'}</p>}</div>
          <div className="hidden overflow-x-auto lg:block"><Table>
            <THead>
              <tr>
                <TH>Project</TH>
                <TH>Jurisdiction</TH>
                <TH>Stage</TH>
                <TH>Status</TH>
                <TH>Target Submission</TH>
                <TH>Actions</TH>
              </tr>
            </THead>
            <TBody>
              {filteredProjects.map((project) => (
                <TR key={project.id}>
                  <TD>
                    <button
                      type="button"
                      className="text-left text-sm font-semibold text-ink hover:text-info"
                      onClick={() => setSelectedProjectId(project.id)}
                    >
                      {project.name}
                    </button>
                  </TD>
                  <TD className="text-muted">
                    {jurisdictionsById[project.jurisdiction_id]?.name || '-'}
                  </TD>
                  <TD>
                    <Badge tone={stageTone(project.stage)}>{formatStage(project.stage)}</Badge>
                  </TD>
                  <TD>
                    <Badge tone={statusTone(project.status)}>{project.status.replace(/_/g, ' ')}</Badge>
                  </TD>
                  <TD className="text-muted">{formatDate(project.target_submission_date)}</TD>
                  <TD>
                    <Button size="sm" onClick={() => setSelectedProjectId(project.id)} aria-label={`Open ${project.name}`}>Open project</Button>
                  </TD>
                </TR>
              ))}
              {filteredProjects.length === 0 ? <TableEmpty colSpan={6}>{projects.length ? 'No projects match these filters. Change the search or jurisdiction to see more.' : 'Create a certification project to select its requirement sets, plan milestones and prepare submission.'}</TableEmpty> : null}
            </TBody>
          </Table></div>
        </Card>
      ) : null}
      {selectedProjectId && !selectedProject && !projectsQuery.isLoading && !projectsQuery.isError && <Card className="p-5"><p role="alert">This project is unavailable.</p><Button onClick={() => setSelectedProjectId(null)}>Back to projects</Button></Card>}

      {selectedProject ? (
        <Card className="space-y-6 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-ink">{selectedProject.name}</h1>
              <p className="text-sm text-muted">
                Jurisdiction: {jurisdictionsById[selectedProject.jurisdiction_id]?.name || '-'}
              </p>
              {selectedProject.source_document_id ? (
                <p className="text-xs text-muted">
                  <Link className="underline" to={`/requirements/sets/${selectedProject.source_document_id}`}>{requirementSetNameById[selectedProject.source_document_id] || 'Open source requirement set'}</Link>
                </p>
              ) : null}
            </div>
            <Button variant="secondary" onClick={() => setSelectedProjectId(null)}>
              Back to projects
            </Button>
          </div>
          {selectedProject.access?.permissions.includes('manage_access') && <AccessPanel type="certification_project" id={selectedProject.id} />}
          <SectionNav label="Project sections" value={projectSection} onChange={(value) => updateLocation('section', value)} items={[
            { id: 'overview', label: 'Overview' }, { id: 'requirements', label: 'Requirements and evidence' }, { id: 'testing', label: 'Testing and findings' }, { id: 'reports', label: 'Reports and submission' }, { id: 'history', label: 'History' },
          ]} />
          <section hidden={projectSection !== 'overview'} aria-label="Project overview" className="space-y-5">
            <ol className="certification-progression" aria-label="Certification stages">{stageOrder.map(stage => <li key={stage} aria-current={selectedProject.stage === stage ? 'step' : undefined}>{stageLabel[stage]}{selectedProject.stage === stage && <span>Current stage</span>}</li>)}</ol>
            <div className="flex flex-wrap gap-6 text-sm">
              <div><span className="block text-muted">Stage</span><span className="font-semibold">{formatStage(selectedProject.stage)}</span></div>
              <div><span className="block text-muted">Status</span><span className="capitalize">{selectedProject.status.replace(/_/g, ' ')}</span></div>
              <div><span className="block text-muted">Target submission</span>{formatDate(selectedProject.target_submission_date)}</div>
            </div>
            {selectedProject.description && <p className="max-w-prose text-sm text-muted">{selectedProject.description}</p>}
            <div className="project-next-step space-y-3">
              <h2 className="font-semibold">Next step for this project</h2>
              <p className="text-sm text-muted">{(selectedProject.baseline_versions || []).length} requirement {(selectedProject.baseline_versions || []).length === 1 ? 'set' : 'sets'} in the baseline · {submissionCycle ? `Submission assessment ${submissionCycle.status}` : 'Submission assessment not started'} · {submissionPackages.length} submission packages</p>
              <div className="flex flex-wrap gap-2">
                {submissionCycle ? <LinkButton variant="primary" to={`/review-cycles/${submissionCycle.id}`}>Continue requirement assessment</LinkButton> : <Button variant="primary" onClick={() => updateLocation('section', 'requirements')}>{(selectedProject.baseline_versions || []).length ? 'Start requirement assessment' : 'Choose approved requirements'}</Button>}
                <Link to={`/program-workspace?project=${selectedProject.id}`} className="rounded-md border border-line-strong px-3 py-2 text-sm">View readiness and next actions</Link>
              </div>
            </div>
            {canManageProjects && <details open={projectDraft.stage !== selectedProject.stage || projectDraft.status !== selectedProject.status || undefined}><summary className="cursor-pointer text-sm font-semibold text-ink">Update project stage or status</summary><form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); updateProjectMutation.mutate({ id: selectedProject.id, ...projectDraft }) }}>
              <label className="text-sm text-muted">Project stage<select className="mt-1 block px-3 py-2" value={projectDraft.stage} onChange={(e) => setProjectDraft((draft) => ({ ...draft, stage: e.target.value }))}>{stageOrder.map((stage) => <option key={stage} value={stage}>{formatStage(stage)}</option>)}</select></label>
              <label className="text-sm text-muted">Project status<select className="mt-1 block px-3 py-2" value={projectDraft.status} onChange={(e) => setProjectDraft((draft) => ({ ...draft, status: e.target.value }))}><option value="active">Active</option><option value="on_hold">On hold</option><option value="completed">Completed</option></select></label>
              <Button type="submit" loading={updateProjectMutation.isPending} disabled={projectDraft.stage === selectedProject.stage && projectDraft.status === selectedProject.status}>Save project status</Button>
            </form></details>}
            {canManageProjects && <details className="border-t border-line pt-3"><summary className="cursor-pointer text-sm text-muted">Project administration</summary><div className="pt-3"><Button variant="destructive" size="sm" onClick={() => handleDeleteProject(selectedProject)} aria-label="Delete project">Delete project</Button></div></details>}
          </section>

          <section hidden={projectSection !== 'requirements'} aria-label="Project requirement sets" className="space-y-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-base font-semibold text-ink">Project baseline</h3>
              <Button variant="secondary" size="sm" loading={updateProjectBaselineMutation.isPending} disabled={!canSaveBaseline} onClick={() => setConfirmBaseline(true)}>Save baseline</Button>
            </div>
            <p className="text-sm text-muted">Current versions stay in place until you select an update. Existing assessments keep their original baseline.</p>
            <div className="space-y-3">
              {baselineOptions.map((set) => {
                const current = currentBaseline.find((item) => item.document_id === set.document_id)
                const selected = baselineSelection.includes(set.document_id)
                const upgradeAvailable = current && set.current_version_id && set.current_version_id !== current.requirement_set_version_id
                return <div key={set.document_id} className="space-y-2 border-b border-line pb-3">
                  <label className="flex items-start gap-2 text-sm text-ink"><input type="checkbox" disabled={!canManageProjects || updateProjectBaselineMutation.isPending} checked={selected} onChange={(event) => {
                    setBaselineSelection((ids) => event.target.checked ? [...ids, set.document_id] : ids.filter((id) => id !== set.document_id))
                    setBaselineUpgrades((values) => { const next = { ...values }; delete next[set.document_id]; return next })
                  }} /><span>{set.name || set.filename} · {current ? `Current v${current.version_number}` : `Approved v${set.current_version_number ?? '?'}`}{current && !selected ? ' · Proposed removal' : ''}</span></label>
                  {selected && upgradeAvailable && <label className="flex items-start gap-2 text-sm"><input type="checkbox" disabled={!canManageProjects || updateProjectBaselineMutation.isPending} checked={Boolean(baselineUpgrades[set.document_id])} onChange={(event) => setBaselineUpgrades((values) => { const next = { ...values }; if (event.target.checked) next[set.document_id] = { id: set.current_version_id!, number: set.current_version_number }; else delete next[set.document_id]; return next })} /><span>Update from v{current.version_number} to approved v{set.current_version_number}{baselineUpgrades[set.document_id] ? ' · Proposed update' : ''}</span></label>}
                </div>
              })}
              {baselineOptions.length === 0 && <p className="text-sm text-muted">No approved requirement sets in this jurisdiction.</p>}
            </div>
            {staleBaselineUpgrade && <p role="alert" className="text-sm text-warning">An approved version changed. Clear the proposed update and select the version you want before saving.</p>}
            {baselineChanged && <div className="space-y-2 text-sm"><p className="font-medium">Proposed changes</p><ul className="list-disc space-y-1 pl-5">{baselineChanges.map((change) => <li key={change}>{change}</li>)}</ul></div>}
            <ConfirmDialog open={confirmBaseline} title="Confirm project baseline changes" description="New assessments will use this baseline. Existing active and closed assessments keep their original versions and decisions. Use Preview migration to assess changes separately." dangerDetails={baselineChanges} confirmLabel="Confirm baseline changes" confirmVariant="primary" isWorking={updateProjectBaselineMutation.isPending} onClose={() => setConfirmBaseline(false)} onConfirm={() => {
              if (!canSaveBaseline) { setConfirmBaseline(false); return }
              const targetVersions = Object.fromEntries(Object.entries(baselineUpgrades).map(([id, version]) => [id, version.id]))
              baselineSelection.filter((id) => !currentBaselineIds.includes(id)).forEach((id) => { targetVersions[id] = selectedProjectApprovedSets.find((set) => set.document_id === id)!.current_version_id! })
              updateProjectBaselineMutation.mutate({ projectId: selectedProject.id, requirement_set_ids: baselineSelection, target_version_ids: targetVersions, expected_baseline_version_ids: Object.fromEntries(currentBaseline.map((item) => [item.document_id, item.requirement_set_version_id])) })
            }} />
            {(selectedProject.baseline_versions || []).length > 0 ? (
              <div className="mt-3 text-xs text-muted">
                Current project baseline:{' '}
                {(selectedProject.baseline_versions || [])
                  .map((item) => `${item.set_name || requirementSetNameById[item.document_id] || item.document_id} v${item.version_number}`)
                  .join(', ')}
              </div>
            ) : (
              <div className="mt-3 text-xs text-warning">
                Choose an approved requirement set to establish the project baseline before starting an assessment. If none is available, <Link className="underline" to="/requirements">create and approve a requirement set</Link> first.
              </div>
            )}
          </section>

          <section hidden={projectSection !== 'requirements'} aria-label="Project assessments" className="space-y-3 border-t border-line pt-4">
            <div className="border-b border-line pb-4"><h2 className="text-lg font-semibold">Requirement assessments</h2><p className="mt-1 text-sm text-muted">Work through requirements and record reviewer decisions for submission, changes and ongoing maintenance.</p></div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-ink">Submission assessment</h3>
                {submissionCyclesQuery.isError ? <LoadError subject="Submission assessment" onRetry={() => submissionCyclesQuery.refetch()} /> : submissionCyclesQuery.isLoading ? (
                  <p className="text-sm text-muted">Loading cycle...</p>
                ) : submissionCycle ? (
                  <div className="space-y-1">
                    <p className="text-sm text-muted">{submissionCycle.name}</p>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                      <Badge tone={submissionCycle.status === 'closed' ? 'green' : 'blue'}>
                        {submissionCycle.status}
                      </Badge>
                      <span>Type: {submissionCycle.cycle_type || 'submission'}</span>
                      <span>{submissionCycle.snapshot_id ? 'Assessment snapshot recorded' : 'Snapshot is created when the assessment closes'}</span>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted">
                    No submission assessment yet. Create one to assess this project’s approved requirements. Internal package approvals remain separate.
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {submissionCycle ? (
                  <Link
                    to={`/review-cycles/${submissionCycle.id}`}
                    className="inline-flex items-center rounded-md border border-line-strong px-3 py-2 text-sm font-medium text-ink hover:bg-canvas"
                  >
                    Open assessment
                  </Link>
                ) : null}
                {canManagePackages && !submissionCycle ? (
                  <Button
                    variant="primary"
                    loading={ensureSubmissionCycleMutation.isPending}
                    disabled={(selectedProject.baseline_versions || []).length === 0}
                    onClick={() => ensureSubmissionCycleMutation.mutate(selectedProject.id)}
                  >
                    Create submission assessment
                  </Button>
                ) : null}
                {canManagePackages && submissionCycle ? (
                  <Button
                    variant="secondary"
                    loading={previewBaselineMigrationMutation.isPending}
                    onClick={() =>
                      previewBaselineMigrationMutation.mutate({
                        projectId: selectedProject.id,
                        fromCycleId: submissionCycle.id,
                        requirement_set_ids: baselineSelection,
                      })
                    }
                    disabled={baselineSelection.length === 0}
                  >
                    Preview migration
                  </Button>
                ) : null}
              </div>
            </div>
            {submissionCycle && canManagePackages && <p className="text-sm text-muted">Preview migration compares this assessment with the latest approved versions of the selected requirement sets.</p>}
            {migrationPreview ? (
              <div className="mt-4 rounded-lg border border-line bg-canvas p-3">
                <div className="text-sm font-semibold text-ink">Migration Preview</div>
                <div className="mt-1 text-xs text-muted">
                  Matched: {migrationPreview.matched.length} | Changed: {migrationPreview.changed.length} | Added:{' '}
                  {migrationPreview.added.length} | Removed: {migrationPreview.removed.length}
                </div>
                {migrationPreview.changed.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {migrationPreview.changed.map((item) => (
                      <div
                        key={item.new_requirement_id || `${item.document_id}-${item.reference_id}`}
                        className="rounded-md border border-line bg-surface p-2 text-xs"
                      >
                        <div className="font-medium text-ink">{item.reference_id}</div>
                        <div className="text-muted">{item.set_name || item.document_id || 'Requirement set'}</div>
                        <div className="mt-1 text-muted">
                          Choose whether this changed requirement should start fresh or clone the prior assessment work.
                        </div>
                        <div className="mt-2 flex gap-3">
                          <label className="inline-flex items-center gap-1 text-ink">
                            <input
                              type="radio"
                              checked={(changedDecisions[item.new_requirement_id || ''] || 'reset_pending') === 'reset_pending'}
                              disabled={!item.new_requirement_id}
                              onChange={() => {
                                const requirementId = item.new_requirement_id
                                if (!requirementId) return
                                setChangedDecisions((current) => ({
                                  ...current,
                                  [requirementId]: 'reset_pending',
                                }))
                              }}
                            />
                            Reset pending
                          </label>
                          <label className="inline-flex items-center gap-1 text-ink">
                            <input
                              type="radio"
                              checked={changedDecisions[item.new_requirement_id || ''] === 'carry_forward'}
                              disabled={!item.new_requirement_id}
                              onChange={() => {
                                const requirementId = item.new_requirement_id
                                if (!requirementId) return
                                setChangedDecisions((current) => ({
                                  ...current,
                                  [requirementId]: 'carry_forward',
                                }))
                              }}
                            />
                            Carry forward
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 flex justify-end">
                  <Button
                    variant="secondary"
                    loading={executeBaselineMigrationMutation.isPending}
                    onClick={() =>
                      executeBaselineMigrationMutation.mutate({
                        projectId: selectedProject.id,
                        migrationId: migrationPreview.migration_id,
                      })
                    }
                  >
                    Execute migration
                  </Button>
                </div>
              </div>
            ) : null}
          </section>

          <section hidden={projectSection !== 'requirements'} aria-label="Project forms and evidence" className="border-t border-line pt-4"><ProjectForms key={`forms-${selectedProject.id}`} projectId={selectedProject.id} jurisdictionId={selectedProject.jurisdiction_id} canManage={canManageProjects} /></section>
          <section hidden={projectSection !== 'history'} aria-label="Project history" className="space-y-4"><h2 className="text-lg font-semibold">Earlier assessments and maintenance</h2>{(submissionCyclesQuery.data?.items || []).filter(cycle => cycle.id !== submissionCycle?.id).map(cycle => <div key={cycle.id} className="flex flex-wrap justify-between gap-2 border-b border-line py-3"><Link className="text-accent underline" to={`/review-cycles/${cycle.id}`}>{cycle.name}</Link><span className="text-sm text-muted">{cycle.cycle_type || 'Operational'} · {cycle.status}</span></div>)}<h3 className="font-semibold">Previous submission packages</h3>{submissionPackages.slice(1).map(pkg => <div key={pkg.id} className="flex justify-between border-b border-line py-2 text-sm"><span>Version {pkg.version}</span><span className="text-muted">{pkg.status}</span></div>)}<ProjectMaintenance key={`maintenance-${selectedProject.id}`} projectId={selectedProject.id} jurisdictionId={selectedProject.jurisdiction_id} canManage={canManageProjects} assessments={submissionCyclesQuery.data?.items || []} /></section>

          <section hidden={projectSection !== 'testing'} aria-label="Testing and findings" className="space-y-4">
            {submissionCycle && (
              <div className="flex flex-col gap-4 rounded-lg border border-line bg-subtle p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-ink">Assessment findings</h2>
                  <p className="text-sm text-muted">Track tests, reviewer decisions and findings against the pinned requirements.</p>
                </div>
                <LinkButton variant="primary" className="w-full shrink-0 sm:w-auto" to={`/review-cycles/${submissionCycle.id}`}>
                  Open assessment and findings
                </LinkButton>
              </div>
            )}
            <CertificationEngagement key={`testing-${selectedProject.id}`} mode="testing" project={selectedProject} canManage={canManageProjects} saving={updateEngagementMutation.isPending} onSave={(update) => updateEngagementMutation.mutateAsync({ id: selectedProject.id, update })} />
          </section>

          <section hidden={projectSection !== 'testing'} aria-label="Project milestones">
            <details open={milestonesExpanded} onToggle={(event) => setMilestonesExpanded(event.currentTarget.open)} className="rounded-lg border border-line p-3">
              <summary className="cursor-pointer text-sm font-semibold text-ink">Milestones · {(milestonesQuery.data?.items ?? []).filter((item) => item.status === 'done').length}/{(milestonesQuery.data?.items ?? []).length} done{(milestonesQuery.data?.items ?? []).some((item) => item.status === 'blocked') ? ' · blocked items' : ''}</summary>
              <p className="mt-2 text-xs text-muted">Timeline stages with editable status and due dates</p>
              <div className="mt-3">
            {milestonesQuery.isError ? <LoadError subject="Milestones" onRetry={() => milestonesQuery.refetch()} /> : milestonesQuery.isLoading ? (
              <p className="text-sm text-muted">Loading milestones...</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {(milestonesQuery.data?.items ?? []).map((milestone) => {
                  const draft = milestoneDrafts[milestone.id] || {
                    status: milestone.status,
                    due_at: dateInputValue(milestone.due_at),
                    notes: milestone.notes || '',
                  }
                  const dirty = draft.status !== milestone.status || draft.due_at !== dateInputValue(milestone.due_at) || draft.notes !== (milestone.notes || '')
                  return (
                    <div key={milestone.id} className="rounded-xl border border-line bg-surface p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold text-ink">{milestone.title}</div>
                        <Badge
                          tone={milestone.status === 'done' ? 'green' : milestone.status === 'blocked' ? 'amber' : 'slate'}
                        >
                          {milestone.status}
                        </Badge>
                      </div>
                      {dirty && <p className="mt-1 text-xs text-warning">Unsaved changes</p>}
                      <div className="mt-3 grid grid-cols-1 gap-2">
                        <label className="grid gap-1 text-xs font-medium text-muted">Status<select
                          aria-label={`Status for ${milestone.title}`}
                          disabled={!canManageProjects}
                          value={draft.status}
                          onChange={(e) =>
                            setMilestoneDrafts((current) => ({
                              ...current,
                              [milestone.id]: { ...draft, status: e.target.value },
                            }))
                          }
                          className="rounded-md border border-line-strong bg-surface px-2 py-1 text-xs text-ink"
                        >
                          <option value="pending">Pending</option>
                          <option value="done">Done</option>
                          <option value="blocked">Blocked</option>
                        </select></label>
                        <label className="grid gap-1 text-xs font-medium text-muted">Due date<input
                          type="date"
                          aria-label={`Due date for ${milestone.title}`}
                          disabled={!canManageProjects}
                          value={draft.due_at}
                          onChange={(e) =>
                            setMilestoneDrafts((current) => ({
                              ...current,
                              [milestone.id]: { ...draft, due_at: e.target.value },
                            }))
                          }
                          className="rounded-md border border-line-strong bg-surface px-2 py-1 text-xs text-ink"
                        />
                        </label><label className="grid gap-1 text-xs font-medium text-muted">Notes<textarea
                          rows={2}
                          aria-label={`Notes for ${milestone.title}`}
                          disabled={!canManageProjects}
                          value={draft.notes}
                          onChange={(e) =>
                            setMilestoneDrafts((current) => ({
                              ...current,
                              [milestone.id]: { ...draft, notes: e.target.value },
                            }))
                          }
                          className="rounded-md border border-line-strong bg-surface px-2 py-1 text-xs text-ink"
                          placeholder="Milestone notes"
                        />
                        </label><div className="flex justify-end">
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={!canManageProjects || !dirty}
                            loading={updateMilestoneMutation.isPending}
                            onClick={() =>
                              updateMilestoneMutation.mutate({
                                project_id: selectedProject.id,
                                milestone_id: milestone.id,
                                status: draft.status,
                                due_at: draft.due_at ? new Date(`${draft.due_at}T00:00:00Z`).toISOString() : null,
                                notes: draft.notes.trim() || null,
                              })
                            }
                          >
                            Save milestone
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
              </div>
            </details>
          </section>

          <section hidden={projectSection !== 'reports'} aria-label="Submission packages" className="space-y-3">
            <CertificationEngagement key={`report-${selectedProject.id}`} mode="report" project={selectedProject} canManage={canManageProjects} saving={updateEngagementMutation.isPending} onSave={(update) => updateEngagementMutation.mutateAsync({ id: selectedProject.id, update })} />
            <h3 className="text-base font-semibold text-ink">Submission packages</h3>
            <p className="text-sm text-muted">Package approval records an internal submission decision. Regulator approval is recorded separately.</p>
            {canManagePackages && <form onSubmit={handleCreatePackage} className="grid grid-cols-1 items-start gap-3 rounded-lg border border-line p-3 md:grid-cols-4">
              <label className="flex flex-col gap-1 text-sm text-muted"><span>Package version</span><input aria-label="Package version"
                id="submission-package-version"
                required
                value={packageForm.version}
                onChange={(e) => setPackageForm((current) => ({ ...current, version: e.target.value }))}
                className="rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                placeholder="Version (e.g. v1)"
              /></label>
              <div className="rounded-md border border-line bg-canvas p-3 md:col-span-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Submission checklist
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {submissionChecklistItems.map((item) => (
                    <label key={item.id} className="flex min-h-9 items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={Boolean(packageChecklistState[item.id])}
                        onChange={(event) =>
                          setPackageChecklistState((current) => ({
                            ...current,
                            [item.id]: event.target.checked,
                          }))
                        }
                        className="h-4 w-4 rounded border-line-strong text-info"
                      />
                      <span>
                        {item.label}
                        {!item.required ? <span className="text-faint"> (optional)</span> : null}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="md:col-span-4 flex justify-end">
                <Button variant="secondary" type="submit" loading={createPackageMutation.isPending}>
                  Add package
                </Button>
              </div>
            </form>}

            {packagesQuery.isError ? <LoadError subject="Submission packages" onRetry={() => packagesQuery.refetch()} /> : packagesQuery.isLoading ? (
              <p className="text-sm text-muted">Loading submission packages...</p>
            ) : submissionPackages.length === 0 ? (
              <p className="text-sm text-muted">No submission packages yet.</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {submissionPackages.map((pkg) => (
                  <div
                    key={pkg.id}
                    className={`rounded-xl border p-3 ${
                      selectedPackageId === pkg.id ? 'border-info-line bg-info-soft/40' : 'border-line bg-surface'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="text-sm font-semibold text-ink hover:text-info"
                        aria-pressed={selectedPackageId === pkg.id}
                        onClick={() => setSelectedPackageId(pkg.id)}
                      >
                        {pkg.version}
                      </button>
                      <Badge tone={packageStatusTone(pkg.status)}>{pkg.status}</Badge>
                    </div>
                    <div className="mt-1 text-xs text-muted">Created: {formatDate(pkg.created_at)}</div>
                    <div className="mt-1 text-xs text-muted">
                      Assessment: {pkg.review_cycle_id ? (pkg.review_cycle_id === submissionCycle?.id ? submissionCycle.name : 'Linked assessment') : 'not linked'}
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {pkg.snapshot_id ? 'Assessment snapshot attached' : 'Assessment snapshot not attached'}
                    </div>
                    {pkg.checklist_completion ? (
                      <div className="mt-1 text-xs text-muted">
                        Checklist: {pkg.checklist_completion.required_completed}/
                        {pkg.checklist_completion.required_total} required
                      </div>
                    ) : null}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {(canManagePackages || canApprovePackages) && ['pending_approval', 'approved'].includes(pkg.status) && <Button size="sm" onClick={() => { setReturnPackageId(pkg.id); setReturnReason('') }}>Return to draft</Button>}
                      {selectedPackageId !== pkg.id && <Button size="sm" onClick={() => setSelectedPackageId(pkg.id)}>Review package</Button>}
                      {canApprovePackages && pkg.status === 'pending_approval' ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={approvePackageMutation.isPending}
                          onClick={() => approvePackageMutation.mutate(pkg.id)}
                        >
                          Approve
                        </Button>
                      ) : null}
                      {canApprovePackages && pkg.status === 'approved' ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={lockPackageMutation.isPending}
                          onClick={() => lockPackageMutation.mutate(pkg.id)}
                        >
                          Lock + handoff
                        </Button>
                      ) : null}
                      {pkg.review_cycle_id ? (
                        <Link
                          to={`/review-cycles/${pkg.review_cycle_id}`}
                          className="inline-flex items-center rounded-md border border-line-strong px-2 py-1 text-xs font-medium text-ink hover:bg-canvas"
                        >
                          Open assessment
                        </Link>
                      ) : null}
                      <Button
                        disabled={!canManagePackages && !canApprovePackages}
                        variant="secondary"
                        size="sm"
                        loading={createBundleManifestMutation.isPending}
                        onClick={() => createBundleManifestMutation.mutate(pkg.id)}
                      >
                        Download manifest
                      </Button>
                    </div>
                    {manifestsByPackage[pkg.id] ? (
                      <div className="mt-2 text-xs text-muted">
                        Latest manifest: {manifestsByPackage[pkg.id].id}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

          {selectedPackage ? (
            <div className="space-y-3 border-t border-line pt-4">
              <section aria-labelledby="package-readiness-heading" className="space-y-3 pb-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 id="package-readiness-heading" className="text-base font-semibold text-ink">Readiness for {selectedPackage.version}</h3>
                    {selectedPackageGateCheck && !packageReadinessBusy && <Badge tone={packageReadyForApproval ? 'green' : 'amber'}>{packageReadyForApproval ? (selectedPackage.status === 'draft' ? 'Ready for internal approval' : 'Checks passed') : 'Needs attention'}</Badge>}
                  </div>
                  {canManagePackages && selectedPackage.status === 'draft' && <Button
                    variant="primary"
                    loading={requestApprovalMutation.isPending}
                    disabled={packageReadinessBusy || !packageReadyForApproval}
                    aria-describedby="package-approval-guidance"
                    onClick={() => requestApprovalMutation.mutate(selectedPackage.id)}
                  >Request approval</Button>}
                </div>
                {selectedPackageGateCheckQuery.isError ? <div id="package-approval-guidance"><LoadError subject="Submission readiness" onRetry={() => selectedPackageGateCheckQuery.refetch()} /></div> : packageReadinessBusy ? (
                  <p id="package-approval-guidance" role="status" className="text-sm text-muted">Checking package readiness before approval…</p>
                ) : selectedPackageGateCheck ? <>
                  <p id="package-approval-guidance" className="text-sm text-muted">{packageReadyForApproval ? `${selectedPackage.status === 'draft' ? 'The package can proceed to internal approval.' : 'The package meets the loaded submission checks.'} Approval and locking remain separate from the external certification outcome.` : 'Resolve the checks below before requesting internal approval.'}</p>
                  {packageReadyForApproval && canAutoBindSnapshot && <p className="text-sm text-muted">{canAutoLinkAssessment ? 'The closed submission assessment and its snapshot will be attached when you request approval.' : 'The closed assessment snapshot will be attached when you request approval.'}</p>}
                  <p className="text-sm text-muted">Required documents: {selectedPackageGateCheck.required_artifacts_included}/{selectedPackageGateCheck.required_artifacts_total} included{selectedPackageGateCheck.checklist_required_total !== undefined ? ` · Checklist: ${selectedPackageGateCheck.checklist_required_completed ?? 0}/${selectedPackageGateCheck.checklist_required_total} required complete` : ''}</p>
                  {approvalBlockingReasons.length > 0 && <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{approvalBlockingReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
                  {(selectedPackageGateCheck.checklist_blocking_items || []).length > 0 && <p className="text-sm text-muted">Incomplete checklist items: {selectedPackageGateCheck.checklist_blocking_items?.join(', ')}</p>}
                  <div className="flex flex-wrap gap-2">
                    {approvalBlockingReasons.some((reason) => /review|snapshot/i.test(reason)) && (assessmentRemediationId ? <LinkButton size="sm" to={`/review-cycles/${assessmentRemediationId}`}>Open submission assessment</LinkButton> : <Button size="sm" onClick={() => updateLocation('section', 'requirements')}>Set up submission assessment</Button>)}
                    {canManagePackages && approvalBlockingReasons.includes('Submission package snapshot does not match submission review cycle snapshot.') && <Button size="sm" onClick={() => document.getElementById('submission-package-version')?.focus()}>Create a new package version</Button>}
                    {selectedPackageGateCheck.missing_required_artifacts.length > 0 && <Button size="sm" onClick={() => focusPackageSection('documents')}>Update required documents</Button>}
                    {((selectedPackageGateCheck.checklist_blocking_items || []).length > 0 || approvalBlockingReasons.some((reason) => /checklist/i.test(reason))) && <Button size="sm" onClick={() => focusPackageSection('checklist')}>Complete package checklist</Button>}
                    <Button variant="ghost" size="sm" onClick={() => selectedPackageGateCheckQuery.refetch()}>Refresh readiness</Button>
                  </div>
                </> : <div id="package-approval-guidance"><LoadError subject="Submission readiness" onRetry={() => selectedPackageGateCheckQuery.refetch()} /></div>}
              </section>
              <div id={`package-checklist-${selectedPackage.id}`} tabIndex={-1} aria-label={`Checklist for ${selectedPackage.version}`}>
                <SubmissionChecklistEditor key={`${selectedPackage.id}-${selectedPackage.status}`} checklist={selectedPackage.checklist || buildSubmissionChecklist({})} readOnly={!canManagePackages || selectedPackage.status !== 'draft'} saving={saveChecklistMutation.isPending} onSave={(checklist) => saveChecklistMutation.mutateAsync(checklist)} />
              </div>
              <h3 id={`package-documents-${selectedPackage.id}`} tabIndex={-1} className="text-base font-semibold text-ink">Documents for {selectedPackage.version}</h3>
              <p className="text-sm text-muted">These are references to controlled files or document links. The manifest records them; use assessment reports for the downloadable evidence ZIP.</p>
              {selectedPackage.review_cycle_id && <Link to={`/reports?section=reviews&review=${selectedPackage.review_cycle_id}`} className="inline-block text-sm font-semibold text-accent underline">Open assessment reports and evidence package</Link>}
              {selectedPackage.status !== 'draft' && <p className="text-sm text-muted">{selectedPackage.status === 'locked' ? 'This package is locked. Create a new package version for further work.' : 'Return this package to draft before changing its contents.'}</p>}
              {canManagePackages && selectedPackage.status === 'draft' && <form onSubmit={handleCreateArtifact} className="grid grid-cols-1 gap-2 rounded-lg border border-line p-3 md:grid-cols-3">
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted "><span>Document type</span><input aria-label="Document type"
                  value={artifactForm.artifact_type}
                  onChange={(e) =>
                    setArtifactForm((current) => ({ ...current, artifact_type: e.target.value }))
                  }
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                  placeholder="Document type"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted "><span>Document name</span><input aria-label="Document name"
                  value={artifactForm.name}
                  onChange={(e) => setArtifactForm((current) => ({ ...current, name: e.target.value }))}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                  placeholder="Document name"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted "><span>Link URL (optional)</span><input aria-label="Link URL (optional)"
                  value={artifactForm.link_url}
                  onChange={(e) => setArtifactForm((current) => ({ ...current, link_url: e.target.value }))}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                  placeholder="Link URL (optional)"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>File reference (optional)</span><input aria-label="File reference (optional)"
                  value={artifactForm.file_path}
                  onChange={(e) => setArtifactForm((current) => ({ ...current, file_path: e.target.value }))}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                  placeholder="File path (optional)"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted "><span>Notes (optional)</span><input aria-label="Notes (optional)"
                  value={artifactForm.notes}
                  onChange={(e) => setArtifactForm((current) => ({ ...current, notes: e.target.value }))}
                  className="w-full rounded-md border border-line-strong px-3 py-2 text-sm text-ink"
                  placeholder="Notes (optional)"
                /></label>
                <label className="inline-flex items-center gap-2 text-xs text-ink">
                  <input
                    type="checkbox"
                    checked={artifactForm.required}
                    onChange={(e) =>
                      setArtifactForm((current) => ({ ...current, required: e.target.checked }))
                    }
                  />
                  Required
                </label>
                <label className="inline-flex items-center gap-2 text-xs text-ink">
                  <input
                    type="checkbox"
                    checked={artifactForm.included}
                    onChange={(e) =>
                      setArtifactForm((current) => ({ ...current, included: e.target.checked }))
                    }
                  />
                  Included
                </label>
                <div className="md:col-span-3 flex justify-end">
                  <Button variant="secondary" type="submit" loading={createArtifactMutation.isPending}>
                    Add document
                  </Button>
                </div>
              </form>}

              {artifactsQuery.isError ? <LoadError subject="Package documents" onRetry={() => artifactsQuery.refetch()} /> : artifactsQuery.isLoading ? (
                <p className="text-sm text-muted">Loading documents...</p>
              ) : artifacts.length === 0 ? (
                <p className="text-sm text-muted">No documents yet.</p>
              ) : (
                <div className="space-y-2">
                  {artifacts.map((artifact) => {
                    const draft = artifactDrafts[artifact.id] || {
                      artifact_type: artifact.artifact_type,
                      name: artifact.name,
                      file_path: artifact.file_path || '',
                      link_url: artifact.link_url || '',
                      required: artifact.required,
                      included: artifact.included,
                      notes: artifact.notes || '',
                    }
                    return (
                      <fieldset disabled={!canManagePackages || selectedPackage.status !== 'draft'} key={artifact.id} className="grid grid-cols-1 gap-2 rounded-lg border border-line bg-surface p-3 md:grid-cols-6">
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted "><span>Document type</span><input aria-label="Document type"
                          value={draft.artifact_type}
                          onChange={(e) =>
                            setArtifactDrafts((current) => ({
                              ...current,
                              [artifact.id]: { ...draft, artifact_type: e.target.value },
                            }))
                          }
                          className="w-full rounded-md border border-line-strong px-2 py-1 text-xs text-ink"
                        /></label>
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Document name</span><input aria-label="Document name"
                          value={draft.name}
                          onChange={(e) =>
                            setArtifactDrafts((current) => ({
                              ...current,
                              [artifact.id]: { ...draft, name: e.target.value },
                            }))
                          }
                          className="w-full rounded-md border border-line-strong px-2 py-1 text-xs text-ink"
                        /></label>
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Notes (optional)</span><input aria-label="Notes (optional)"
                          value={draft.notes}
                          onChange={(e) =>
                            setArtifactDrafts((current) => ({
                              ...current,
                              [artifact.id]: { ...draft, notes: e.target.value },
                            }))
                          }
                          className="w-full rounded-md border border-line-strong px-2 py-1 text-xs text-ink"
                          placeholder="Notes"
                        /></label>
                        <div className="flex items-center justify-end">
                          <Button
                            variant="secondary"
                            size="sm"
                            loading={updateArtifactMutation.isPending}
                            onClick={() =>
                              updateArtifactMutation.mutate({
                                package_id: selectedPackage.id,
                                artifact_id: artifact.id,
                                draft,
                              })
                            }
                          >
                            Save
                          </Button>
                        </div>
                        <label className="inline-flex items-center gap-2 text-xs text-ink">
                          <input
                            type="checkbox"
                            checked={draft.required}
                            onChange={(e) =>
                              setArtifactDrafts((current) => ({
                                ...current,
                                [artifact.id]: { ...draft, required: e.target.checked },
                              }))
                            }
                          />
                          Required
                        </label>
                        <label className="inline-flex items-center gap-2 text-xs text-ink">
                          <input
                            type="checkbox"
                            checked={draft.included}
                            onChange={(e) =>
                              setArtifactDrafts((current) => ({
                                ...current,
                                [artifact.id]: { ...draft, included: e.target.checked },
                              }))
                            }
                          />
                          Included
                        </label>
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>File reference (optional)</span><input aria-label="File reference (optional)"
                          value={draft.file_path}
                          onChange={(e) =>
                            setArtifactDrafts((current) => ({
                              ...current,
                              [artifact.id]: { ...draft, file_path: e.target.value },
                            }))
                          }
                          className="w-full rounded-md border border-line-strong px-2 py-1 text-xs text-ink"
                          placeholder="File path"
                        /></label>
                        <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Link URL (optional)</span><input aria-label="Link URL (optional)"
                          value={draft.link_url}
                          onChange={(e) =>
                            setArtifactDrafts((current) => ({
                              ...current,
                              [artifact.id]: { ...draft, link_url: e.target.value },
                            }))
                          }
                          className="w-full rounded-md border border-line-strong px-2 py-1 text-xs text-ink"
                          placeholder="Link URL"
                        /></label>
                      </fieldset>
                    )
                  })}
                </div>
              )}
            </div>
          ) : null}
          </section>
        </Card>
      ) : null}

      <DecisionModal open={!!returnPackageId} title="Return package to draft" description="This clears the existing approval. After corrections, the package must go through approval again. Locked packages cannot be reopened." rationaleLabel="Reason for changes" rationaleValue={returnReason} onRationaleChange={setReturnReason} rationaleMode="required" confirmVariant="primary" confirmLabel="Return to draft" onConfirm={() => returnPackageMutation.mutate()} onClose={() => setReturnPackageId(null)} isWorking={returnPackageMutation.isPending} />

      <Modal
        open={showCreateModal}
        title="Start certification"
        onClose={() => {
          setShowCreateModal(false)
          setCreateBaselineSelection([])
        }}
        size="lg"
      >
        <form onSubmit={handleCreateProject} className="space-y-4">
          {createProjectMutation.isError && <p role="alert" className="rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger">{getApiErrorMessage(createProjectMutation.error, 'Unable to create the project. Check the fields and try again.')}</p>}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Project name</label>
            <input
              name="name"
              aria-label="Project name"
              required
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
              placeholder="Certification project name"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Jurisdiction</label>
            <select
              name="jurisdiction_id"
              aria-label="Project jurisdiction"
              required
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
              value={createJurisdictionId}
              onChange={(event) => setCreateJurisdictionId(event.target.value)}
            >
              {(jurisdictionsQuery.data?.items ?? []).map((jurisdiction) => (
                <option key={jurisdiction.id} value={jurisdiction.id}>
                  {jurisdiction.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Approved requirement sets (optional at setup)
            </label>
            <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border border-line p-3">
              {createModalSets.map((set) => (
                <label key={set.document_id} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={createBaselineSelection.includes(set.document_id)}
                    onChange={(event) => {
                      setCreateBaselineSelection((current) =>
                        event.target.checked
                          ? [...current, set.document_id]
                          : current.filter((id) => id !== set.document_id)
                      )
                    }}
                  />
                  <span>
                    {(set.name || set.filename)}{' '}
                    {set.current_version_number ? `(v${set.current_version_number})` : ''}
                  </span>
                </label>
              ))}
              {createModalSets.length === 0 ? (
                <div className="text-xs text-muted">No approved requirement sets for this jurisdiction.</div>
              ) : null}
              {createBaselineSelection.length === 0 && <div className="text-xs text-muted">You can choose an approved baseline later. An assessment needs one before it starts.</div>}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Target submission date</label>
            <input
              type="date"
              name="target_submission_date"
              aria-label="Target submission date"
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Description</label>
            <textarea aria-label="Description"
              name="description"
              rows={3}
              className="w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
              placeholder="Scope, lab dependencies, key blockers..."
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-muted">Assurance type<select name="assurance_type" className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink"><option value="">Choose later</option><option value="test">Test</option><option value="audit">Audit</option><option value="certification">Certification</option></select></label>
            <label className="text-sm text-muted">Test lab or provider (optional)<input name="provider_name" maxLength={255} className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink" /></label>
            <label className="text-sm text-muted sm:col-span-2">Assurance scope (optional)<textarea name="assurance_scope" rows={2} className="mt-1 block w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-ink" /></label>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setShowCreateModal(false)
                setCreateBaselineSelection([])
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              loading={createProjectMutation.isPending}
            >
              Start certification
            </Button>
          </div>
        </form>
      </Modal>

      <DecisionModal
        open={!!projectToDelete}
        title="Delete certification project?"
        description={
          projectToDelete
            ? `Delete certification project "${projectToDelete.name}"? This cannot be undone.`
            : ''
        }
        confirmLabel="Delete project"
        confirmVariant="destructive"
        dangerDetails={[
          'Permanently remove the certification project record.',
          'Delete linked execution context that depends on this project.',
        ]}
        onConfirm={() => {
          if (!projectToDelete) return
          deleteProjectMutation.mutate(projectToDelete.id)
          setProjectToDelete(null)
        }}
        onClose={() => setProjectToDelete(null)}
        isWorking={deleteProjectMutation.isPending}
      />
    </div>
  )
}
