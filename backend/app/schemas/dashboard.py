from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ComplianceMetric(BaseModel):
    total: int
    evidenced: int
    percentage: float


class StatusBreakdownItem(BaseModel):
    status: str
    total: int
    percentage_of_total: float


class Kpis(BaseModel):
    overall: ComplianceMetric
    mandatory: ComplianceMetric
    at_risk_count: int = Field(
        description="Count of requirements currently in in_progress or blocked.",
    )
    by_status: list[StatusBreakdownItem]


class DocumentBreakdownItem(BaseModel):
    document_id: str
    name: str
    document_type: str
    total: int
    evidenced: int
    percentage: float


class DocumentTypeBreakdownItem(BaseModel):
    document_type: str
    total: int
    evidenced: int
    percentage: float


class RequirementTypeBreakdownItem(BaseModel):
    requirement_type: str
    total: int
    evidenced: int
    percentage: float


class Breakdowns(BaseModel):
    by_document: list[DocumentBreakdownItem]
    by_document_type: list[DocumentTypeBreakdownItem]
    by_requirement_type: list[RequirementTypeBreakdownItem]


class EvidenceCounts(BaseModel):
    notes: int = 0
    files: int = 0
    links: int = 0


class AssignedRequirementItem(BaseModel):
    action_reasons: list[str] = Field(default_factory=list)
    requirement_id: str
    reference_id: str
    title: str | None = None
    document_name: str
    status: str
    assigned_to: str | None = None
    last_changed_at: datetime | None = None


class AssignedRequirements(BaseModel):
    total: int
    by_status: list[StatusBreakdownItem]
    items: list[AssignedRequirementItem]


class AssignedReviewItem(BaseModel):
    action_reasons: list[str] = Field(default_factory=list)
    cycle_id: str
    cycle_name: str
    deadline: datetime | None = None
    review_item_id: str
    requirement_reference_id: str
    requirement_title: str | None = None
    review_status: str
    project_id: str | None = None
    project_name: str | None = None
    change_entry_id: str | None = None
    change_title: str | None = None


class AssignedReviewItems(BaseModel):
    total: int
    by_status: list[StatusBreakdownItem]
    items: list[AssignedReviewItem]


class AssignedFormItem(BaseModel):
    case_id: str
    name: str
    kind: str
    status: str
    owner_id: str | None = None
    due_date: date | None = None
    application_id: str | None = None
    application_name: str | None = None
    project_id: str | None = None
    project_name: str | None = None


class AssignedForms(BaseModel):
    total: int = 0
    items: list[AssignedFormItem] = Field(default_factory=list)


class AuthorityQueryItem(BaseModel):
    query_id: str
    application_id: str
    application_name: str
    question: str
    status: str
    owner_id: str | None = None
    due_date: date | None = None


class AuthorityQueries(BaseModel):
    total: int = 0
    items: list[AuthorityQueryItem] = Field(default_factory=list)


class MyWork(BaseModel):
    assigned_requirements: AssignedRequirements
    assigned_review_items: AssignedReviewItems
    assigned_forms: AssignedForms = Field(default_factory=AssignedForms)
    authority_queries: AuthorityQueries = Field(default_factory=AuthorityQueries)


class DocumentQueueItem(BaseModel):
    id: str
    name: str | None = None
    filename: str
    document_type: str
    status: str
    created_at: datetime
    missing_fields: list[str] = []


class ExtractionFailureItem(BaseModel):
    run_id: str
    document_id: str
    document_name: str
    status: str
    error_message: str | None = None
    error_page: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExtractionFailuresRecent(BaseModel):
    last_7_days: int
    last_30_days: int
    items: list[ExtractionFailureItem]


class DocumentStatusCount(BaseModel):
    status: str
    total: int


class Queues(BaseModel):
    document_status_counts: list[DocumentStatusCount] = []
    documents_pending_approval: list[DocumentQueueItem] = []
    documents_needing_submission: list[DocumentQueueItem] = []
    documents_needing_extraction: list[DocumentQueueItem] = []
    extraction_failures_recent: ExtractionFailuresRecent


class ReviewCycleProgress(BaseModel):
    total: int
    completed: int
    pending: int


class ActiveReviewCycleItem(BaseModel):
    id: str
    name: str
    deadline: datetime | None = None
    progress: ReviewCycleProgress
    due_in_days: int | None = None
    my_pending_count: int | None = None


class ReviewCycles(BaseModel):
    active: list[ActiveReviewCycleItem]


class DataQualityRequirementItem(BaseModel):
    requirement_id: str
    reference_id: str
    title: str | None = None
    document_name: str
    current_status: str
    evidence_counts: EvidenceCounts = Field(default_factory=EvidenceCounts)


class DataQuality(BaseModel):
    evidenced_without_evidence: list[DataQualityRequirementItem]
    evidence_without_evidenced_status: list[DataQualityRequirementItem]
    unassigned_requirements_count: int
    unlinked_requirements_count: int


class AuditActivityItem(BaseModel):
    title: str | None = None
    destination: str | None = None
    id: str
    user_name: str
    action: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    summary: str | None = None


class SnapshotItem(BaseModel):
    id: str
    name: str
    snapshot_type: str
    total_requirements: int
    evidenced_requirements: int
    created_at: datetime


class DashboardResponse(BaseModel):
    generated_at: datetime
    kpis: Kpis
    breakdowns: Breakdowns
    my_work: MyWork
    review_cycles: ReviewCycles
    snapshots: list[SnapshotItem]
    recent_activity: list[AuditActivityItem]
    queues: Queues | None = None
    data_quality: DataQuality | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "description": "Role-adaptive compliance dashboard payload.",
        }
    )
