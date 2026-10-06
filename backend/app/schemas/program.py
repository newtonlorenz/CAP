import uuid
from datetime import datetime
from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ControlCreate(BaseModel):
    jurisdiction_id: uuid.UUID
    code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    test_method: Optional[str] = None
    evidence_expectations: Optional[str] = None
    cadence_days: Optional[int] = Field(default=None, ge=1, le=3650)
    status: str = "active"


class ControlResponse(BaseModel):
    id: uuid.UUID
    jurisdiction_id: uuid.UUID
    code: str
    title: str
    description: Optional[str]
    test_method: Optional[str]
    evidence_expectations: Optional[str]
    cadence_days: Optional[int]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ObligationCreate(BaseModel):
    jurisdiction_id: uuid.UUID
    code: str = Field(min_length=1, max_length=100)
    legal_reference: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    status: str = "active"


class ObligationResponse(BaseModel):
    id: uuid.UUID
    jurisdiction_id: uuid.UUID
    code: str
    legal_reference: Optional[str]
    title: str
    description: Optional[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ControlCrosswalkCreate(BaseModel):
    source_control_id: uuid.UUID
    target_obligation_id: uuid.UUID
    mapping_strength: str = "partial"
    notes: Optional[str] = None


class ControlCrosswalkResponse(BaseModel):
    id: uuid.UUID
    source_control_id: uuid.UUID
    target_obligation_id: uuid.UUID
    mapping_strength: str
    notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EngagementFields(BaseModel):
    assurance_type: Optional[Literal["test", "audit", "certification"]] = None
    provider_name: Optional[str] = Field(default=None, max_length=255)
    engagement_reference: Optional[str] = Field(default=None, max_length=255)
    assurance_scope: Optional[str] = None
    system_version: Optional[str] = Field(default=None, max_length=255)
    scheduled_test_date: Optional[datetime] = None
    actual_test_date: Optional[datetime] = None
    report_reference: Optional[str] = Field(default=None, max_length=255)
    report_outcome: Optional[Literal["not_recorded", "passed", "passed_with_findings", "failed"]] = None
    report_issued_at: Optional[datetime] = None
    report_link: Optional[str] = Field(default=None, max_length=2048)

    @field_validator("report_link")
    @classmethod
    def validate_report_link(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Report link must be an HTTP(S) URL")
        return value


class CertificationProjectCreate(EngagementFields):
    source_document_id: Optional[uuid.UUID] = None
    requirement_set_ids: list[uuid.UUID] = Field(default_factory=list)
    jurisdiction_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    stage: str = "intake"
    status: str = "active"
    owner_id: Optional[uuid.UUID] = None
    target_submission_date: Optional[datetime] = None


class CertificationProjectUpdate(EngagementFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    target_submission_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProjectBaselineVersion(BaseModel):
    document_id: uuid.UUID
    requirement_set_version_id: uuid.UUID
    version_number: int
    set_name: Optional[str] = None


class CertificationProjectResponse(EngagementFields):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    source_document_id: Optional[uuid.UUID]
    requirement_set_ids: list[uuid.UUID] = Field(default_factory=list)
    baseline_versions: list[ProjectBaselineVersion] = Field(default_factory=list)
    jurisdiction_id: uuid.UUID
    name: str
    description: Optional[str]
    stage: str
    status: str
    owner_id: Optional[uuid.UUID]
    created_by: uuid.UUID
    started_at: Optional[datetime]
    target_submission_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CertificationProjectFromDocumentResponse(BaseModel):
    created: bool
    project: CertificationProjectResponse


class CertificationProjectSubmissionCycleResponse(BaseModel):
    created: bool
    review_cycle_id: uuid.UUID
    review_items_created: int = 0
    warning: Optional[str] = None


class CertificationProjectBaselineUpdateRequest(BaseModel):
    requirement_set_ids: list[uuid.UUID] = Field(default_factory=list)
    # Only explicitly selected versions may replace existing project baselines.
    target_version_ids: dict[uuid.UUID, uuid.UUID] = Field(default_factory=dict)
    expected_baseline_version_ids: Optional[dict[uuid.UUID, uuid.UUID]] = None


class CertificationProjectBaselineUpdateResponse(BaseModel):
    project: CertificationProjectResponse
    warning: Optional[str] = None


class ProgramStageCheck(BaseModel):
    code: str
    label: str
    passed: bool
    severity: str = "error"
    reason: Optional[str] = None
    cta_label: Optional[str] = None
    cta_path: Optional[str] = None


class ProgramGateBlocker(BaseModel):
    code: str
    reason: str
    cta_label: Optional[str] = None
    cta_path: Optional[str] = None


class ProgramStageReadiness(BaseModel):
    ready: bool
    blocker_count: int


class ProgramStageState(BaseModel):
    stage: str
    title: str
    order: int = Field(ge=0)
    state: str
    ready_to_advance: bool
    checks: list[ProgramStageCheck] = Field(default_factory=list)


class ProgramWorkspaceProjectDeepLinks(BaseModel):
    project: str
    review_cycle: Optional[str] = None
    submission_package: Optional[str] = None


class ProgramWorkspaceProjectSummary(BaseModel):
    project_id: uuid.UUID
    project_name: str
    jurisdiction_id: uuid.UUID
    stage: str
    status: str
    target_submission_date: Optional[datetime] = None
    stage_states: list[ProgramStageState] = Field(default_factory=list)
    current_stage_readiness: ProgramStageReadiness
    blockers: list[ProgramGateBlocker] = Field(default_factory=list)
    deep_links: ProgramWorkspaceProjectDeepLinks


class ProgramWorkspaceAction(BaseModel):
    id: str
    project_id: uuid.UUID
    stage: str
    priority: str = "medium"
    title: str
    summary: str
    cta_label: str
    cta_path: str
    role_scope: list[str] = Field(default_factory=list)


class ProgramWorkspaceSummaryResponse(BaseModel):
    generated_at: datetime
    jurisdiction_id: Optional[uuid.UUID] = None
    items: list[ProgramWorkspaceProjectSummary] = Field(default_factory=list)
    next_actions: list[ProgramWorkspaceAction] = Field(default_factory=list)


class BaselineMigrationDeltaItem(BaseModel):
    document_id: Optional[uuid.UUID] = None
    set_name: Optional[str] = None
    reference_id: str
    old_requirement_id: Optional[uuid.UUID] = None
    new_requirement_id: Optional[uuid.UUID] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None


class BaselineMigrationPreviewRequest(BaseModel):
    from_cycle_id: Optional[uuid.UUID] = None
    requirement_set_ids: list[uuid.UUID] = Field(default_factory=list)


class BaselineMigrationPreviewResponse(BaseModel):
    migration_id: uuid.UUID
    from_cycle_id: Optional[uuid.UUID] = None
    target_version_ids: list[uuid.UUID] = Field(default_factory=list)
    matched: list[BaselineMigrationDeltaItem] = Field(default_factory=list)
    changed: list[BaselineMigrationDeltaItem] = Field(default_factory=list)
    added: list[BaselineMigrationDeltaItem] = Field(default_factory=list)
    removed: list[BaselineMigrationDeltaItem] = Field(default_factory=list)


class ProjectMigrationChangedDecision(BaseModel):
    new_requirement_id: Optional[uuid.UUID] = None
    reference_id: Optional[str] = None  # Legacy clients may identify a unique reference.
    action: str = "reset_pending"


class ProjectMigrationExecuteRequest(BaseModel):
    migration_id: uuid.UUID
    changed_decisions: list[ProjectMigrationChangedDecision] = Field(default_factory=list)


class BaselineMigrationChangedDecision(BaseModel):
    reference_id: str
    action: str = Field(default="reset_pending")


class BaselineMigrationExecuteRequest(BaseModel):
    migration_id: uuid.UUID
    changed_decisions: list[BaselineMigrationChangedDecision] = Field(default_factory=list)


class BaselineMigrationExecuteResponse(BaseModel):
    created: bool
    from_cycle_id: Optional[uuid.UUID]
    to_cycle_id: uuid.UUID
    migrated_items: int


class CertificationProjectMilestoneCreate(BaseModel):
    stage: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=255)
    due_at: Optional[datetime] = None
    status: str = "pending"
    notes: Optional[str] = None


class CertificationProjectMilestoneUpdate(BaseModel):
    stage: Optional[str] = Field(default=None, min_length=1, max_length=40)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    due_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class CertificationProjectMilestoneResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    stage: str
    title: str
    due_at: Optional[datetime]
    status: str
    notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionChecklistItem(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=255)
    required: bool = True
    completed: bool = False
    guidance: Optional[str] = Field(default=None, max_length=500)


class SubmissionChecklistSection(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    items: list[SubmissionChecklistItem] = Field(default_factory=list)


class SubmissionChecklist(BaseModel):
    sections: list[SubmissionChecklistSection] = Field(default_factory=list)


class SubmissionChecklistCompletion(BaseModel):
    required_total: int = 0
    required_completed: int = 0
    optional_total: int = 0
    optional_completed: int = 0
    completion_score: float = 1.0
    ready: bool = True
    blocking_items: list[str] = Field(default_factory=list)


class SubmissionPackageCreate(BaseModel):
    project_id: uuid.UUID
    version: str = Field(min_length=1, max_length=50)
    review_cycle_id: Optional[uuid.UUID] = None
    snapshot_id: Optional[uuid.UUID] = None
    status: str = "draft"
    checklist_json: Optional[str] = None
    checklist: Optional[SubmissionChecklist] = None


class SubmissionPackageReturnRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class SubmissionPackageUpdate(BaseModel):
    review_cycle_id: Optional[uuid.UUID] = None
    snapshot_id: Optional[uuid.UUID] = None
    status: Optional[str] = None
    checklist_json: Optional[str] = None
    checklist: Optional[SubmissionChecklist] = None
    approval_requested_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None


class SubmissionPackageResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    review_cycle_id: Optional[uuid.UUID]
    snapshot_id: Optional[uuid.UUID]
    version: str
    status: str
    checklist_json: Optional[str]
    checklist: Optional[SubmissionChecklist] = None
    checklist_completion: SubmissionChecklistCompletion = Field(
        default_factory=SubmissionChecklistCompletion
    )
    approval_requested_at: Optional[datetime]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    locked_at: Optional[datetime]
    created_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionPackageArtifactCreate(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    file_path: Optional[str] = Field(default=None, max_length=500)
    link_url: Optional[str] = Field(default=None, max_length=2000)
    required: bool = False
    included: bool = True
    notes: Optional[str] = None


class SubmissionPackageArtifactUpdate(BaseModel):
    artifact_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    file_path: Optional[str] = Field(default=None, max_length=500)
    link_url: Optional[str] = Field(default=None, max_length=2000)
    required: Optional[bool] = None
    included: Optional[bool] = None
    notes: Optional[str] = None


class SubmissionPackageArtifactResponse(BaseModel):
    id: uuid.UUID
    submission_package_id: uuid.UUID
    artifact_type: str
    name: str
    file_path: Optional[str]
    link_url: Optional[str]
    required: bool
    included: bool
    notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionPackageGateCheckResponse(BaseModel):
    package_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    review_cycle_linked: bool
    review_cycle_closed: bool
    review_cycle_snapshot_id: Optional[uuid.UUID]
    snapshot_bound: bool
    required_artifacts_total: int
    required_artifacts_included: int
    missing_required_artifacts: list[str] = Field(default_factory=list)
    checklist_required_total: int = 0
    checklist_required_completed: int = 0
    checklist_completion_score: float = 1.0
    checklist_blocking_items: list[str] = Field(default_factory=list)
    checks_passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)


class MaintenancePlanCreate(BaseModel):
    certification_project_id: Optional[uuid.UUID] = None
    jurisdiction_id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    name: str = Field(min_length=1, max_length=255)
    cadence_days: int = Field(ge=1, le=3650)
    reminder_days: int = Field(default=7, ge=0, le=365)
    escalation_days: int = Field(default=3, ge=0, le=365)
    next_run_at: Optional[datetime] = None
    status: str = "active"
    auto_generated: bool = False
    owner_id: Optional[uuid.UUID] = None


class MaintenancePlanUpdate(BaseModel):
    certification_project_id: Optional[uuid.UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    cadence_days: Optional[int] = Field(default=None, ge=1, le=3650)
    reminder_days: Optional[int] = Field(default=None, ge=0, le=365)
    escalation_days: Optional[int] = Field(default=None, ge=0, le=365)
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    status: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None


class MaintenancePlanGenerateRequest(BaseModel):
    jurisdiction_id: Optional[uuid.UUID] = None
    only_missing: bool = True


class MaintenancePlanResponse(BaseModel):
    certification_project_id: Optional[uuid.UUID] = None
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    document_id: Optional[uuid.UUID]
    name: str
    cadence_days: int
    reminder_days: int
    escalation_days: int
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    status: str
    auto_generated: bool
    owner_id: Optional[uuid.UUID]
    created_by: Optional[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceEventResponse(BaseModel):
    id: uuid.UUID
    maintenance_plan_id: uuid.UUID
    review_cycle_id: Optional[uuid.UUID]
    event_type: str
    due_at: Optional[datetime]
    sent_at: Optional[datetime]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceItemCreate(BaseModel):
    requirement_id: uuid.UUID
    evidence_type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=255)
    body: Optional[str] = None
    file_path: Optional[str] = Field(default=None, max_length=500)
    link_url: Optional[str] = Field(default=None, max_length=2000)
    owner_id: Optional[uuid.UUID] = None
    reviewer_id: Optional[uuid.UUID] = None
    review_status: str = "draft"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    expires_in_days: Optional[int] = Field(default=None, ge=0, le=3650)


class EvidenceItemUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    body: Optional[str] = None
    file_path: Optional[str] = Field(default=None, max_length=500)
    link_url: Optional[str] = Field(default=None, max_length=2000)
    owner_id: Optional[uuid.UUID] = None
    reviewer_id: Optional[uuid.UUID] = None
    approved_by: Optional[uuid.UUID] = None
    review_status: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    expires_in_days: Optional[int] = Field(default=None, ge=0, le=3650)


class EvidenceItemResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    requirement_id: uuid.UUID
    evidence_type: str
    title: str
    body: Optional[str]
    file_path: Optional[str]
    link_url: Optional[str]
    owner_id: Optional[uuid.UUID]
    reviewer_id: Optional[uuid.UUID]
    approved_by: Optional[uuid.UUID]
    review_status: str
    valid_from: Optional[datetime]
    valid_to: Optional[datetime]
    approved_at: Optional[datetime]
    expires_in_days: Optional[int]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceValidationCreate(BaseModel):
    evidence_item_id: uuid.UUID
    validation_status: str = Field(min_length=1, max_length=30)
    comment: Optional[str] = None


class EvidenceValidationResponse(BaseModel):
    id: uuid.UUID
    evidence_item_id: uuid.UUID
    validator_id: Optional[uuid.UUID]
    validation_status: str
    comment: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationConnectionCreate(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    config_json: Optional[str] = None
    enabled: bool = True


class IntegrationConnectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    config_json: Optional[str] = None
    enabled: Optional[bool] = None
    last_sync_status: Optional[str] = None
    last_sync_message: Optional[str] = None
    last_sync_at: Optional[datetime] = None


class IntegrationConnectionResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    provider: str
    name: str
    config_json: Optional[str]
    enabled: bool
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    last_sync_message: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExportManifestCreate(BaseModel):
    scope_type: str = Field(min_length=1, max_length=50)
    scope_id: str = Field(min_length=1, max_length=255)
    payload: dict


class ExportManifestResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    scope_type: str
    scope_id: str
    payload_json: str
    hash_algo: str
    signature: str
    signed_by: Optional[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
