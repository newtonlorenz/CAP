import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UTCModel(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def normalise_utc_datetimes(cls, value):
        # SQLite historical rows and API responses can omit offsets; CAP stores UTC.
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
        return value


RELEVANCE_CODE_VALUES = {1, 2, 3}


RegulatoryScope = Literal["unknown", "base_platform", "rng", "game", "game_platform", "other"]
ResponsibilityRole = Literal[
    "unknown", "licensed_operator", "licensed_game_supplier", "unlicensed_subcontractor"
]


class ProgrammeAssurance(UTCModel):
    change_plan_reference: Optional[str] = None
    change_plan_approved_at: Optional[datetime] = None
    change_plan_approved_by: Optional[str] = None
    change_plan_approval_evidence: Optional[str] = None
    ato_accreditation_reference: Optional[str] = None
    ato_accreditation_evidence: Optional[str] = None
    responsible_owner: Optional[str] = None
    integration_procedure_reference: Optional[str] = None
    integration_procedure_approved_at: Optional[datetime] = None
    integration_procedure_ato: Optional[str] = None
    latest_certification_at: Optional[datetime] = None
    certification_reference: Optional[str] = None
    certification_evidence: Optional[str] = None
    certification_ato: Optional[str] = None
    report_submitted_at: Optional[datetime] = None
    cadence_anchor_at: Optional[datetime] = None
    renewal_report_due_at: Optional[datetime] = None
    renewal_due_at: Optional[datetime] = None
    postponed_until: Optional[datetime] = None
    postponement_notified_at: Optional[datetime] = None
    postponement_reference: Optional[str] = None


class ATOEvaluation(UTCModel):
    status: Literal["pending", "approved", "rejected"] = "pending"
    provider: Optional[str] = None
    reference: Optional[str] = None
    evidence: Optional[str] = None
    approved_at: Optional[datetime] = None


class ChangeCertification(UTCModel):
    timing: Optional[Literal["during", "direct_continuation"]] = None
    planned_at: Optional[datetime] = None
    schedule_reference: Optional[str] = None
    continuation_confirmed: bool = False
    continuation_started_at: Optional[datetime] = None
    continuation_evidence: Optional[str] = None
    status: Literal["pending", "certified", "rejected"] = "pending"
    provider: Optional[str] = None
    reference: Optional[str] = None
    evidence: Optional[str] = None
    certified_at: Optional[datetime] = None
    component_versions: dict[str, str] = Field(default_factory=dict)
    component_checksums: dict[str, str] = Field(default_factory=dict)


class CertificationDeferral(UTCModel):
    permission_reference: Optional[str] = None
    permission_evidence: Optional[str] = None
    qa_function: Optional[str] = None
    qa_qualified: bool = False
    qa_separate: bool = False
    due_at: Optional[datetime] = None


class RegulatorActions(UTCModel):
    rng_notified_at: Optional[datetime] = None
    rng_reference: Optional[str] = None
    game_approval_required: Optional[bool] = None
    game_approval_reference: Optional[str] = None
    game_approval_at: Optional[datetime] = None
    game_approval_basis: Optional[str] = None
    error_identified_at: Optional[datetime] = None
    error_notified_at: Optional[datetime] = None
    error_reference: Optional[str] = None
    error_notice_immediate: Optional[bool] = None


class SupplierActions(UTCModel):
    recommended_at: Optional[datetime] = None
    delay_justification: Optional[str] = None
    whole_system_evaluation: Optional[str] = None
    rejection_attestation: Optional[str] = None
    rejection_ato: Optional[str] = None
    rejection_evidence: Optional[str] = None


class ChangeCompliance(UTCModel):
    evaluation: ATOEvaluation = Field(default_factory=ATOEvaluation)
    certification: ChangeCertification = Field(default_factory=ChangeCertification)
    deferral: CertificationDeferral = Field(default_factory=CertificationDeferral)
    regulator: RegulatorActions = Field(default_factory=RegulatorActions)
    supplier: SupplierActions = Field(default_factory=SupplierActions)
    integration_procedure_reference: Optional[str] = None
    integration_requirement_references: list[str] = Field(default_factory=list)
    annual_certification_due_at: Optional[datetime] = None
    annual_certification_anchor_at: Optional[datetime] = None
    annual_certification_reference: Optional[str] = None
    annual_certification_provider: Optional[str] = None
    annual_certification_evidence: Optional[str] = None


class ComponentRegisterCreate(UTCModel):
    responsibility_role: ResponsibilityRole = "unknown"
    programme_assurance: Optional[ProgrammeAssurance] = None
    jurisdiction_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    status: Literal["active", "inactive"] = "active"


class ComponentRegisterUpdate(UTCModel):
    responsibility_role: Optional[ResponsibilityRole] = None
    programme_assurance: Optional[ProgrammeAssurance] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[Literal["active", "inactive"]] = None


class ComponentRegisterResponse(UTCModel):
    responsibility_role: str = "unknown"
    programme_assurance: Optional[ProgrammeAssurance] = None
    programme_readiness: Optional[dict[str, Any]] = None
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    name: str
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComponentBase(UTCModel):
    regulatory_scope: RegulatoryScope = "unknown"
    component_uid: str = Field(min_length=1, max_length=100)
    definition: str = Field(min_length=1)
    version: str = Field(min_length=1, max_length=100)
    identifying_characteristics: str = Field(min_length=1)
    change_owner_id: Optional[uuid.UUID] = None
    change_owner_name: Optional[str] = Field(default=None, max_length=255)

    confidentiality_code: int
    integrity_code: int
    availability_code: int
    accountability_code: int

    checksum_hash: Optional[str] = Field(default=None, max_length=255)
    is_hardware: bool = False
    geographic_location: Optional[str] = Field(default=None, max_length=255)

    hosting_model: Literal["on_prem", "private_cloud", "public_cloud"] = "on_prem"
    virtualized: bool = False
    public_cloud_provider: Optional[str] = Field(default=None, max_length=255)
    public_cloud_certification: Optional[str] = Field(default=None, max_length=255)
    public_cloud_iso27001: bool = False
    public_cloud_independent: bool = False
    public_cloud_redundancy: bool = False

    status: Literal["active", "inactive", "retired"] = "active"

    @field_validator(
        "confidentiality_code",
        "integrity_code",
        "availability_code",
        "accountability_code",
    )
    @classmethod
    def validate_relevance_codes(cls, value: int) -> int:
        if value not in RELEVANCE_CODE_VALUES:
            raise ValueError("Relevance codes must be one of: 1, 2, 3")
        return value


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(UTCModel):
    regulatory_scope: Optional[RegulatoryScope] = None
    component_uid: Optional[str] = Field(default=None, min_length=1, max_length=100)
    definition: Optional[str] = None
    version: Optional[str] = Field(default=None, min_length=1, max_length=100)
    identifying_characteristics: Optional[str] = None
    change_owner_id: Optional[uuid.UUID] = None
    change_owner_name: Optional[str] = Field(default=None, max_length=255)

    confidentiality_code: Optional[int] = None
    integrity_code: Optional[int] = None
    availability_code: Optional[int] = None
    accountability_code: Optional[int] = None

    checksum_hash: Optional[str] = Field(default=None, max_length=255)
    is_hardware: Optional[bool] = None
    geographic_location: Optional[str] = Field(default=None, max_length=255)

    hosting_model: Optional[Literal["on_prem", "private_cloud", "public_cloud"]] = None
    virtualized: Optional[bool] = None
    public_cloud_provider: Optional[str] = Field(default=None, max_length=255)
    public_cloud_certification: Optional[str] = Field(default=None, max_length=255)
    public_cloud_iso27001: Optional[bool] = None
    public_cloud_independent: Optional[bool] = None
    public_cloud_redundancy: Optional[bool] = None

    status: Optional[Literal["active", "inactive", "retired"]] = None

    @field_validator(
        "confidentiality_code",
        "integrity_code",
        "availability_code",
        "accountability_code",
    )
    @classmethod
    def validate_relevance_codes(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value not in RELEVANCE_CODE_VALUES:
            raise ValueError("Relevance codes must be one of: 1, 2, 3")
        return value


class ComponentResponse(UTCModel):
    regulatory_scope: str = "unknown"
    id: uuid.UUID
    register_id: uuid.UUID
    component_uid: str
    definition: str
    version: str
    identifying_characteristics: str
    change_owner_id: Optional[uuid.UUID]
    change_owner_name: Optional[str]
    confidentiality_code: int
    integrity_code: int
    availability_code: int
    accountability_code: int
    classification_code: int
    checksum_hash: Optional[str]
    is_hardware: bool
    geographic_location: Optional[str]
    hosting_model: str
    virtualized: bool
    public_cloud_provider: Optional[str]
    public_cloud_certification: Optional[str] = Field(default=None, max_length=255)
    public_cloud_iso27001: bool
    public_cloud_independent: bool
    public_cloud_redundancy: bool
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeEntryComponentInput(UTCModel):
    baseline_scope_assessment: Optional[str] = None
    planned_checksum_hash: Optional[str] = Field(default=None, max_length=255)
    baseline_id: Optional[uuid.UUID] = None
    component_id: uuid.UUID
    version_at_proposal: Optional[str] = Field(default=None, max_length=100)
    planned_version: Optional[str] = Field(default=None, max_length=100)
    implemented_version: Optional[str] = Field(default=None, max_length=100)


class ChangeEntryComponentResponse(UTCModel):
    baseline_scope_assessment: Optional[str] = None
    frozen_snapshot: Optional[dict[str, Any]] = None
    baseline_id: Optional[uuid.UUID] = None
    planned_checksum_hash: Optional[str] = None
    implemented_checksum_hash: Optional[str] = None
    id: uuid.UUID
    change_entry_id: uuid.UUID
    component_id: uuid.UUID
    version_at_proposal: Optional[str]
    planned_version: Optional[str]
    implemented_version: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeEntryCreate(UTCModel):
    compliance: ChangeCompliance = Field(default_factory=ChangeCompliance)
    blocking_assessment_ids: list[uuid.UUID] = Field(default_factory=list)
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    change_type: Literal["standard", "normal", "emergency"] = "normal"
    complexity_classification: Optional[str] = Field(default=None, max_length=100)
    resource_assessment: Optional[str] = None
    scheduling_assessment: Optional[str] = None
    affected_components_summary: Optional[str] = None
    affected_docs_summary: Optional[str] = None
    planned_start_at: Optional[datetime] = None
    planned_end_at: Optional[datetime] = None
    justification: Optional[str] = None
    affected_documentation: Optional[str] = None

    evaluation_effect: Optional[str] = None
    evaluation_risk: Optional[str] = None
    evaluation_regulatory_impact: Optional[str] = None
    evaluation_ciaa_impact: Optional[str] = None

    testing_org_required: bool = False
    testing_org_status: Optional[str] = Field(default=None, max_length=40)
    testing_org_due_at: Optional[datetime] = None
    testing_org_cycle: Optional[Literal["immediate", "quarterly", "annual"]] = None
    testing_org_next_due_at: Optional[datetime] = None
    testing_org_approved_at: Optional[datetime] = None
    integration_related: bool = False

    components: list[ChangeEntryComponentInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedule_order(self):
        if (
            self.planned_start_at
            and self.planned_end_at
            and self.planned_end_at < self.planned_start_at
        ):
            raise ValueError("planned_end_at must be after planned_start_at")
        return self


class ChangeEntryUpdate(UTCModel):
    compliance: Optional[ChangeCompliance] = None
    blocking_assessment_ids: Optional[list[uuid.UUID]] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    change_type: Optional[Literal["standard", "normal", "emergency"]] = None
    complexity_classification: Optional[str] = Field(default=None, max_length=100)
    resource_assessment: Optional[str] = None
    scheduling_assessment: Optional[str] = None
    affected_components_summary: Optional[str] = None
    affected_docs_summary: Optional[str] = None
    planned_start_at: Optional[datetime] = None
    planned_end_at: Optional[datetime] = None
    justification: Optional[str] = None
    affected_documentation: Optional[str] = None

    evaluation_effect: Optional[str] = None
    evaluation_risk: Optional[str] = None
    evaluation_regulatory_impact: Optional[str] = None
    evaluation_ciaa_impact: Optional[str] = None

    implementation_notes: Optional[str] = None
    verification_notes: Optional[str] = None
    implemented_start_at: Optional[datetime] = None
    implemented_end_at: Optional[datetime] = None

    testing_org_required: Optional[bool] = None
    testing_org_status: Optional[str] = Field(default=None, max_length=40)
    testing_org_due_at: Optional[datetime] = None
    testing_org_cycle: Optional[Literal["immediate", "quarterly", "annual"]] = None
    testing_org_next_due_at: Optional[datetime] = None
    testing_org_approved_at: Optional[datetime] = None
    integration_related: Optional[bool] = None

    components: Optional[list[ChangeEntryComponentInput]] = None

    @model_validator(mode="after")
    def validate_schedule_order(self):
        if (
            self.planned_start_at
            and self.planned_end_at
            and self.planned_end_at < self.planned_start_at
        ):
            raise ValueError("planned_end_at must be after planned_start_at")
        if (
            self.implemented_start_at
            and self.implemented_end_at
            and self.implemented_end_at < self.implemented_start_at
        ):
            raise ValueError("implemented_end_at must be after implemented_start_at")
        return self


class ChangeEntryApproveRequest(UTCModel):
    approval_decision: str = Field(min_length=1)


class ChangeEntryRejectRequest(UTCModel):
    rejection_reason: str = Field(min_length=1)


class ImplementedComponent(UTCModel):
    component_id: uuid.UUID
    implemented_version: str = Field(min_length=1, max_length=100)
    implemented_checksum_hash: Optional[str] = Field(default=None, max_length=255)


class ChangeRollbackRequest(UTCModel):
    recovery_change_id: uuid.UUID
    reason: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    follow_up: str = Field(min_length=1)
    components: list[ImplementedComponent] = Field(min_length=1)


class ChangeEntryImplementRequest(UTCModel):
    components: list[ImplementedComponent] = Field(default_factory=list)
    implementation_notes: str = Field(min_length=1)
    implemented_start_at: Optional[datetime] = None
    implemented_end_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_implementation_window(self):
        if (
            self.implemented_start_at
            and self.implemented_end_at
            and self.implemented_end_at < self.implemented_start_at
        ):
            raise ValueError("implemented_end_at must be after implemented_start_at")
        return self


class ChangeEntryVerifyRequest(UTCModel):
    verification_notes: str = Field(min_length=1)


class ChangeEventCreate(UTCModel):
    event_type: Literal["note", "decision", "status_change"]
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_event_note(self):
        if self.event_type in {"note", "decision"} and not (self.note and self.note.strip()):
            raise ValueError("note is required for note and decision events")
        return self


class ChangeEventUpdate(UTCModel):
    event_type: Optional[Literal["note", "decision", "status_change"]] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_event_note(self):
        if self.event_type in {"note", "decision"} and not (self.note and self.note.strip()):
            raise ValueError("note is required when event_type is note or decision")
        return self


class ChangeEntityDeleteRequest(UTCModel):
    reason: str = Field(min_length=1)


class ChangeEventResponse(UTCModel):
    id: uuid.UUID
    change_entry_id: uuid.UUID
    event_type: str
    status_from: Optional[str]
    status_to: Optional[str]
    note: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_by: Optional[uuid.UUID]
    updated_at: Optional[datetime]
    deleted_by: Optional[uuid.UUID]
    deleted_at: Optional[datetime]
    deletion_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class IntegrationCheckCreate(UTCModel):
    action: str = Field(min_length=1)
    action_reference: Optional[str] = Field(default=None, max_length=255)
    result: Literal["pending", "pass", "fail"] = "pending"
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    evidence_notes: Optional[str] = None


class IntegrationCheckUpdate(UTCModel):
    action: Optional[str] = Field(default=None, min_length=1)
    action_reference: Optional[str] = Field(default=None, max_length=255)
    result: Optional[Literal["pending", "pass", "fail"]] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    evidence_notes: Optional[str] = None


class IntegrationCheckResponse(UTCModel):
    id: uuid.UUID
    change_entry_id: uuid.UUID
    action: str
    action_reference: Optional[str]
    result: str
    completed_by: Optional[uuid.UUID]
    completed_at: Optional[datetime]
    notes: Optional[str]
    evidence_notes: Optional[str]
    created_at: datetime
    updated_by: Optional[uuid.UUID]
    updated_at: Optional[datetime]
    deleted_by: Optional[uuid.UUID]
    deleted_at: Optional[datetime]
    deletion_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ChangeActivityItem(UTCModel):
    id: str
    activity_type: Literal["status_event", "event", "integration_check", "audit_log"]
    action: str
    occurred_at: datetime
    actor_id: Optional[uuid.UUID]
    detail: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChangeActivityResponse(UTCModel):
    items: list[ChangeActivityItem]


class ChangeEntryResponse(UTCModel):
    compliance: Optional[ChangeCompliance] = None
    approved_scope: Optional[dict[str, Any]] = None
    blocking_assessment_ids: list[str] = Field(default_factory=list)
    readiness: Optional[dict[str, Any]] = None
    jurisdiction_id: Optional[uuid.UUID] = None
    id: uuid.UUID
    register_id: uuid.UUID
    title: str
    description: Optional[str]
    category: Optional[str]
    change_type: str
    proposed_by_name_snapshot: Optional[str]
    complexity_classification: Optional[str]
    resource_assessment: Optional[str]
    scheduling_assessment: Optional[str]
    affected_components_summary: Optional[str]
    affected_docs_summary: Optional[str]
    planned_start_at: Optional[datetime]
    planned_end_at: Optional[datetime]
    justification: Optional[str]
    affected_documentation: Optional[str]
    evaluation_effect: Optional[str]
    evaluation_risk: Optional[str]
    evaluation_regulatory_impact: Optional[str]
    evaluation_ciaa_impact: Optional[str]
    approval_decision: Optional[str]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    rejected_by: Optional[uuid.UUID]
    rejected_at: Optional[datetime]
    implementation_notes: Optional[str]
    implemented_by: Optional[uuid.UUID]
    implemented_at: Optional[datetime]
    implemented_start_at: Optional[datetime]
    implemented_end_at: Optional[datetime]
    verification_notes: Optional[str]
    verified_by: Optional[uuid.UUID]
    verified_at: Optional[datetime]
    testing_org_required: bool
    testing_org_status: Optional[str]
    testing_org_due_at: Optional[datetime]
    testing_org_cycle: Optional[str]
    testing_org_next_due_at: Optional[datetime]
    testing_org_approved_at: Optional[datetime]
    integration_related: bool
    status: str
    proposed_by: uuid.UUID
    proposed_at: datetime
    created_at: datetime
    updated_at: datetime
    assessments: list[dict[str, Any]] = Field(default_factory=list)
    components: list[ChangeEntryComponentResponse] = Field(default_factory=list)
    events: list[ChangeEventResponse] = Field(default_factory=list)
    integration_checks: list[IntegrationCheckResponse] = Field(default_factory=list)

    @field_validator("blocking_assessment_ids", mode="before")
    @classmethod
    def unresolved_ids(cls, value):
        return value or []

    model_config = ConfigDict(from_attributes=True)


class ComponentBaselineCreate(UTCModel):
    certification_scope: Literal["manual", "whole_platform"] = "manual"
    certification_at: Optional[datetime] = None
    certification_evidence: Optional[str] = None
    certification_ato: Optional[str] = None
    certification_reference: Optional[str] = None
    label: str = Field(min_length=1, max_length=255)


class ComponentBaselineResponse(UTCModel):
    certification_scope: Literal["manual", "whole_platform"] = "manual"
    certification_at: Optional[datetime] = None
    certification_evidence: Optional[str] = None
    certification_ato: Optional[str] = None
    certification_reference: Optional[str] = None
    id: uuid.UUID
    register_id: uuid.UUID
    label: str
    established_by: uuid.UUID
    established_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BaselineDiffItem(UTCModel):
    component_uid: str
    change_type: Literal["added", "removed", "changed"]
    baseline_version: Optional[str] = None
    current_version: Optional[str] = None
    baseline_classification_code: Optional[int] = None
    current_classification_code: Optional[int] = None
    changed_fields: list[str] = Field(default_factory=list)
    field_differences: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BaselineDiffResponse(UTCModel):
    baseline_id: uuid.UUID
    register_id: uuid.UUID
    summary: dict
    items: list[BaselineDiffItem]


class ChangeRequirementImpactCreate(UTCModel):
    requirement_set_version_id: uuid.UUID
    requirement_id: Optional[uuid.UUID] = None
    certification_project_id: Optional[uuid.UUID] = None
    rationale: str = Field(default="", max_length=4000)


class ChangeRequirementImpactsUpdate(UTCModel):
    items: list[ChangeRequirementImpactCreate] = Field(default_factory=list, max_length=200)


class ChangeAssessmentCreate(UTCModel):
    impact_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=255)
    deadline: Optional[datetime] = None
    default_assigned_reviewer_id: Optional[uuid.UUID] = None
    default_responsible_user_id: Optional[uuid.UUID] = None


class HistoricalComponentAttestation(UTCModel):
    component_id: uuid.UUID
    component_uid: str = Field(min_length=1)
    version: str = Field(min_length=1)
    checksum_hash: Optional[str] = None
    planned_checksum_hash: Optional[str] = Field(default=None, min_length=1)
    implemented_checksum_hash: Optional[str] = Field(default=None, min_length=1)
    regulatory_scope: RegulatoryScope
    confidentiality_code: int = Field(ge=1, le=3)
    integrity_code: int = Field(ge=1, le=3)
    availability_code: int = Field(ge=1, le=3)
    accountability_code: int = Field(ge=1, le=3)


class HistoricalScopeAttestationRequest(UTCModel):
    evidence_reference: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    responsibility_role: ResponsibilityRole
    components: list[HistoricalComponentAttestation] = Field(min_length=1)
