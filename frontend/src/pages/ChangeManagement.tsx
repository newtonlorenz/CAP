import './workflow-pages.css'
import HistoricalChangeScope from '../components/workflows/HistoricalChangeScope'
import ChangeProgramme from '../components/workflows/ChangeProgramme'
import ChangeRecordSummary from '../components/workflows/ChangeRecordSummary'
import Modal from '../components/ui/Modal'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { useDraftNavigationGuard } from '../hooks/useDraftNavigationGuard'
import { getApiErrorMessage } from '../api/errors'
import ChangeAssessments from '../components/workflows/ChangeAssessments'
import ComponentFields, { type ComponentDraft } from '../components/ComponentFields'
import ChangeProposalFields, { type ChangeDraft } from '../components/ChangeProposalFields'
import { downloadClientCsv } from '../utils/csv'
import { formatDateTime } from '../utils/dateFormat'
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import SectionNav from '../components/ui/SectionNav'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useJurisdiction } from '../contexts/JurisdictionContext'
import { useToast } from '../contexts/ToastContext'
import type {
  BaselineDiffResponse,
  ChangeActivityResponse,
  ChangeEntry,
  ComponentBaseline,
  ComponentRegister,
  ManagedComponent,
  PaginatedResponse,
} from '../types'
import { notifyApiError } from '../utils/notify'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import LoadError from '../components/ui/LoadError'
import Card from '../components/ui/Card'
import DecisionModal from '../components/ui/DecisionModal'
import { Table, TBody, TD, TH, THead, TR, TableEmpty } from '../components/ui/Table'

type TabId = 'components' | 'changes' | 'baselines' | 'programme' | 'reports'
type ChangeEventType = 'note' | 'decision' | 'status_change'
type IntegrationResult = 'pending' | 'pass' | 'fail'
type WorkflowAction = 'approve' | 'reject' | 'implement' | 'verify' | 'rollback'

function missingApprovalDetails(change: ChangeEntry, danish: boolean): string[] {
  const readiness = change.readiness?.approval
  if (readiness) {
    if (readiness.ready) return []
    const reasons = [...new Set(readiness.reasons.map(item => item.message))]
    return reasons.length ? reasons : ['Approval checks are incomplete. Reload this change before approval.']
  }
  if (danish) return ['Danish approval readiness is unavailable. Reload this change before approval.']
  const missing: string[] = []
  if (!change.change_type) missing.push('Change type')
  if (!change.description?.trim()) missing.push('Description')
  if (!change.components.length) missing.push('At least one linked component')
  const planning = [
    ['complexity_classification', 'complexity'], ['resource_assessment', 'resources'],
    ['scheduling_assessment', 'scheduling'], ['planned_start_at', 'planned start'],
    ['planned_end_at', 'planned end'], ['justification', 'justification'],
  ] as const
  const missingPlanning = planning.filter(([key]) => !change[key]?.trim()).map(([, label]) => label)
  if (missingPlanning.length) missing.push(`Planning: ${missingPlanning.join(', ')}`)
  const evaluation = [
    ['evaluation_effect', 'expected effect'], ['evaluation_risk', 'risk'],
    ['evaluation_regulatory_impact', 'regulatory impact'], ['evaluation_ciaa_impact', 'CIAA impact'],
  ] as const
  const missingEvaluation = evaluation.filter(([key]) => !change[key]?.trim()).map(([, label]) => label)
  if (missingEvaluation.length) missing.push(`Impact evaluation: ${missingEvaluation.join(', ')}`)
  if (change.testing_org_required && (!change.testing_org_status || !change.testing_org_cycle)) missing.push('Testing organization status and cycle')
  return missing
}



const tabs: Array<{ id: TabId; label: string }> = [
  { id: 'changes', label: 'Change Register' },
  { id: 'components', label: 'Components' },
  { id: 'programme', label: 'Programme assurance' },
  { id: 'baselines', label: 'Baselines' },
  { id: 'reports', label: 'Reports' },
]
const EMPTY_REGISTERS: ComponentRegister[] = []
const EMPTY_COMPONENTS: ManagedComponent[] = []
const EMPTY_CHANGES: ChangeEntry[] = []
const EMPTY_BASELINES: ComponentBaseline[] = []

const changeStatusTone = (status: string): 'slate' | 'blue' | 'amber' | 'green' | 'red' => {
  if (status === 'verified') return 'green'
  if (status === 'implemented') return 'blue'
  if (status === 'approved') return 'blue'
  if (status === 'rejected') return 'red'
  return 'slate'
}

const componentStatusTone = (status: string): 'slate' | 'green' | 'amber' => {
  if (status === 'active') return 'green'
  if (status === 'retired') return 'amber'
  return 'slate'
}

function formatDate(value: string | null): string {
  if (!value) return '-'
  return formatDateTime(value)
}

function formatOptionLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`
}

function toInputDateTime(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const year = date.getFullYear()
  const month = pad2(date.getMonth() + 1)
  const day = pad2(date.getDate())
  const hours = pad2(date.getHours())
  const minutes = pad2(date.getMinutes())
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

function workflowStamp(approvedAt?: string | null): string {
  const approved = approvedAt ? Math.ceil(new Date(approvedAt).getTime() / 1000) * 1000 : 0
  const date = new Date(Math.max(Math.floor(Date.now() / 1000) * 1000, approved))
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19)
}

function toIsoOrNull(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString()
}

function defaultComponentDraft(): ComponentDraft {
  return {
    component_uid: '',
    definition: '',
    version: '',
    identifying_characteristics: '',
    change_owner_name: '',
    confidentiality_code: 2,
    integrity_code: 2,
    availability_code: 2,
    accountability_code: 2,
    checksum_hash: '',
    is_hardware: false,
    geographic_location: '',
    hosting_model: 'on_prem',
    virtualized: false,
    public_cloud_provider: '',
    public_cloud_certification: '',
    public_cloud_independent: false,
    public_cloud_redundancy: false,
    status: 'active',
    regulatory_scope: 'unknown',
  }
}

function defaultChangeDraft(): ChangeDraft {
  return {
    title: '',
    description: '',
    category: '',
    change_type: 'normal',
    complexity_classification: '',
    resource_assessment: '',
    scheduling_assessment: '',
    affected_components_summary: '',
    affected_docs_summary: '',
    planned_start_at: '',
    planned_end_at: '',
    justification: '',
    affected_documentation: '',
    evaluation_effect: '',
    evaluation_risk: '',
    evaluation_regulatory_impact: '',
    evaluation_ciaa_impact: '',
    testing_org_required: true,
    testing_org_status: 'pending',
    testing_org_cycle: 'annual',
    testing_org_next_due_at: '',
    testing_org_approved_at: '',
    integration_related: false,
    component_ids: [],
    planned_versions: {}, planned_checksum_hashes: {}, baseline_scope_assessments: {}, compliance: {},
  }
}

function componentDraftFromEntity(component: ManagedComponent): ComponentDraft {
  return {
    regulatory_scope: component.regulatory_scope || 'unknown',
    component_uid: component.component_uid,
    definition: component.definition,
    version: component.version,
    identifying_characteristics: component.identifying_characteristics,
    change_owner_name: component.change_owner_name || '',
    confidentiality_code: component.confidentiality_code,
    integrity_code: component.integrity_code,
    availability_code: component.availability_code,
    accountability_code: component.accountability_code,
    checksum_hash: component.checksum_hash || '',
    is_hardware: component.is_hardware,
    geographic_location: component.geographic_location || '',
    hosting_model: component.hosting_model === 'private_cloud' || component.hosting_model === 'public_cloud' ? component.hosting_model : 'on_prem',
    virtualized: component.virtualized,
    public_cloud_provider: component.public_cloud_provider || '',
    public_cloud_certification: component.public_cloud_certification || '',
    public_cloud_independent: component.public_cloud_independent,
    public_cloud_redundancy: component.public_cloud_redundancy,
    status: component.status === 'inactive' || component.status === 'retired' ? component.status : 'active',
  }
}

function changeDraftFromEntity(change: ChangeEntry): ChangeDraft {
  return {
    title: change.title,
    description: change.description || '',
    category: change.category || '',
    change_type:
      change.change_type === 'standard' || change.change_type === 'emergency' ? change.change_type : 'normal',
    complexity_classification: change.complexity_classification || '',
    resource_assessment: change.resource_assessment || '',
    scheduling_assessment: change.scheduling_assessment || '',
    affected_components_summary: change.affected_components_summary || '',
    affected_docs_summary: change.affected_docs_summary || '',
    planned_start_at: toInputDateTime(change.planned_start_at),
    planned_end_at: toInputDateTime(change.planned_end_at),
    justification: change.justification || '',
    affected_documentation: change.affected_documentation || '',
    evaluation_effect: change.evaluation_effect || '',
    evaluation_risk: change.evaluation_risk || '',
    evaluation_regulatory_impact: change.evaluation_regulatory_impact || '',
    evaluation_ciaa_impact: change.evaluation_ciaa_impact || '',
    testing_org_required: change.testing_org_required,
    testing_org_status: change.testing_org_status || '',
    testing_org_cycle:
      change.testing_org_cycle === 'immediate' || change.testing_org_cycle === 'quarterly' ? change.testing_org_cycle : 'annual',
    testing_org_next_due_at: toInputDateTime(change.testing_org_next_due_at),
    testing_org_approved_at: toInputDateTime(change.testing_org_approved_at),
    integration_related: change.integration_related,
    component_ids: change.components.map((item) => item.component_id),
    planned_versions: Object.fromEntries(change.components.map(item => [item.component_id, item.planned_version || ''])),
    baseline_scope_assessments: Object.fromEntries(change.components.map(item => [item.component_id, item.baseline_scope_assessment || ''])),
    planned_checksum_hashes: Object.fromEntries(change.components.map(item => [item.component_id, item.planned_checksum_hash || ''])),
    compliance: change.compliance || {},
  }
}

export default function ChangeManagement() {
  const { user } = useAuth()
  const { jurisdictionId, jurisdictionById, setJurisdictionId } = useJurisdiction()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [searchParams, setSearchParams] = useSearchParams()
  const requestedChangeId = searchParams.get('change')
  const activeTab: TabId = tabs.find((tab) => tab.id === searchParams.get('tab'))?.id || 'changes'
  const setActiveTab = (value: TabId) => setSearchParams((current) => { const next = new URLSearchParams(current); next.set('tab', value); return next })
  const [selectedRegisterId, setSelectedRegisterId] = useState<string | null>(null)
  const [selectedBaselineId, setSelectedBaselineId] = useState<string | null>(null)
  const selectedChangeId = requestedChangeId
  const setSelectedChangeId = useCallback((value: string | null) => setSearchParams(current => { const next = new URLSearchParams(current); if (value) { next.set('change', value); next.set('tab', 'changes') } else next.delete('change'); return next }), [setSearchParams])
  const previousRegisterId = useRef<string | null>(null)
  const linkedChangeQuery = useQuery({ queryKey: ['change-management', 'linked-change', requestedChangeId], enabled: Boolean(requestedChangeId), queryFn: async () => (await api.get<ChangeEntry & { jurisdiction_id?: string | null }>(`/change-management/changes/${requestedChangeId}`)).data })

  useEffect(() => { const targetJurisdiction = linkedChangeQuery.data?.jurisdiction_id; if (targetJurisdiction && targetJurisdiction !== jurisdictionId) setJurisdictionId(targetJurisdiction) }, [linkedChangeQuery.data?.jurisdiction_id, jurisdictionId, setJurisdictionId])

  const [registerForm, setRegisterForm] = useState({ name: 'Component register', status: 'active' })
  const [showCreateRegisterForm, setShowCreateRegisterForm] = useState(false)

  const [componentForm, setComponentForm] = useState<ComponentDraft>(() => defaultComponentDraft())
  const [editingComponentId, setEditingComponentId] = useState<string | null>(null)
  const componentCreateDetails = useRef<HTMLDetailsElement>(null)
  const [showCreateChange, setShowCreateChange] = useState(false)
  const [programmeDraftState, setProgrammeDraftState] = useState({dirty:false,saving:false})
  const onProgrammeDraftState = useCallback((dirty:boolean,saving:boolean) => setProgrammeDraftState(previous => previous.dirty === dirty && previous.saving === saving ? previous : {dirty,saving}), [])
  const [pendingDiscard, setPendingDiscard] = useState<(() => void) | null>(null)
  const detailsRef = useRef<HTMLDivElement>(null)
  const workflowInitial = useRef('')
  const [workflowVersions, setWorkflowVersions] = useState<Record<string, {version: string; checksum: string}>>({})
  const [recoveryChangeId, setRecoveryChangeId] = useState('')
  const [rollbackOutcome, setRollbackOutcome] = useState('')
  const [rollbackFollowUp, setRollbackFollowUp] = useState('')
  const [componentEditDraft, setComponentEditDraft] = useState<ComponentDraft>(() => defaultComponentDraft())
  const [componentFilters, setComponentFilters] = useState({
    q: '',
    status: 'all',
    classification: 'all',
    hosting_model: 'all',
  })

  const [changeForm, setChangeForm] = useState<ChangeDraft>(() => defaultChangeDraft())
  const [editingChangeId, setEditingChangeId] = useState<string | null>(null)
  const [changeEditDraft, setChangeEditDraft] = useState<ChangeDraft>(() => defaultChangeDraft())
  const [changeFilters, setChangeFilters] = useState({
    q: '',
    status: 'all',
    change_type: 'all',
    integration: 'all',
    component_id: '',
  })

  const [workflowAction, setWorkflowAction] = useState<{ changeId: string; action: WorkflowAction } | null>(null)
  const [workflowRationale, setWorkflowRationale] = useState('')
  const [workflowImplementedStart, setWorkflowImplementedStart] = useState('')
  const [workflowImplementedEnd, setWorkflowImplementedEnd] = useState('')

  const [eventForm, setEventForm] = useState<{ event_type: ChangeEventType; note: string }>({
    event_type: 'note',
    note: '',
  })
  const [editingEventId, setEditingEventId] = useState<string | null>(null)
  const [eventEditDraft, setEventEditDraft] = useState<{ event_type: ChangeEventType; note: string }>({
    event_type: 'note',
    note: '',
  })

  const [integrationCheckForm, setIntegrationCheckForm] = useState({
    action: '',
    action_reference: '',
    result: 'pending' as IntegrationResult,
    completed_at: '',
    notes: '',
    evidence_notes: '',
  })
  const [editingCheckId, setEditingCheckId] = useState<string | null>(null)
  const [integrationCheckEditDraft, setIntegrationCheckEditDraft] = useState({
    action: '',
    action_reference: '',
    result: 'pending' as IntegrationResult,
    completed_at: '',
    notes: '',
    evidence_notes: '',
  })
  const [pendingComponentDelete, setPendingComponentDelete] = useState<{
    componentId: string
    label: string
  } | null>(null)
  const [pendingEventDelete, setPendingEventDelete] = useState<{
    changeId: string
    eventId: string
    reason: string
  } | null>(null)
  const [pendingIntegrationCheckDelete, setPendingIntegrationCheckDelete] = useState<{
    changeId: string
    checkId: string
    reason: string
  } | null>(null)

  const [baselineLabel, setBaselineLabel] = useState('')
  const [baselineCertification, setBaselineCertification] = useState('')
  const [baselineScope, setBaselineScope] = useState('manual')
  const [baselineDate, setBaselineDate] = useState('')
  const [baselineEvidence, setBaselineEvidence] = useState('')
  const [baselineAto, setBaselineAto] = useState('')
  const [baselineSearch, setBaselineSearch] = useState('')

  const [reportPeriod, setReportPeriod] = useState<'90' | '180' | '365'>('90')
  const [historyComponentId, setHistoryComponentId] = useState('')
  const [downloadingReport, setDownloadingReport] = useState<string | null>(null)

  const canConfigure = user?.role === 'admin' || user?.role === 'manager'
  const canEdit = canConfigure || user?.role === 'contributor'
  const canDownloadReports = canConfigure || user?.role === 'approver'

  const registersQuery = useQuery({
    queryKey: ['change-management', 'registers', jurisdictionId],
    enabled: !!jurisdictionId,
    queryFn: async () => {
      const params = new URLSearchParams()
      params.set('limit', '1000')
      if (jurisdictionId) params.set('jurisdiction_id', jurisdictionId)
      const response = await api.get<PaginatedResponse<ComponentRegister>>(
        `/change-management/registers?${params.toString()}`
      )
      return response.data
    },
  })

  const registers = registersQuery.data?.items ?? EMPTY_REGISTERS

  useEffect(() => {
    if (!registers.length) {
      setSelectedRegisterId(null)
      return
    }
    if (requestedChangeId && linkedChangeQuery.isPending) return
    const linkedRegister = linkedChangeQuery.data?.register_id
    if (requestedChangeId && linkedRegister && registers.some(item => item.id === linkedRegister) && selectedRegisterId !== linkedRegister) { setSelectedRegisterId(linkedRegister); return }
    if (!selectedRegisterId || !registers.find((item) => item.id === selectedRegisterId)) {
      setSelectedRegisterId(registers[0].id)
    }
  }, [registers, selectedRegisterId, requestedChangeId, linkedChangeQuery.data, linkedChangeQuery.isPending])

  const componentsQuery = useQuery({
    queryKey: ['change-management', 'components', selectedRegisterId],
    enabled: !!selectedRegisterId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<ManagedComponent>>(
        `/change-management/registers/${selectedRegisterId}/components?limit=1000`
      )
      return response.data
    },
  })

  const changesQuery = useQuery({
    queryKey: ['change-management', 'changes', selectedRegisterId],
    enabled: !!selectedRegisterId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<ChangeEntry>>(
        `/change-management/registers/${selectedRegisterId}/changes?limit=1000`
      )
      return response.data
    },
  })

  const baselinesQuery = useQuery({
    queryKey: ['change-management', 'baselines', selectedRegisterId],
    enabled: !!selectedRegisterId,
    queryFn: async () => {
      const response = await api.get<PaginatedResponse<ComponentBaseline>>(
        `/change-management/registers/${selectedRegisterId}/baselines?limit=1000`
      )
      return response.data
    },
  })

  const baselineDiffQuery = useQuery({
    queryKey: ['change-management', 'baseline-diff', selectedRegisterId, selectedBaselineId],
    enabled: !!selectedRegisterId && !!selectedBaselineId,
    queryFn: async () => {
      const response = await api.get<BaselineDiffResponse>(
        `/change-management/registers/${selectedRegisterId}/baselines/${selectedBaselineId}/diff`
      )
      return response.data
    },
  })

  const activityQuery = useQuery({
    queryKey: ['change-management', 'activity', selectedChangeId],
    enabled: !!selectedChangeId,
    queryFn: async () => {
      const response = await api.get<ChangeActivityResponse>(`/change-management/changes/${selectedChangeId}/activity`)
      return response.data
    },
  })

  const selectedRegister = useMemo(
    () => registers.find((item) => item.id === selectedRegisterId) || null,
    [registers, selectedRegisterId]
  )
  const danish = ['dk', 'denmark'].includes(jurisdictionById[jurisdictionId || '']?.code?.toLowerCase() || '')
  const components = componentsQuery.data?.items ?? EMPTY_COMPONENTS
  const changes = changesQuery.data?.items ?? EMPTY_CHANGES
  const baselines = baselinesQuery.data?.items ?? EMPTY_BASELINES

  const selectedChange = useMemo(
    () => changes.find((item) => item.id === selectedChangeId) || (linkedChangeQuery.data?.id === selectedChangeId ? linkedChangeQuery.data : null),
    [changes, selectedChangeId, linkedChangeQuery.data]
  )
  const workflowChange = workflowAction
    ? changes.find(item => item.id === workflowAction.changeId)
      || (linkedChangeQuery.data?.id === workflowAction.changeId ? linkedChangeQuery.data : null)
    : null
  const workflowLabel = workflowAction ? `${formatOptionLabel(workflowAction.action)} Change` : ''
  const approvalMissing = workflowAction?.action === 'approve' && workflowChange ? missingApprovalDetails(workflowChange, danish) : []
  useEffect(() => {
    if (!workflowAction || !approvalMissing.length) return
    const heading = document.getElementById('change-workflow-heading')
    heading?.focus()
    heading?.scrollIntoView?.({ block: 'start' })
  }, [workflowAction, approvalMissing.length])

  useEffect(() => {
    if (selectedBaselineId && !baselines.find((item) => item.id === selectedBaselineId)) {
      setSelectedBaselineId(null)
    }
  }, [baselines, selectedBaselineId])

  useEffect(() => {
    if (selectedChangeId && changesQuery.isSuccess && linkedChangeQuery.isError && !changes.find((item) => item.id === selectedChangeId)) {
      setSelectedChangeId(null)
    }
  }, [changes, selectedChangeId, changesQuery.isSuccess, linkedChangeQuery.isError, setSelectedChangeId])

  useEffect(() => {
    if (historyComponentId && !components.find((item) => item.id === historyComponentId)) {
      setHistoryComponentId('')
    }
  }, [components, historyComponentId])

  useEffect(() => {
    if (previousRegisterId.current === selectedRegisterId) return
    previousRegisterId.current = selectedRegisterId
    setSelectedBaselineId(null)
    setHistoryComponentId('')
    setEditingComponentId(null)
    setEditingChangeId(null)
    setWorkflowAction(null)
  }, [selectedRegisterId])

  const filteredComponents = useMemo(() => {
    const query = componentFilters.q.trim().toLowerCase()
    return [...components]
      .filter((component) => {
        if (componentFilters.status !== 'all' && component.status !== componentFilters.status) return false
        if (
          componentFilters.classification !== 'all' &&
          String(component.classification_code) !== componentFilters.classification
        )
          return false
        if (componentFilters.hosting_model !== 'all' && component.hosting_model !== componentFilters.hosting_model)
          return false
        if (!query) return true
        return (
          component.component_uid.toLowerCase().includes(query) ||
          component.definition.toLowerCase().includes(query) ||
          (component.change_owner_name || '').toLowerCase().includes(query)
        )
      })
      .sort((a, b) => a.component_uid.localeCompare(b.component_uid))
  }, [components, componentFilters])

  const filteredChanges = useMemo(() => {
    const query = changeFilters.q.trim().toLowerCase()
    return [...changes]
      .filter((change) => {
        if (changeFilters.status === 'attention') {const check = ['draft','rejected'].includes(change.status) ? change.readiness?.approval : change.status === 'approved' ? change.readiness?.implementation : change.readiness?.verification;if (!check?.reasons.some(item => !item.code.endsWith('_status'))) return false} else if (changeFilters.status !== 'all' && change.status !== changeFilters.status) return false
        if (changeFilters.change_type !== 'all' && change.change_type !== changeFilters.change_type) return false
        if (changeFilters.integration === 'yes' && !change.integration_related) return false
        if (changeFilters.integration === 'no' && change.integration_related) return false
        if (changeFilters.component_id && !change.components.some((link) => link.component_id === changeFilters.component_id))
          return false
        if (!query) return true
        return (
          change.title.toLowerCase().includes(query) ||
          (change.description || '').toLowerCase().includes(query) ||
          (change.justification || '').toLowerCase().includes(query)
        )
      })
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  }, [changes, changeFilters])

  const filteredBaselines = useMemo(() => {
    const query = baselineSearch.trim().toLowerCase()
    return [...baselines]
      .filter((baseline) => !query || baseline.label.toLowerCase().includes(query))
      .sort((a, b) => new Date(b.established_at).getTime() - new Date(a.established_at).getTime())
  }, [baselines, baselineSearch])

  const createRegisterMutation = useMutation({
    mutationFn: async () => {
      if (!jurisdictionId) {
        throw new Error('Select a jurisdiction before creating a register')
      }
      const response = await api.post<ComponentRegister>('/change-management/registers', {
        jurisdiction_id: jurisdictionId,
        name: registerForm.name,
        status: registerForm.status,
      })
      return response.data
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setSelectedRegisterId(created.id)
      setShowCreateRegisterForm(false)
      setActiveTab('components')
      toast.success('Component register created')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to create register'),
  })

  const buildComponentPayload = (draft: ComponentDraft) => ({
    ...draft,
    checksum_hash: draft.checksum_hash || null,
    geographic_location: draft.geographic_location || null,
    public_cloud_provider: draft.public_cloud_provider || null,
    change_owner_name: draft.change_owner_name || null,
  })

  const createComponentMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRegisterId) throw new Error('Select a register before adding components')
      const response = await api.post<ManagedComponent>(
        `/change-management/registers/${selectedRegisterId}/components`,
        buildComponentPayload(componentForm)
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      componentCreateDetails.current?.removeAttribute('open')
      setComponentForm(defaultComponentDraft())
      toast.success('Component added')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to add component'),
  })

  const updateComponentMutation = useMutation({
    mutationFn: async (componentId: string) => {
      const response = await api.patch<ManagedComponent>(
        `/change-management/components/${componentId}`,
        buildComponentPayload(componentEditDraft)
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setEditingComponentId(null)
      toast.success('Component updated')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to update component'),
  })

  const deleteComponentMutation = useMutation({
    mutationFn: async (componentId: string) => {
      await api.delete(`/change-management/components/${componentId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setEditingComponentId(null)
      toast.success('Component deleted')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to delete component'),
  })

  const buildChangePayload = (draft: ChangeDraft, existing?: ChangeEntry) => ({
    title: draft.title,
    description: draft.description || null,
    category: draft.category || null,
    change_type: draft.change_type,
    complexity_classification: draft.complexity_classification || null,
    resource_assessment: draft.resource_assessment || null,
    scheduling_assessment: draft.scheduling_assessment || null,
    affected_components_summary: draft.affected_components_summary || null,
    affected_docs_summary: draft.affected_docs_summary || null,
    planned_start_at: toIsoOrNull(draft.planned_start_at),
    planned_end_at: toIsoOrNull(draft.planned_end_at),
    justification: draft.justification || null,
    affected_documentation: draft.affected_documentation || null,
    evaluation_effect: draft.evaluation_effect || null,
    evaluation_risk: draft.evaluation_risk || null,
    evaluation_regulatory_impact: draft.evaluation_regulatory_impact || null,
    evaluation_ciaa_impact: draft.evaluation_ciaa_impact || null,
    testing_org_required: draft.testing_org_required,
    testing_org_status: draft.testing_org_status || null,
    testing_org_cycle: draft.testing_org_cycle,
    testing_org_next_due_at: toIsoOrNull(draft.testing_org_next_due_at),
    testing_org_approved_at: toIsoOrNull(draft.testing_org_approved_at),
    integration_related: draft.integration_related,
    compliance: danish ? draft.compliance : undefined,
    components: draft.component_ids.map((componentId) => {
      const link = existing?.components.find((item) => item.component_id === componentId)
      return {
        component_id: componentId,
        version_at_proposal: link ? link.version_at_proposal : components.find((item) => item.id === componentId)?.version || null,
        planned_version: draft.planned_versions[componentId] || null,
        planned_checksum_hash: draft.planned_checksum_hashes[componentId] || null,
        baseline_scope_assessment: draft.baseline_scope_assessments[componentId] || null,
        implemented_version: link?.implemented_version || null,
      }
    }),
  })

  const createChangeMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRegisterId) throw new Error('Select a register before creating a change proposal')
      const response = await api.post<ChangeEntry>(
        `/change-management/registers/${selectedRegisterId}/changes`,
        buildChangePayload(changeForm)
      )
      return response.data
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setSelectedChangeId(created.id)
      setShowCreateChange(false)
      setChangeForm(defaultChangeDraft())
      toast.success('Change proposal created')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to create change proposal'),
  })

  const updateChangeMutation = useMutation({
    mutationFn: async (changeId: string) => {
      const existing = changes.find((item) => item.id === changeId)
      const payload = existing && ['approved', 'implemented', 'verified'].includes(existing.status)
        ? (danish ? {compliance:changeEditDraft.compliance} : { testing_org_status: changeEditDraft.testing_org_status || null, testing_org_cycle: changeEditDraft.testing_org_cycle, testing_org_next_due_at: toIsoOrNull(changeEditDraft.testing_org_next_due_at), testing_org_approved_at: toIsoOrNull(changeEditDraft.testing_org_approved_at) })
        : buildChangePayload(changeEditDraft, existing)
      const response = await api.patch<ChangeEntry>(`/change-management/changes/${changeId}`, payload)
      return response.data
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setSelectedChangeId(updated.id)
      setEditingChangeId(null)
      toast.success('Change proposal updated')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to update change proposal'),
  })

  const workflowMutation = useMutation({
    mutationFn: async (payload: {
      changeId: string
      action: WorkflowAction
      rationale: string
      implementedStart?: string
      implementedEnd?: string
    }) => {
      if (payload.action === 'approve') {
        await api.post(`/change-management/changes/${payload.changeId}/approve`, {
          approval_decision: payload.rationale,
        })
        return
      }
      if (payload.action === 'reject') {
        await api.post(`/change-management/changes/${payload.changeId}/reject`, {
          rejection_reason: payload.rationale,
        })
        return
      }
      const actualComponents = Object.entries(workflowVersions).map(([component_id, value]) => ({ component_id, implemented_version: value.version, implemented_checksum_hash: value.checksum || null }))
      if (payload.action === 'rollback') {
        await api.post(`/change-management/changes/${payload.changeId}/rollback`, { reason: payload.rationale, recovery_change_id:recoveryChangeId, outcome: rollbackOutcome, follow_up: rollbackFollowUp, components: actualComponents })
        return
      }
      if (payload.action === 'implement') {
        await api.post(`/change-management/changes/${payload.changeId}/implement`, {
          components: actualComponents,
          implementation_notes: payload.rationale,
          implemented_start_at: payload.implementedStart ? toIsoOrNull(payload.implementedStart) : null,
          implemented_end_at: payload.implementedEnd ? toIsoOrNull(payload.implementedEnd) : null,
        })
        return
      }
      await api.post(`/change-management/changes/${payload.changeId}/verify`, {
        verification_notes: payload.rationale,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setWorkflowAction(null)
      setWorkflowRationale('')
      toast.success('Change workflow action saved')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to run workflow action'),
  })

  const createBaselineMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRegisterId) throw new Error('Select a register before creating a baseline')
      await api.post(`/change-management/registers/${selectedRegisterId}/baselines`, {
        label: baselineLabel,
        certification_reference: baselineCertification || null,
        certification_scope: baselineScope,
        certification_at: baselineDate ? new Date(baselineDate).toISOString() : null,
        certification_evidence: baselineEvidence || null,
        certification_ato: baselineAto || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setBaselineLabel('')
      setBaselineCertification('')
      setBaselineScope('manual'); setBaselineDate(''); setBaselineEvidence(''); setBaselineAto('')
      toast.success('Baseline snapshot created')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to create baseline'),
  })

  const addEventMutation = useMutation({
    mutationFn: async (changeId: string) => {
      await api.post(`/change-management/changes/${changeId}/events`, {
        event_type: eventForm.event_type,
        note: eventForm.note || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setEventForm({ event_type: 'note', note: '' })
      toast.success('Change event added')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to add change event'),
  })

  const updateEventMutation = useMutation({
    mutationFn: async (payload: { changeId: string; eventId: string }) => {
      await api.patch(`/change-management/changes/${payload.changeId}/events/${payload.eventId}`, {
        event_type: eventEditDraft.event_type,
        note: eventEditDraft.note || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setEditingEventId(null)
      toast.success('Event updated')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to update event'),
  })

  const deleteEventMutation = useMutation({
    mutationFn: async (payload: { changeId: string; eventId: string; reason: string }) => {
      await api.delete(`/change-management/changes/${payload.changeId}/events/${payload.eventId}`, {
        data: { reason: payload.reason },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      toast.success('Event deleted with audit trail')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to delete event'),
  })

  const addIntegrationCheckMutation = useMutation({
    mutationFn: async (changeId: string) => {
      await api.post(`/change-management/changes/${changeId}/integration-checks`, {
        action: integrationCheckForm.action,
        action_reference: integrationCheckForm.action_reference || null,
        result: integrationCheckForm.result,
        completed_at: toIsoOrNull(integrationCheckForm.completed_at),
        notes: integrationCheckForm.notes || null,
        evidence_notes: integrationCheckForm.evidence_notes || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setIntegrationCheckForm({
        action: '',
        action_reference: '',
        result: 'pending',
        completed_at: '',
        notes: '',
        evidence_notes: '',
      })
      toast.success('Integration check recorded')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to add integration check'),
  })

  const updateIntegrationCheckMutation = useMutation({
    mutationFn: async (payload: { changeId: string; checkId: string }) => {
      await api.patch(`/change-management/changes/${payload.changeId}/integration-checks/${payload.checkId}`, {
        action: integrationCheckEditDraft.action,
        action_reference: integrationCheckEditDraft.action_reference || null,
        result: integrationCheckEditDraft.result,
        completed_at: toIsoOrNull(integrationCheckEditDraft.completed_at),
        notes: integrationCheckEditDraft.notes || null,
        evidence_notes: integrationCheckEditDraft.evidence_notes || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      setEditingCheckId(null)
      toast.success('Integration check updated')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to update integration check'),
  })

  const deleteIntegrationCheckMutation = useMutation({
    mutationFn: async (payload: { changeId: string; checkId: string; reason: string }) => {
      await api.delete(`/change-management/changes/${payload.changeId}/integration-checks/${payload.checkId}`, {
        data: { reason: payload.reason },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['change-management'] })
      toast.success('Integration check deleted with audit trail')
    },
    onError: (error: unknown) => notifyApiError(toast, error, 'Failed to delete integration check'),
  })



  const openWorkflow = (changeId: string, action: WorkflowAction) => {
    setSelectedChangeId(changeId)
    const target = changes.find(item => item.id === changeId) || selectedChange
    const versions = Object.fromEntries((target?.components || []).map(link => [link.component_id, { version: (action === 'rollback' ? link.version_at_proposal : link.planned_version) || '', checksum: (action === 'rollback' ? link.frozen_snapshot?.checksum_hash : link.planned_checksum_hash) || '' }]))
    const stamp = ''
    setWorkflowVersions(versions); workflowInitial.current = JSON.stringify({versions,start:stamp,end:stamp})
    setRecoveryChangeId(''); setRollbackOutcome(''); setRollbackFollowUp('')
    setWorkflowAction({ changeId, action })
    setWorkflowRationale('')
    setWorkflowImplementedStart(stamp)
    setWorkflowImplementedEnd(stamp)
  }

  const submitWorkflow = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!workflowAction || approvalMissing.length) return
    if (!workflowRationale.trim()) {
      toast.error('Enter rationale before submitting workflow action')
      return
    }
    workflowMutation.mutate({
      changeId: workflowAction.changeId,
      action: workflowAction.action,
      rationale: workflowRationale.trim(),
      implementedStart: workflowAction.action === 'implement' ? workflowImplementedStart : undefined,
      implementedEnd: workflowAction.action === 'implement' ? workflowImplementedEnd : undefined,
    })
  }

  const changeDraftDirty = JSON.stringify(changeForm) !== JSON.stringify(defaultChangeDraft())
  const [readinessField, setReadinessField] = useState<string | null>(null)
  const editingChange = changes.find(item => item.id === editingChangeId)
  const editDirty = Boolean(editingChange && JSON.stringify(changeEditDraft) !== JSON.stringify(changeDraftFromEntity(editingChange)))
  const componentDirty = JSON.stringify(componentForm) !== JSON.stringify(defaultComponentDraft())
  const componentEditing = components.find(item => item.id === editingComponentId)
  const componentEditDirty = Boolean(componentEditing && JSON.stringify(componentEditDraft) !== JSON.stringify(componentDraftFromEntity(componentEditing)))
  const workflowDirty = Boolean(workflowAction && (workflowRationale || recoveryChangeId || rollbackOutcome || rollbackFollowUp || JSON.stringify({versions:workflowVersions,start:workflowImplementedStart,end:workflowImplementedEnd}) !== workflowInitial.current))
  const localDirty = programmeDraftState.dirty || changeDraftDirty || editDirty || componentDirty || componentEditDirty || workflowDirty || Boolean(eventForm.note || editingEventId && JSON.stringify(eventEditDraft) !== JSON.stringify({event_type:selectedChange?.events.find(item => item.id === editingEventId)?.event_type,note:selectedChange?.events.find(item => item.id === editingEventId)?.note || ''}) || Object.values(integrationCheckForm).some(value => value && value !== 'pending') || editingCheckId || baselineLabel || baselineCertification || baselineScope !== 'manual' || baselineDate || baselineEvidence || baselineAto || showCreateRegisterForm && (registerForm.name !== 'Component register' || registerForm.status !== 'active'))
  const isSaving = programmeDraftState.saving || [createChangeMutation,updateChangeMutation,workflowMutation,createComponentMutation,updateComponentMutation,createRegisterMutation,createBaselineMutation,addEventMutation,updateEventMutation,addIntegrationCheckMutation,updateIntegrationCheckMutation].some(mutation => mutation.isPending)
  useDraftNavigationGuard(localDirty || isSaving)
  const discardThen = (dirty: boolean, action: () => void) => { if (isSaving) return; if (dirty) setPendingDiscard(() => action); else action() }
  useEffect(() => {
    if (!editingChangeId || !readinessField) return
    const editor = document.getElementById('change-evidence-editor')
    editor?.querySelectorAll('details').forEach(details => { details.open = true })
    const labels: Record<string, string> = {
      description: 'Description', complexity_classification: 'Complexity', resource_assessment: 'Resource assessment', scheduling_assessment: 'Scheduling assessment',
      justification: 'Justification', evaluation_effect: 'Evaluation: expected effect', evaluation_risk: 'Evaluation: risk',
      evaluation_regulatory_impact: 'Evaluation: regulatory impact', evaluation_ciaa_impact: 'Evaluation: CIAA impact',
      planned_start_at: 'Planned Start', planned_end_at: 'Planned End',
    }
    const label = labels[readinessField.replace(/^missing_/, '')]
    const field = label ? Array.from(editor?.querySelectorAll('label') || []).find(item => item.textContent?.trim() === label)?.querySelector<HTMLElement>('input,textarea,select') : undefined
    if (field) { field.focus(); field.scrollIntoView?.({ block: 'center' }) }
  }, [editingChangeId, readinessField])
  const prerequisiteAction = (code: string) => {
    if (!selectedChange || code.endsWith('_status')) return undefined
    const jump = (target: string) => {
      const element = document.getElementById(target)
      element?.focus(); element?.scrollIntoView?.({ block: 'start' })
    }
    if (code.startsWith('blocking_assessment')) return { label: 'Review assessments', onClick: () => jump('change-assessments') }
    if (code === 'integration_checks') return { label: 'Review integration checks', onClick: () => jump('change-integration-checks') }
    if (code.startsWith('programme_')) return { label: 'Review programme assurance', onClick: () => setActiveTab('programme') }
    if (['certified_platform_baseline', 'platform_baseline_renewal'].includes(code)) return { label: 'Review baselines', onClick: () => setActiveTab('baselines') }
    if (['unknown_component_scope', 'unknown_responsibility'].includes(code)) return { label: 'Review components and register', onClick: () => setActiveTab('components') }
    if (['stale_component_baseline', 'unresolved_approved_scope'].includes(code)) return { label: 'Review approval and scope actions', onClick: () => jump('change-scope-actions') }
    const editable = canEdit && !['verified', 'rolled_back'].includes(selectedChange.status) || canConfigure && selectedChange.status === 'verified' && selectedChange.readiness?.certification_status !== 'not_required' && !selectedChange.readiness?.certification_completed
    if (!editable) return undefined
    return { label: code.startsWith('missing_') ? 'Complete change details' : 'Edit change evidence', onClick: () => discardThen(editDirty, () => {
      setReadinessField(code); setEditingChangeId(selectedChange.id); setChangeEditDraft(changeDraftFromEntity(selectedChange))
    }) }
  }
  const focusChange = (id: string) => {
    setSelectedChangeId(id)
    window.setTimeout(() => {
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
      detailsRef.current?.focus()
      detailsRef.current?.scrollIntoView?.({
        behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'start',
      })
    }, 100)
  }
  const duplicateChangeIntoDraft = (change: ChangeEntry, reopen = false) => discardThen(changeDraftDirty, () => {
    const draft = changeDraftFromEntity(change)
    draft.title = `${change.title} (${reopen ? 're-open' : 'copy'})`
    draft.compliance = {}; draft.testing_org_status = 'pending'; draft.testing_org_approved_at = ''; draft.testing_org_next_due_at = ''
    draft.planned_start_at = ''; draft.planned_end_at = ''
    setChangeForm(draft); setShowCreateChange(true)
  })
  const reopenRejectedChange = (change: ChangeEntry) => duplicateChangeIntoDraft(change, true)

  const downloadReport = async (endpoint: string, filename: string, params?: URLSearchParams) => {
    setDownloadingReport(endpoint)
    try {
      const url = params ? `${endpoint}?${params.toString()}` : endpoint
      const response = await api.get(url, { responseType: 'blob' })
      const blob = new Blob([response.data])
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = filename
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (error) {
      notifyApiError(toast, error, 'Failed to download report')
    } finally {
      setDownloadingReport(null)
    }
  }

  const renderRegisterRequiredState = (title: string, summary: string) => (
    <Card className="space-y-2 p-6">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <p className="text-sm text-muted">No register configured for this jurisdiction yet.</p>
      <p className="text-sm text-muted">{summary}</p>
      {canConfigure ? (
        <p className="text-sm text-ink">Use the register setup form above to create the first register.</p>
      ) : (
        <p className="text-sm text-ink">Ask a manager or admin to create the component register.</p>
      )}
    </Card>
  )

  if (registersQuery.isError) return <div className="space-y-4"><h1 className="text-2xl font-semibold text-ink">Change Management</h1><LoadError subject="Component registers" onRetry={() => registersQuery.refetch()} /></div>

  return (
    <div data-tour="changes-page" className="workflow-page change-page min-w-0 space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Change Management</h1>
        <p className="mt-1 text-sm text-muted">
          Controlled changes and release evidence
        </p>
        {jurisdictionId && jurisdictionById[jurisdictionId] && (
          <p className="mt-1 text-sm text-muted">Jurisdiction: {jurisdictionById[jurisdictionId].name}</p>
        )}
      </div>

      {requestedChangeId && linkedChangeQuery.isError && <LoadError subject="Linked change" onRetry={() => linkedChangeQuery.refetch()} />}
      <SectionNav label="Change management sections" value={activeTab} items={tabs.filter(tab => tab.id !== 'programme' || danish)} onChange={(value) => setActiveTab(value as TabId)} />

      {!jurisdictionId && (
        <Card className="p-6 text-sm text-muted">
          Select a jurisdiction to manage component and change registers.
        </Card>
      )}

      {jurisdictionId && !(activeTab === 'changes' && selectedChange) && (
        <Card className="space-y-3 p-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 max-w-full flex-wrap items-center gap-3">
                <label className="text-sm font-medium text-ink">Component Register</label>
                <select aria-label="Component Register"
                  className="w-full min-w-0 max-w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm sm:w-auto"
                  value={selectedRegisterId || ''}
                  disabled={!registers.length}
                  onChange={(event) => { const value = event.target.value; discardThen(localDirty, () => { setChangeForm(defaultChangeDraft()); setComponentForm(defaultComponentDraft()); setEventForm({event_type:'note',note:''}); setIntegrationCheckForm({action:'',action_reference:'',result:'pending',completed_at:'',notes:'',evidence_notes:''}); setBaselineLabel(''); setBaselineCertification('')
      setBaselineScope('manual'); setBaselineDate(''); setBaselineEvidence(''); setBaselineAto(''); setWorkflowRationale(''); setSelectedChangeId(null); setSelectedRegisterId(value || null) }) }}
                >
                  <option value="">{registersQuery.isPending ? 'Loading registers…' : registers.length ? 'Select Register' : 'No Registers Available'}</option>
                  {registers.map((register) => (
                    <option key={register.id} value={register.id}>
                      {register.name} ({formatOptionLabel(register.status)})
                    </option>
                  ))}
                </select>
              </div>
              {canConfigure && (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={registersQuery.isPending || registersQuery.isError}
                  onClick={() => setShowCreateRegisterForm((prev) => !prev)}
                >
                  {showCreateRegisterForm ? 'Cancel' : 'Create Register'}
                </Button>
              )}
            </div>

            {selectedRegister && (
              <details className="text-sm text-muted">
                <summary className="cursor-pointer">Register details</summary>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink">{selectedRegister.name}</span>
                <Badge tone={selectedRegister.status === 'active' ? 'green' : 'slate'}>
                  {formatOptionLabel(selectedRegister.status)}
                </Badge>
                <span>Created {formatDate(selectedRegister.created_at)}</span>
                </div>
              </details>
            )}

            {!registersQuery.isLoading && !selectedRegister && (
              <p className="text-sm text-muted">No register configured for this jurisdiction yet.</p>
            )}
          </div>

          {canConfigure && showCreateRegisterForm && (
            <form
              className="grid grid-cols-1 gap-3 rounded-xl border border-line bg-canvas/70 p-3 md:grid-cols-4"
              onSubmit={(event) => {
                event.preventDefault()
                createRegisterMutation.mutate()
              }}
            >
              <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted md:col-span-2"><span>Register name *</span><input aria-label="Register name"
                value={registerForm.name}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Register name"
                className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm "
                required
              /></label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted"><span>Register status</span><select
                value={registerForm.status}
                onChange={(event) => setRegisterForm((prev) => ({ ...prev, status: event.target.value }))}
                className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select></label>
              <Button variant="primary" loading={createRegisterMutation.isPending} type="submit">
                Save Register
              </Button>
            </form>
          )}

          {!canConfigure && !selectedRegister && (
            <p className="text-sm text-ink">
              Register setup is restricted to manager and admin roles. Ask a manager/admin to create the first
              register for this jurisdiction.
            </p>
          )}
        </Card>
      )}

      {jurisdictionId && activeTab === 'programme' && danish && (selectedRegister ? <ChangeProgramme key={selectedRegister.id} register={selectedRegister} canEdit={canConfigure} onDraftState={onProgrammeDraftState} /> : renderRegisterRequiredState('Programme assurance', 'Select or create a register to record governance and annual certification.'))}

      {jurisdictionId && activeTab === 'components' &&
        (componentsQuery.isError ? <LoadError subject="Components" onRetry={() => componentsQuery.refetch()} /> : !selectedRegisterId ? (
          renderRegisterRequiredState(
            'Components',
            'Register components with CIAA classification, hosting model, checksum, and location details.'
          )
        ) : (
          <div className="space-y-6">
            {canEdit && (
              <details ref={componentCreateDetails} className="rounded-xl border border-line bg-surface p-4">
                <summary className="cursor-pointer text-sm font-semibold text-accent">Add Component</summary><div className="mt-4 space-y-3">
                <p className="text-xs text-muted">
                  CIAA codes must be 1-3. Final classification is the highest CIAA value. Classification 3 requires
                  checksum/hash. Hardware requires geographic location unless public-cloud exemption criteria are met.
                </p>
                <form
                  className="grid grid-cols-1 gap-3 md:grid-cols-2"
                  onSubmit={(event: FormEvent<HTMLFormElement>) => {
                    event.preventDefault()
                    createComponentMutation.mutate()
                  }}
                >
                  <ComponentFields draft={componentForm} setDraft={setComponentForm} />
                  <div className="md:col-span-2">
                    <Button variant="primary" loading={createComponentMutation.isPending} type="submit">
                      Add Component
                    </Button>
                  </div>
                </form>
              </div></details>
            )}

            <Card className="space-y-3 p-4">
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Search components</span><input aria-label="Search components"
                  placeholder="Search components"
                  value={componentFilters.q}
                  onChange={(event) => setComponentFilters((prev) => ({ ...prev, q: event.target.value }))}
                  className="w-full min-w-[220px] rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Status</span><select aria-label="Status" value={componentFilters.status}
                  onChange={(event) => setComponentFilters((prev) => ({ ...prev, status: event.target.value }))}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Statuses</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="retired">Retired</option>
                </select></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Classification</span><select aria-label="Classification" value={componentFilters.classification}
                  onChange={(event) =>
                    setComponentFilters((prev) => ({ ...prev, classification: event.target.value }))
                  }
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Classifications</option>
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="3">3</option>
                </select></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Hosting</span><select aria-label="Hosting" value={componentFilters.hosting_model}
                  onChange={(event) =>
                    setComponentFilters((prev) => ({ ...prev, hosting_model: event.target.value }))
                  }
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Hosting</option>
                  <option value="on_prem">On Prem</option>
                  <option value="private_cloud">Private Cloud</option>
                  <option value="public_cloud">Public Cloud</option>
                </select></label>
                <Button
                  variant="secondary"
                  onClick={() =>
                    downloadClientCsv(
                      'change-management-components-filtered.csv',
                      ['uid', 'version', 'classification', 'status', 'owner', 'hosting', 'location'],
                      filteredComponents.map((component) => [
                        component.component_uid,
                        component.version,
                        component.classification_code,
                        component.status,
                        component.change_owner_name,
                        component.hosting_model,
                        component.geographic_location,
                      ])
                    )
                  }
                >
                  Export Filtered CSV
                </Button>
              </div>

              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>UID</TH>
                      <TH>Version</TH>
                      <TH>Classification</TH>
                      <TH>Status</TH>
                      <TH>Owner</TH>
                      <TH>Hosting</TH>
                      <TH>Location</TH>
                      <TH>Actions</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {filteredComponents.length === 0 && <TableEmpty colSpan={8}>No matching components.</TableEmpty>}
                    {filteredComponents.map((component) => (
                      <TR key={component.id}>
                        <TD>{component.component_uid}</TD>
                        <TD>{component.version}</TD>
                        <TD>{component.classification_code}</TD>
                        <TD>
                          <Badge tone={componentStatusTone(component.status)}>{formatOptionLabel(component.status)}</Badge>
                        </TD>
                        <TD>{component.change_owner_name || '-'}</TD>
                        <TD>{formatOptionLabel(component.hosting_model)}</TD>
                        <TD>{component.geographic_location || '-'}</TD>
                        <TD>
                          {canEdit && (
                            <div className="flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                  setEditingComponentId(component.id)
                                  setComponentEditDraft(componentDraftFromEntity(component))
                                }}
                              >
                                Edit
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                loading={deleteComponentMutation.isPending}
                                onClick={() => {
                                  setPendingComponentDelete({
                                    componentId: component.id,
                                    label: component.component_uid,
                                  })
                                }}
                              >
                                Delete
                              </Button>
                            </div>
                          )}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            </Card>

            {editingComponentId && (
              <Card className="space-y-3 p-6">
                <h3 className="text-base font-semibold text-ink">Edit Component</h3>
                <form
                  className="grid grid-cols-1 gap-3 md:grid-cols-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    updateComponentMutation.mutate(editingComponentId)
                  }}
                >
                  <ComponentFields autoFocus draft={componentEditDraft} setDraft={setComponentEditDraft} />
                  <div className="md:col-span-2 flex flex-wrap gap-2">
                    <Button variant="primary" type="submit" loading={updateComponentMutation.isPending}>
                      Save Component
                    </Button>
                    <Button variant="secondary" onClick={() => discardThen(componentEditDirty, () => setEditingComponentId(null))}>
                      Cancel
                    </Button>
                    <Button
                      variant="secondary"
                      loading={deleteComponentMutation.isPending}
                      onClick={() => {
                        if (!editingComponentId) return
                        setPendingComponentDelete({
                          componentId: editingComponentId,
                          label: componentEditDraft.component_uid || 'this component',
                        })
                      }}
                    >
                      Delete Component
                    </Button>
                  </div>
                </form>
              </Card>
            )}
          </div>
        ))}

      {jurisdictionId && activeTab === 'changes' &&
        (changesQuery.isError ? <LoadError subject="Changes" onRetry={() => changesQuery.refetch()} /> : !selectedRegisterId ? (
          renderRegisterRequiredState(
            'Change Register',
            'Log proposals, approvals, implementation, verification, integration actions, and timeline evidence.'
          )
        ) : (
          <div className="space-y-6">
            {selectedChange && <Button variant="ghost" onClick={() => discardThen(localDirty, () => setSelectedChangeId(null))}>← Back to changes</Button>}
            {!selectedChange && canEdit && <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted">Select a change to review its evidence and next steps.</p><Button variant="primary" onClick={() => setShowCreateChange(true)}>New change</Button></div>}
            <Modal open={showCreateChange} title="New change" description="Save a draft with a title, then complete the impact evaluation and evidence before approval." size="lg" onClose={() => discardThen(changeDraftDirty, () => {setShowCreateChange(false); setChangeForm(defaultChangeDraft())})}>
              <form className="grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={event => { event.preventDefault(); createChangeMutation.mutate() }}>
                <ChangeProposalFields autoFocus draft={changeForm} setDraft={setChangeForm} components={components} danish={danish} />
                {createChangeMutation.isError && <p role="alert" className="text-sm text-danger md:col-span-2">{getApiErrorMessage(createChangeMutation.error, 'Could not save the draft. Your entries are preserved.')}</p>}
                <div className="md:col-span-2 flex gap-2"><Button variant="primary" loading={createChangeMutation.isPending} type="submit">Save draft</Button><Button onClick={() => discardThen(changeDraftDirty, () => {setShowCreateChange(false);setChangeForm(defaultChangeDraft())})}>Cancel</Button></div>
              </form>
            </Modal>

            {!selectedChange && <Card className="space-y-3 p-4">
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Search changes</span><input aria-label="Search changes"
                  placeholder="Search changes"
                  value={changeFilters.q}
                  onChange={(event) => setChangeFilters((prev) => ({ ...prev, q: event.target.value }))}
                  className="w-full min-w-[220px] rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                /></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Status</span><select aria-label="Status" value={changeFilters.status}
                  onChange={(event) => setChangeFilters((prev) => ({ ...prev, status: event.target.value }))}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Statuses</option><option value="attention">Needs attention</option>
                  <option value="draft">Draft</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="implemented">Implemented</option>
                  <option value="verified">Verified</option><option value="rolled_back">Rolled back</option>
                </select></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Change type</span><select aria-label="Change type" value={changeFilters.change_type}
                  onChange={(event) => setChangeFilters((prev) => ({ ...prev, change_type: event.target.value }))}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Types</option>
                  <option value="standard">Standard</option>
                  <option value="normal">Normal</option>
                  <option value="emergency">Emergency</option>
                </select></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Integration</span><select aria-label="Integration" value={changeFilters.integration}
                  onChange={(event) => setChangeFilters((prev) => ({ ...prev, integration: event.target.value }))}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="all">All Integration Flags</option>
                  <option value="yes">Integration Related: Yes</option>
                  <option value="no">Integration Related: No</option>
                </select></label>
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Affected component</span><select aria-label="Affected component" value={changeFilters.component_id}
                  onChange={(event) => setChangeFilters((prev) => ({ ...prev, component_id: event.target.value }))}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="">All Linked Components</option>
                  {components.map((component) => (
                    <option key={component.id} value={component.id}>
                      {component.component_uid}
                    </option>
                  ))}
                </select></label>
                <Button
                  variant="secondary"
                  onClick={() =>
                    downloadClientCsv(
                      'change-management-changes-filtered.csv',
                      ['title', 'status', 'type', 'components', 'integration_related', 'updated_at'],
                      filteredChanges.map((change) => [
                        change.title,
                        change.status,
                        change.change_type,
                        change.components.length,
                        change.integration_related,
                        change.updated_at,
                      ])
                    )
                  }
                >
                  Export Filtered CSV
                </Button>
              </div>

              <ul className="divide-y divide-line" aria-label="Changes">
                {!filteredChanges.length && <li className="py-4 text-sm text-muted">No matching changes.</li>}
                {filteredChanges.map(change => <li key={change.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
                  <div className="min-w-0 flex-1"><h3 className="break-words font-semibold text-ink">{change.title}</h3><div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted"><Badge tone={changeStatusTone(change.status)}>{formatOptionLabel(change.status)}</Badge><span>{formatOptionLabel(change.change_type)} · {change.components.length} components</span><span>Updated {formatDate(change.updated_at)}</span></div>{change.readiness?.certification_due_at && <p className="mt-2 text-xs text-muted">Certification due {formatDate(change.readiness.certification_due_at)}</p>}</div>
                  <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => focusChange(change.id)}>Details</Button>{canEdit && <Button size="sm" onClick={() => duplicateChangeIntoDraft(change)}>Duplicate</Button>}</div>
                </li>)}
              </ul>
            </Card>}

            {workflowAction && workflowChange && (
              <Modal open title={`${formatOptionLabel(workflowAction.action)}: ${workflowChange.title}`} size="lg" onClose={() => discardThen(workflowDirty, () => setWorkflowAction(null))}>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 id="change-workflow-heading" tabIndex={-1} className="min-w-0 scroll-mt-24 break-words text-base font-semibold text-ink">{workflowLabel}: {workflowChange.title}</h3>
                  <Badge tone={changeStatusTone(workflowChange.status)}>{formatOptionLabel(workflowChange.status)}</Badge>
                </div>
                <ChangeRecordSummary change={workflowChange} components={components} compact />
                {approvalMissing.length > 0 ? <div className="mt-4 space-y-3">
                  <p className="text-sm text-muted">Finish these proposal details before approval:</p>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{approvalMissing.map(detail => <li key={detail}>{detail}</li>)}</ul>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="primary" disabled={Boolean(editingChangeId && editingChangeId !== workflowChange.id)} onClick={() => { if (!editingChangeId) { setEditingChangeId(workflowChange.id); setChangeEditDraft(changeDraftFromEntity(workflowChange)) } setWorkflowAction(null) }}>Complete proposal details</Button>
                    <Button onClick={() => setWorkflowAction(null)}>Cancel</Button>
                  </div>
                  {editingChangeId && editingChangeId !== workflowChange.id && <p className="text-sm text-muted">Save or cancel your open proposal before editing another change.</p>}
                </div> : <form aria-labelledby="change-workflow-heading" className="space-y-3 mt-4" onSubmit={submitWorkflow}>
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Enter required rationale *</span><textarea autoFocus data-autofocus aria-label="Enter required rationale"
                    value={workflowRationale}
                    onChange={(event) => setWorkflowRationale(event.target.value)}
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                    placeholder="Enter required rationale"
                    required
                  /></label>
                  {workflowAction.action === 'implement' && (
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      <p className="text-sm text-muted md:col-span-2">Record when implementation actually started and finished.</p>
                      <label className="space-y-1 text-xs font-medium text-muted">
                        <span>Implemented Start</span>
                        <input
                          type="datetime-local" step="1"
                          max={workflowStamp()}
                          value={workflowImplementedStart}
                          onChange={(event) => setWorkflowImplementedStart(event.target.value)}
                          className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                          required
                        />
                      </label>
                      <label className="space-y-1 text-xs font-medium text-muted">
                        <span>Implemented End</span>
                        <input
                          type="datetime-local" step="1"
                          min={workflowImplementedStart || undefined}
                          max={workflowStamp()}
                          value={workflowImplementedEnd}
                          onChange={(event) => setWorkflowImplementedEnd(event.target.value)}
                          className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                          required
                        />
                      </label>
                    </div>
                  )}
                  {(workflowAction.action === 'implement' || workflowAction.action === 'rollback') && <fieldset className="space-y-3"><legend className="text-sm font-semibold">Actual component versions</legend>{Object.entries(workflowVersions).map(([id, value]) => <div key={id} className="grid gap-2 sm:grid-cols-2"><label className="text-sm">{components.find(c => c.id === id)?.component_uid || id} — actual version<input required className="mt-1 w-full rounded-lg border border-line bg-canvas p-2" value={value.version} onChange={event => setWorkflowVersions(prev => ({...prev,[id]:{...value,version:event.target.value}}))} /></label><label className="text-sm">Actual checksum<input required={selectedChange?.components.find(link => link.component_id === id)?.frozen_snapshot?.classification_code === 3} className="mt-1 w-full rounded-lg border border-line bg-canvas p-2" value={value.checksum} onChange={event => setWorkflowVersions(prev => ({...prev,[id]:{...value,checksum:event.target.value}}))} /></label></div>)}</fieldset>}
                  {workflowAction.action === 'rollback' && <><label className="block text-sm">Approved recovery change<select required className="mt-1 w-full rounded-lg border border-line bg-canvas p-2" value={recoveryChangeId} onChange={event => {const id=event.target.value;setRecoveryChangeId(id);const recovery=changes.find(item => item.id === id);if (recovery) setWorkflowVersions(Object.fromEntries((selectedChange?.components || []).map(link => {const restored=recovery.components.find(item => item.component_id === link.component_id);return [link.component_id,{version:restored?.implemented_version || '',checksum:restored?.implemented_checksum_hash || ''}]})))}}><option value="">Select an implemented recovery change</option>{changes.filter(item => item.id !== workflowAction.changeId && ['implemented','verified'].includes(item.status)).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><p className="text-sm text-muted">Record the separately approved recovery and the versions already observed. CAP does not execute software rollback.</p><label className="block text-sm">Rollback outcome<textarea required className="mt-1 w-full rounded-lg border border-line bg-canvas p-2" value={rollbackOutcome} onChange={event => setRollbackOutcome(event.target.value)} /></label><label className="block text-sm">Follow-up action<textarea required className="mt-1 w-full rounded-lg border border-line bg-canvas p-2" value={rollbackFollowUp} onChange={event => setRollbackFollowUp(event.target.value)} /></label></>}
                  {workflowMutation.isError && <p role="alert" className="text-sm text-danger">{getApiErrorMessage(workflowMutation.error, 'Could not record this action. Your entries are preserved.')}</p>}
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" variant="primary" loading={workflowMutation.isPending}>
                      {workflowLabel}
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => discardThen(workflowDirty, () => setWorkflowAction(null))}>
                      Cancel
                    </Button>
                  </div>
                </form>}
              </Modal>
            )}

            {editingChangeId && (
              <Modal open title={`Edit: ${editingChange?.title || 'Change'}`} size="lg" onClose={() => discardThen(editDirty, () => setEditingChangeId(null))}>
                <form
                  id="change-evidence-editor"
                  className="grid grid-cols-1 gap-3 md:grid-cols-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    updateChangeMutation.mutate(editingChangeId)
                  }}
                >
                  <ChangeProposalFields danish={danish} autoFocus proposalReadOnly={['approved', 'implemented', 'verified'].includes(changes.find((item) => item.id === editingChangeId)?.status || '')} draft={changeEditDraft} setDraft={setChangeEditDraft} components={components} />
                  <div className="md:col-span-2 flex flex-wrap gap-2">
                    <Button variant="primary" type="submit" loading={updateChangeMutation.isPending}>
                      Save Change
                    </Button>
                    <Button variant="secondary" onClick={() => discardThen(editDirty, () => setEditingChangeId(null))}>
                      Cancel
                    </Button>
                  </div>
                </form>
              </Modal>
            )}

            {selectedChange && (
              <Card data-tour="change-detail" className="change-detail-surface space-y-4 p-6">
                <div ref={detailsRef} tabIndex={-1} className="scroll-mt-6 outline-none focus-visible:ring-2 focus-visible:ring-accent">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="change-detail-title">{selectedChange.title}</h2>
                  <Badge tone={changeStatusTone(selectedChange.status)}>
                    {formatOptionLabel(selectedChange.status)}
                  </Badge>
                </div>

                <nav className="change-record-navigation" aria-label="Change record sections">
                  {[['change-readiness', 'Readiness'], ['change-component-scope', 'Scope & components'], ['change-assessments', 'Assessments'], ['change-implementation-record', 'Implementation'], ['change-record-history', 'History']].map(([id, label]) => <a key={id} href={`#${id}`} onClick={() => { const section = document.getElementById(id); if (section instanceof HTMLDetailsElement) section.open = true }}>{label}</a>)}
                </nav>
                <ChangeRecordSummary readinessExpected={danish} change={selectedChange} components={components} prerequisiteAction={prerequisiteAction} actions={canConfigure && ['draft','rejected'].includes(selectedChange.status) ? <><Button variant="primary" disabled={selectedChange.readiness?.approval?.ready === false || danish && selectedChange.readiness?.approval?.ready !== true} aria-describedby="change-approval-help" onClick={() => openWorkflow(selectedChange.id,'approve')}>{!danish && !selectedChange.readiness?.approval ? 'Review proposal' : 'Approve change'}</Button><p id="change-approval-help">{!selectedChange.readiness?.approval && danish ? 'Unavailable until readiness can be checked' : selectedChange.readiness?.approval.ready === false ? 'Available when required checks pass' : missingApprovalDetails(selectedChange, danish).length > 0 ? 'Complete proposal details before approval' : 'Records internal approval only'}</p></> : undefined} />
                <div id="change-scope-actions" tabIndex={-1} className="scroll-mt-24">{canConfigure && danish && ['implemented','verified'].includes(selectedChange.status) && selectedChange.components.some(link => !link.frozen_snapshot) && <HistoricalChangeScope key={selectedChange.id} change={selectedChange} components={components} responsibilityRole={selectedRegister?.responsibility_role} />}
                <div className="flex flex-wrap gap-2">
                  {(canEdit && !['verified','rolled_back'].includes(selectedChange.status) || canConfigure && selectedChange.status === 'verified' && selectedChange.readiness?.certification_status !== 'not_required' && !selectedChange.readiness?.certification_completed) && <Button onClick={() => {setReadinessField(null);setEditingChangeId(selectedChange.id);setChangeEditDraft(changeDraftFromEntity(selectedChange))}}>Edit change evidence</Button>}
                  {canConfigure && ['draft','approved'].includes(selectedChange.status) && <Button onClick={() => openWorkflow(selectedChange.id,'reject')}>Reject</Button>}
                  {canEdit && selectedChange.status === 'approved' && <Button variant="primary" disabled={selectedChange.readiness?.implementation?.ready === false || danish && selectedChange.readiness?.implementation?.ready !== true} onClick={() => openWorkflow(selectedChange.id,'implement')}>Record implementation</Button>}
                  {canConfigure && selectedChange.status === 'implemented' && <Button variant="primary" disabled={selectedChange.readiness?.verification?.ready === false || danish && selectedChange.readiness?.verification?.ready !== true} onClick={() => openWorkflow(selectedChange.id,'verify')}>Verify</Button>}
                  {canConfigure && ['implemented','verified'].includes(selectedChange.status) && <Button onClick={() => openWorkflow(selectedChange.id,'rollback')}>Record rollback</Button>}
                  {canEdit && selectedChange.status === 'rejected' && <Button onClick={() => reopenRejectedChange(selectedChange)}>Re-open Draft</Button>}
                </div></div></div>
                <div id="change-assessments" tabIndex={-1} className="scroll-mt-24"><ChangeAssessments key={selectedChange.id} changeId={selectedChange.id} changeName={selectedChange.title} blockingAssessmentIds={selectedChange.blocking_assessment_ids || []} jurisdictionId={linkedChangeQuery.data?.id === selectedChange.id ? linkedChangeQuery.data.jurisdiction_id || jurisdictionId || '' : selectedRegister?.jurisdiction_id || jurisdictionId || ''} canEdit={canConfigure && ['draft','rejected'].includes(selectedChange.status)} canManage={canConfigure && !['verified','rolled_back'].includes(selectedChange.status)} /></div>

                <div id="change-record-history" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-ink">Timeline Events</h4>
                    <div className="overflow-x-auto rounded-xl border border-line">
                      <Table>
                        <THead>
                          <TR>
                            <TH>When</TH>
                            <TH>Type</TH>
                            <TH>Note</TH>
                            <TH>Actions</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {selectedChange.events.length === 0 && <TableEmpty colSpan={4}>No events yet.</TableEmpty>}
                          {selectedChange.events.map((event) => (
                            <TR key={event.id}>
                              <TD>{formatDate(event.created_at)}</TD>
                              <TD>{formatOptionLabel(event.event_type)}</TD>
                              <TD>{event.note || '-'}</TD>
                              <TD>
                                <div className="flex flex-wrap gap-2">
                                  {canEdit && event.event_type !== 'status_change' && !event.deleted_at && (
                                    <>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        onClick={() => {
                                          setEditingEventId(event.id)
                                          setEventEditDraft({
                                            event_type:
                                              event.event_type === 'decision' || event.event_type === 'status_change'
                                                ? event.event_type
                                                : 'note',
                                            note: event.note || '',
                                          })
                                        }}
                                      >
                                        Edit
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        onClick={() => {
                                          if (!selectedChangeId) return
                                          setPendingEventDelete({
                                            changeId: selectedChangeId,
                                            eventId: event.id,
                                            reason: '',
                                          })
                                        }}
                                      >
                                        Delete
                                      </Button>
                                    </>
                                  )}
                                  {event.deleted_at && <Badge tone="amber">Deleted</Badge>}
                                </div>
                              </TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h4 id="change-integration-checks" tabIndex={-1} className="scroll-mt-24 text-sm font-semibold text-ink">Integration Checks</h4>
                    <div className="overflow-x-auto rounded-xl border border-line">
                      <Table>
                        <THead>
                          <TR>
                            <TH>Action</TH>
                            <TH>Result</TH>
                            <TH>Completed</TH>
                            <TH>Evidence</TH>
                            <TH>Actions</TH>
                          </TR>
                        </THead>
                        <TBody>
                          {selectedChange.integration_checks.length === 0 && (
                            <TableEmpty colSpan={5}>No integration checks recorded.</TableEmpty>
                          )}
                          {selectedChange.integration_checks.map((check) => (
                            <TR key={check.id}>
                              <TD>{check.action}</TD>
                              <TD>{formatOptionLabel(check.result)}</TD>
                              <TD>{formatDate(check.completed_at)}</TD>
                              <TD>{check.evidence_notes || '-'}</TD>
                              <TD>
                                <div className="flex flex-wrap gap-2">
                                  {canEdit && selectedChange.status !== 'verified' && !check.deleted_at && (
                                    <>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        onClick={() => {
                                          setEditingCheckId(check.id)
                                          setIntegrationCheckEditDraft({
                                            action: check.action,
                                            action_reference: check.action_reference || '',
                                            result: check.result === 'pass' || check.result === 'fail' ? check.result : 'pending',
                                            completed_at: toInputDateTime(check.completed_at),
                                            notes: check.notes || '',
                                            evidence_notes: check.evidence_notes || '',
                                          })
                                        }}
                                      >
                                        Edit
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="secondary"
                                        onClick={() => {
                                          if (!selectedChangeId) return
                                          setPendingIntegrationCheckDelete({
                                            changeId: selectedChangeId,
                                            checkId: check.id,
                                            reason: '',
                                          })
                                        }}
                                      >
                                        Delete
                                      </Button>
                                    </>
                                  )}
                                  {check.deleted_at && <Badge tone="amber">Deleted</Badge>}
                                </div>
                              </TD>
                            </TR>
                          ))}
                        </TBody>
                      </Table>
                    </div>
                  </div>
                </div>

                {canEdit && selectedChangeId && selectedChange?.status !== 'verified' && (
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <form
                      className="space-y-3 rounded-xl border border-line bg-canvas/70 p-4"
                      onSubmit={(event) => {
                        event.preventDefault()
                        addEventMutation.mutate(selectedChangeId)
                      }}
                    >
                      <h4 className="text-sm font-semibold text-ink">Add Event</h4>
                      <select aria-label="Event type"
                        value={eventForm.event_type}
                        onChange={(event) =>
                          setEventForm((prev) => ({ ...prev, event_type: event.target.value as ChangeEventType }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      >
                        <option value="note">Note</option>
                        <option value="decision">Decision</option>
                        <option value="status_change">Status Change</option>
                      </select>
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Event note *</span><textarea aria-label="Event note"
                        value={eventForm.note}
                        onChange={(event) => setEventForm((prev) => ({ ...prev, note: event.target.value }))}
                        placeholder="Event note"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        required={eventForm.event_type !== 'status_change'}
                      /></label>
                      <Button variant="primary" loading={addEventMutation.isPending} type="submit">
                        Add Event
                      </Button>
                    </form>

                    <form
                      className="space-y-3 rounded-xl border border-line bg-canvas/70 p-4"
                      onSubmit={(event) => {
                        event.preventDefault()
                        addIntegrationCheckMutation.mutate(selectedChangeId)
                      }}
                    >
                      <h4 className="text-sm font-semibold text-ink">Add Integration Check</h4>
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Action *</span><input aria-label="Action"
                        value={integrationCheckForm.action}
                        onChange={(event) =>
                          setIntegrationCheckForm((prev) => ({ ...prev, action: event.target.value }))
                        }
                        placeholder="Action"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        required
                      /></label>
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Action reference</span><input aria-label="Action reference"
                        value={integrationCheckForm.action_reference}
                        onChange={(event) =>
                          setIntegrationCheckForm((prev) => ({ ...prev, action_reference: event.target.value }))
                        }
                        placeholder="Action reference"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      /></label>
                      <label className="block space-y-1 text-xs font-medium text-muted"><span>Check result</span><select aria-label="Check result"
                        value={integrationCheckForm.result}
                        onChange={(event) =>
                          setIntegrationCheckForm((prev) => ({
                            ...prev,
                            result: event.target.value as IntegrationResult,
                          }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      >
                        <option value="pending">Pending</option>
                        <option value="pass">Pass</option>
                        <option value="fail">Fail</option>
                      </select></label>
                      <label className="space-y-1 text-xs font-medium text-muted">
                        <span>Completed At</span>
                        <input
                          type="datetime-local"
                          value={integrationCheckForm.completed_at}
                          onChange={(event) =>
                            setIntegrationCheckForm((prev) => ({ ...prev, completed_at: event.target.value }))
                          }
                          className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        />
                      </label>
                      <textarea aria-label="Notes"
                        value={integrationCheckForm.notes}
                        onChange={(event) =>
                          setIntegrationCheckForm((prev) => ({ ...prev, notes: event.target.value }))
                        }
                        placeholder="Notes"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      />
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Evidence notes</span><textarea aria-label="Evidence notes"
                        value={integrationCheckForm.evidence_notes}
                        onChange={(event) =>
                          setIntegrationCheckForm((prev) => ({ ...prev, evidence_notes: event.target.value }))
                        }
                        placeholder="Evidence notes"
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      /></label>
                      <Button variant="primary" loading={addIntegrationCheckMutation.isPending} type="submit">
                        Add Integration Check
                      </Button>
                    </form>
                  </div>
                )}

                {editingEventId && selectedChangeId && (
                  <Card className="space-y-3 border border-line p-4">
                    <h4 className="text-sm font-semibold text-ink">Edit Event</h4>
                    <form
                      className="space-y-3"
                      onSubmit={(event) => {
                        event.preventDefault()
                        updateEventMutation.mutate({ changeId: selectedChangeId, eventId: editingEventId })
                      }}
                    >
                      <select aria-label="Edit event type"
                        value={eventEditDraft.event_type}
                        onChange={(event) =>
                          setEventEditDraft((prev) => ({
                            ...prev,
                            event_type: event.target.value as ChangeEventType,
                          }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      >
                        <option value="note">Note</option>
                        <option value="decision">Decision</option>
                        <option value="status_change">Status Change</option>
                      </select>
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Event note</span><textarea aria-label="Event note"
                        value={eventEditDraft.note}
                        onChange={(event) => setEventEditDraft((prev) => ({ ...prev, note: event.target.value }))}
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        placeholder="Event note"
                      /></label>
                      <div className="flex flex-wrap gap-2">
                        <Button type="submit" variant="primary" loading={updateEventMutation.isPending}>
                          Save Event
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => setEditingEventId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </form>
                  </Card>
                )}

                {editingCheckId && selectedChangeId && (
                  <Card className="space-y-3 border border-line p-4">
                    <h4 className="text-sm font-semibold text-ink">Edit Integration Check</h4>
                    <form
                      className="space-y-3"
                      onSubmit={(event) => {
                        event.preventDefault()
                        updateIntegrationCheckMutation.mutate({ changeId: selectedChangeId, checkId: editingCheckId })
                      }}
                    >
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Action *</span><input aria-label="Action"
                        value={integrationCheckEditDraft.action}
                        onChange={(event) =>
                          setIntegrationCheckEditDraft((prev) => ({ ...prev, action: event.target.value }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        placeholder="Action"
                        required
                      /></label>
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Action reference</span><input aria-label="Action reference"
                        value={integrationCheckEditDraft.action_reference}
                        onChange={(event) =>
                          setIntegrationCheckEditDraft((prev) => ({ ...prev, action_reference: event.target.value }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        placeholder="Action reference"
                      /></label>
                      <label className="block space-y-1 text-xs font-medium text-muted"><span>Check result</span><select aria-label="Check result"
                        value={integrationCheckEditDraft.result}
                        onChange={(event) =>
                          setIntegrationCheckEditDraft((prev) => ({
                            ...prev,
                            result: event.target.value as IntegrationResult,
                          }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                      >
                        <option value="pending">Pending</option>
                        <option value="pass">Pass</option>
                        <option value="fail">Fail</option>
                      </select></label>
                      <label className="space-y-1 text-xs font-medium text-muted">
                        <span>Completed At</span>
                        <input
                          type="datetime-local"
                          value={integrationCheckEditDraft.completed_at}
                          onChange={(event) =>
                            setIntegrationCheckEditDraft((prev) => ({ ...prev, completed_at: event.target.value }))
                          }
                          className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        />
                      </label>
                      <textarea aria-label="Notes"
                        value={integrationCheckEditDraft.notes}
                        onChange={(event) =>
                          setIntegrationCheckEditDraft((prev) => ({ ...prev, notes: event.target.value }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        placeholder="Notes"
                      />
                      <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Evidence notes</span><textarea aria-label="Evidence notes"
                        value={integrationCheckEditDraft.evidence_notes}
                        onChange={(event) =>
                          setIntegrationCheckEditDraft((prev) => ({ ...prev, evidence_notes: event.target.value }))
                        }
                        className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                        placeholder="Evidence notes"
                      /></label>
                      <div className="flex flex-wrap gap-2">
                        <Button type="submit" variant="primary" loading={updateIntegrationCheckMutation.isPending}>
                          Save Integration Check
                        </Button>
                        <Button type="button" variant="secondary" onClick={() => setEditingCheckId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </form>
                  </Card>
                )}

                <Card className="space-y-3 border border-line p-4">
                  <h4 className="text-sm font-semibold text-ink">Activity Timeline</h4>
                  {activityQuery.isError ? <LoadError subject="Activity timeline" onRetry={() => activityQuery.refetch()} /> : activityQuery.isLoading ? <p role="status" className="text-sm text-muted">Loading activity…</p> : <div className="overflow-x-auto">
                    <Table>
                      <THead>
                        <TR>
                          <TH>When</TH>
                          <TH>Type</TH>
                          <TH>Action</TH>
                          <TH>Detail</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {(activityQuery.data?.items || []).length === 0 && (
                          <TableEmpty colSpan={4}>No activity captured yet.</TableEmpty>
                        )}
                        {(activityQuery.data?.items || []).map((item) => (
                          <TR key={`${item.activity_type}-${item.id}-${item.occurred_at}`}>
                            <TD>{formatDate(item.occurred_at)}</TD>
                            <TD>{formatOptionLabel(item.activity_type)}</TD>
                            <TD>{item.action}</TD>
                            <TD>{item.detail || '-'}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  </div>}
                </Card>
              </Card>
            )}
          </div>
        ))}

      {jurisdictionId && activeTab === 'baselines' &&
        (baselinesQuery.isError ? <LoadError subject="Baselines" onRetry={() => baselinesQuery.refetch()} /> : !selectedRegisterId ? (
          renderRegisterRequiredState(
            'Baselines',
            'Freeze immutable snapshots and compare current register state against prior baselines.'
          )
        ) : (
          <div className="space-y-6">
            {canConfigure && (
              <Card className="space-y-3 p-6">
                <h2 className="text-lg font-semibold text-ink">Create baseline snapshot</h2>
                <p className="text-sm text-muted">For Denmark, record the initial whole-platform certified baseline and renew it annually. A manual snapshot provides a comparison but does not establish certification.</p>
                <form
                  className="grid gap-3 sm:grid-cols-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    createBaselineMutation.mutate()
                  }}
                >
                  <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Baseline label *</span><input aria-label="Baseline label"
                    value={baselineLabel}
                    onChange={(event) => setBaselineLabel(event.target.value)}
                    placeholder="Baseline label"
                    className="w-full rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                    required
                  /></label>
                  <label className="text-sm">Baseline purpose<select className="mt-1 block w-full rounded-lg border border-line bg-canvas p-2" value={baselineScope} onChange={event => setBaselineScope(event.target.value)}><option value="manual">Manual comparison snapshot</option><option value="whole_platform">Certified whole-platform baseline</option></select></label>
                  <label className="text-sm">Certifying report reference{baselineScope === 'whole_platform' ? ' *' : ' (optional)'}<input required={baselineScope === 'whole_platform'} className="mt-1 block w-full rounded-lg border border-line bg-canvas p-2" value={baselineCertification} onChange={event => setBaselineCertification(event.target.value)} /></label>
                  {baselineScope === 'whole_platform' && <>
                    <label className="text-sm">Platform certification date *<input required type="datetime-local" className="mt-1 block w-full rounded-lg border border-line bg-canvas p-2" value={baselineDate} onChange={event => setBaselineDate(event.target.value)} /></label>
                    <label className="text-sm">Accredited testing organisation *<input required className="mt-1 block w-full rounded-lg border border-line bg-canvas p-2" value={baselineAto} onChange={event => setBaselineAto(event.target.value)} /></label>
                    <label className="text-sm sm:col-span-2">Certification evidence *<textarea required className="mt-1 block w-full rounded-lg border border-line bg-canvas p-2" value={baselineEvidence} onChange={event => setBaselineEvidence(event.target.value)} /></label>
                  </>}
                  <Button variant="primary" loading={createBaselineMutation.isPending} type="submit">
                    Freeze Baseline
                  </Button>
                </form>
              </Card>
            )}

            <Card className="space-y-3 p-4">
              <div className="flex flex-wrap gap-2">
                <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted"><span>Search baselines</span><input aria-label="Search baselines"
                  placeholder="Search baselines"
                  value={baselineSearch}
                  onChange={(event) => setBaselineSearch(event.target.value)}
                  className="w-full min-w-[220px] rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                /></label>
              </div>
              <div className="overflow-x-auto">
                <Table>
                  <THead>
                    <TR>
                      <TH>Label</TH>
                      <TH>Established</TH>
                      <TH>Action</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {filteredBaselines.length === 0 && <TableEmpty colSpan={3}>No baselines created yet.</TableEmpty>}
                    {filteredBaselines.map((baseline) => (
                      <TR key={baseline.id}>
                        <TD>{baseline.label}<span className="block text-xs text-muted">{baseline.certification_scope === 'whole_platform' ? `Whole-platform certification · ${formatDate(baseline.certification_at || null)} · ${baseline.certification_reference}` : 'Manual snapshot · certification unresolved'}</span></TD>
                        <TD>{formatDate(baseline.established_at)}</TD>
                        <TD>
                          <Button size="sm" variant="secondary" onClick={() => setSelectedBaselineId(baseline.id)}>
                            View Diff
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            </Card>

            {selectedBaselineId && baselineDiffQuery.isError && <LoadError subject="Baseline comparison" onRetry={() => baselineDiffQuery.refetch()} />}
            {selectedBaselineId && baselineDiffQuery.isLoading && <p role="status">Loading baseline comparison…</p>}
            {selectedBaselineId && baselineDiffQuery.data && (
              <Card className="space-y-4 p-6">
                <h3 className="text-base font-semibold text-ink">Baseline Diff Summary</h3>
                <div className="flex flex-wrap gap-2 text-sm">
                  <Badge tone="green">added: {baselineDiffQuery.data.summary.added}</Badge>
                  <Badge tone="red">removed: {baselineDiffQuery.data.summary.removed}</Badge>
                  <Badge tone="amber">changed: {baselineDiffQuery.data.summary.changed}</Badge>
                  <Badge tone="blue">total: {baselineDiffQuery.data.summary.total}</Badge>
                </div>
                <div className="overflow-x-auto">
                  <Table>
                    <THead>
                      <TR>
                        <TH>UID</TH>
                        <TH>Type</TH>
                        <TH>Baseline Version</TH>
                        <TH>Current Version</TH>
                        <TH>Changed Fields</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {baselineDiffQuery.data.items.length === 0 && (
                        <TableEmpty colSpan={5}>No differences from selected baseline.</TableEmpty>
                      )}
                      {baselineDiffQuery.data.items.map((item) => (
                        <TR key={`${item.component_uid}-${item.change_type}`}>
                          <TD>{item.component_uid}</TD>
                          <TD>{item.change_type}</TD>
                          <TD>{item.baseline_version || '-'}</TD>
                          <TD>{item.current_version || '-'}</TD>
                          <TD>{item.changed_fields.length ? item.changed_fields.join(', ') : '-'}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </div>
              </Card>
            )}
          </div>
        ))}

      {jurisdictionId && activeTab === 'reports' && (
        <Card className="space-y-4 p-6">
          <h2 className="text-lg font-semibold text-ink">Change reports</h2>
          {!canDownloadReports && (
            <p className="text-sm text-muted">
              Report downloads are available to manager, approver, and admin roles.
            </p>
          )}

          {canDownloadReports && (
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Export CSV reports for component inventory, change history, hardware locations,
                verified changes, and integration change evidence.
              </p>

              <div className="space-y-3">
                {danish && <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3"><div><p className="text-sm font-medium">Programme assurance</p><p className="text-xs text-muted">Governance, certification and regulator-submission records.</p></div><Button loading={downloadingReport === '/reports/change-management/programme-assurance'} onClick={() => {if (jurisdictionId) void downloadReport('/reports/change-management/programme-assurance', 'change-management-programme-assurance.csv',new URLSearchParams({jurisdiction_id:jurisdictionId}))}}>Download programme assurance</Button></div>}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3">
                  <div>
                    <p className="text-sm font-medium text-ink">Components Report</p>
                    <p className="text-xs text-muted">All registered component fields in the selected jurisdiction.</p>
                  </div>
                  <Button
                    onClick={() => {
                      if (!jurisdictionId) return
                      const params = new URLSearchParams({ jurisdiction_id: jurisdictionId })
                      downloadReport('/reports/change-management/components', 'change-management-components.csv', params)
                    }}
                    loading={downloadingReport === '/reports/change-management/components'}
                  >
                    Download components
                  </Button>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3">
                  <div>
                    <p className="text-sm font-medium text-ink">Hardware Locations</p>
                    <p className="text-xs text-muted">Geographical location records for hardware components.</p>
                  </div>
                  <Button
                    onClick={() => {
                      if (!jurisdictionId) return
                      const params = new URLSearchParams({ jurisdiction_id: jurisdictionId })
                      downloadReport(
                        '/reports/change-management/hardware-locations',
                        'change-management-hardware-locations.csv',
                        params
                      )
                    }}
                    loading={downloadingReport === '/reports/change-management/hardware-locations'}
                  >
                    Download hardware locations
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
                <label className="text-sm text-ink">Period</label>
                <select aria-label="Period"
                  value={reportPeriod}
                  onChange={(event) => setReportPeriod(event.target.value as '90' | '180' | '365')}
                  className="rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                >
                  <option value="90">90 Days</option>
                  <option value="180">180 Days</option>
                  <option value="365">365 Days</option>
                </select>
                <Button
                  onClick={() => {
                    if (!jurisdictionId) return
                    const params = new URLSearchParams({
                      jurisdiction_id: jurisdictionId,
                      period_days: reportPeriod,
                    })
                    downloadReport('/reports/change-management/verified-changes', 'change-management-verified-changes.csv', params)
                  }}
                  loading={downloadingReport === '/reports/change-management/verified-changes'}
                >
                  Verified Changes
                </Button>
                <Button
                  onClick={() => {
                    if (!jurisdictionId) return
                    const params = new URLSearchParams({
                      jurisdiction_id: jurisdictionId,
                      period_days: reportPeriod,
                    })
                    downloadReport('/reports/change-management/integration-changes', 'change-management-integration-changes.csv', params)
                  }}
                  loading={downloadingReport === '/reports/change-management/integration-changes'}
                >
                  Integration Changes
                </Button>
              </div>

              <div className="space-y-2 rounded-xl border border-line p-3">
                <p className="text-sm font-medium text-ink">Component History</p>
                <p className="text-xs text-muted">
                  Export full change history for a specific component, including status chronology and decision notes.
                </p>

                {!selectedRegisterId && (
                  <p className="text-xs text-muted">Select a register above to load component options.</p>
                )}

                {selectedRegisterId && (
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={historyComponentId}
                      onChange={(event) => setHistoryComponentId(event.target.value)}
                      aria-label="Component for history report"
                      className="w-full min-w-0 sm:w-auto sm:min-w-[280px] rounded-xl border border-line-strong bg-surface/90 px-3 py-2 text-sm"
                    >
                      <option value="">Select Component for History Report</option>
                      {components.map((component) => (
                        <option key={component.id} value={component.id}>
                          {component.component_uid}
                        </option>
                      ))}
                    </select>
                    <Button
                      disabled={!historyComponentId}
                      onClick={() => {
                        const params = new URLSearchParams({ component_id: historyComponentId })
                        downloadReport('/reports/change-management/component-history', 'change-management-component-history.csv', params)
                      }}
                      loading={downloadingReport === '/reports/change-management/component-history'}
                    >
                      Component History
                    </Button>
                  </div>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      <ConfirmDialog open={Boolean(pendingDiscard)} title="Discard unsaved changes?" description="Your saved records will remain. The unsaved entries in this form will be discarded." confirmLabel="Discard changes" onClose={() => setPendingDiscard(null)} onConfirm={() => {pendingDiscard?.();setPendingDiscard(null)}} />
      <DecisionModal
        open={!!pendingComponentDelete}
        title="Delete component"
        description={
          pendingComponentDelete
            ? `Delete component "${pendingComponentDelete.label}"?`
            : 'Delete selected component?'
        }
        confirmLabel="Delete component"
        confirmVariant="destructive"
        dangerDetails={[
          'The component will be removed from the register.',
          'Linked references in historical records remain as audit history.',
        ]}
        onConfirm={() => {
          if (!pendingComponentDelete) return
          deleteComponentMutation.mutate(pendingComponentDelete.componentId)
          setPendingComponentDelete(null)
        }}
        onClose={() => setPendingComponentDelete(null)}
        isWorking={deleteComponentMutation.isPending}
      />

      <DecisionModal
        open={!!pendingEventDelete}
        title="Delete timeline event"
        description="Provide a required reason for deleting this event."
        confirmLabel="Delete event"
        confirmVariant="destructive"
        rationaleMode="required"
        rationaleLabel="Deletion rationale"
        rationalePlaceholder="Why is this event being deleted?"
        rationaleValue={pendingEventDelete?.reason || ''}
        onRationaleChange={(value) =>
          setPendingEventDelete((prev) => (prev ? { ...prev, reason: value } : prev))
        }
        onConfirm={() => {
          if (!pendingEventDelete) return
          deleteEventMutation.mutate({
            changeId: pendingEventDelete.changeId,
            eventId: pendingEventDelete.eventId,
            reason: pendingEventDelete.reason.trim(),
          })
          setPendingEventDelete(null)
        }}
        onClose={() => setPendingEventDelete(null)}
        isWorking={deleteEventMutation.isPending}
      />

      <DecisionModal
        open={!!pendingIntegrationCheckDelete}
        title="Delete integration check"
        description="Provide a required reason for deleting this integration check."
        confirmLabel="Delete integration check"
        confirmVariant="destructive"
        rationaleMode="required"
        rationaleLabel="Deletion rationale"
        rationalePlaceholder="Why is this check being deleted?"
        rationaleValue={pendingIntegrationCheckDelete?.reason || ''}
        onRationaleChange={(value) =>
          setPendingIntegrationCheckDelete((prev) => (prev ? { ...prev, reason: value } : prev))
        }
        onConfirm={() => {
          if (!pendingIntegrationCheckDelete) return
          deleteIntegrationCheckMutation.mutate({
            changeId: pendingIntegrationCheckDelete.changeId,
            checkId: pendingIntegrationCheckDelete.checkId,
            reason: pendingIntegrationCheckDelete.reason.trim(),
          })
          setPendingIntegrationCheckDelete(null)
        }}
        onClose={() => setPendingIntegrationCheckDelete(null)}
        isWorking={deleteIntegrationCheckMutation.isPending}
      />
    </div>
  )
}
