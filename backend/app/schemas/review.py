import uuid
from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, ConfigDict, Field


class ReviewCycleCreate(BaseModel):
    name: str
    jurisdiction_id: uuid.UUID
    certification_project_id: Optional[uuid.UUID] = None
    cycle_type: str = "operational"
    description: Optional[str] = None
    scope: str = "all"
    scope_filter: Optional[str] = None
    document_ids: Optional[List[uuid.UUID]] = None
    deadline: Optional[datetime] = None
    default_assigned_reviewer_id: Optional[uuid.UUID] = None
    default_responsible_user_id: Optional[uuid.UUID] = None


class ReviewCycleBaselineVersion(BaseModel):
    document_id: uuid.UUID
    requirement_set_version_id: uuid.UUID
    version_number: int
    set_name: Optional[str] = None
    is_latest: bool = True
    latest_requirement_set_version_id: Optional[uuid.UUID] = None
    latest_version_number: Optional[int] = None


class ReviewCycleResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    certification_project_id: Optional[uuid.UUID]
    change_entry_id: Optional[uuid.UUID] = None
    predecessor_cycle_id: Optional[uuid.UUID]
    cycle_type: str
    name: str
    description: Optional[str]
    scope: str
    scope_filter: Optional[str]
    document_ids: Optional[List[uuid.UUID]] = None
    baseline_versions: List[ReviewCycleBaselineVersion] = Field(default_factory=list)
    deadline: Optional[datetime]
    status: str
    created_by: uuid.UUID
    closed_at: Optional[datetime]
    closed_by: Optional[uuid.UUID]
    snapshot_id: Optional[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewCycleListResponse(BaseModel):
    items: List[ReviewCycleResponse] = Field(default_factory=list)
    total: int


class ReviewCycleBaselineMigrationDeltaItem(BaseModel):
    document_id: Optional[uuid.UUID] = None
    set_name: Optional[str] = None
    reference_id: str
    old_requirement_id: Optional[uuid.UUID] = None
    new_requirement_id: Optional[uuid.UUID] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None


class ReviewCycleBaselineMigrationPreviewResponse(BaseModel):
    source_cycle_id: uuid.UUID
    target_version_ids: list[uuid.UUID] = Field(default_factory=list)
    matched: list[ReviewCycleBaselineMigrationDeltaItem] = Field(default_factory=list)
    changed: list[ReviewCycleBaselineMigrationDeltaItem] = Field(default_factory=list)
    added: list[ReviewCycleBaselineMigrationDeltaItem] = Field(default_factory=list)
    removed: list[ReviewCycleBaselineMigrationDeltaItem] = Field(default_factory=list)


class ReviewCycleBaselineMigrationChangedDecision(BaseModel):
    new_requirement_id: uuid.UUID
    action: Literal["reset_pending", "carry_forward"] = "reset_pending"


class ReviewCycleBaselineMigrationExecuteRequest(BaseModel):
    target_version_ids: list[uuid.UUID] = Field(default_factory=list)
    changed_decisions: list[ReviewCycleBaselineMigrationChangedDecision] = Field(
        default_factory=list
    )


class ReviewCycleBaselineMigrationExecuteResponse(BaseModel):
    created: bool
    from_cycle_id: uuid.UUID
    to_cycle_id: uuid.UUID
    migrated_items: int


class ReviewItemCommentCreate(BaseModel):
    body: str


class ReviewItemCommentUpdate(BaseModel):
    body: str


class ReviewItemCommentResponse(BaseModel):
    id: uuid.UUID
    review_item_id: uuid.UUID
    author_id: Optional[uuid.UUID]
    author_name: str
    body: str
    created_at: datetime
    updated_at: Optional[datetime]
    can_edit: bool = False

    model_config = ConfigDict(from_attributes=True)


class ReviewItemEvidenceFileResponse(BaseModel):
    comment_id: Optional[uuid.UUID] = None
    id: uuid.UUID
    review_item_id: uuid.UUID
    filename: str
    description: Optional[str]
    uploaded_by: uuid.UUID
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewItemResponse(BaseModel):
    id: uuid.UUID
    review_cycle_id: uuid.UUID
    requirement_id: uuid.UUID
    review_status: str
    assigned_reviewer_id: Optional[uuid.UUID]
    responsible_user_id: Optional[uuid.UUID]
    reviewer_id: Optional[uuid.UUID]
    review_comment: Optional[str]
    review_evidence: Optional[str]
    evidence_changed_at: Optional[datetime] = None
    jira_issue_key: Optional[str]
    jira_issue_url: Optional[str]
    jira_status: Optional[str]
    jira_summary: Optional[str]
    jira_assignee: Optional[str]
    jira_priority: Optional[str]
    jira_updated_at: Optional[datetime]
    jira_synced_at: Optional[datetime]
    jira_sync_error: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime
    comments: List[ReviewItemCommentResponse] = Field(default_factory=list)
    evidence_files: List[ReviewItemEvidenceFileResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReviewItemUpdate(BaseModel):
    review_status: Optional[Literal["pending", "confirmed", "updated", "escalated"]] = None
    requirement_status: Optional[
        Literal["not_started", "in_progress", "blocked", "evidenced", "not_applicable"]
    ] = None
    review_evidence: Optional[str] = None


class ReviewItemAssign(BaseModel):
    assigned_reviewer_id: Optional[uuid.UUID] = None
    responsible_user_id: Optional[uuid.UUID] = None


class ReviewItemBulkMutationRequest(BaseModel):
    item_ids: List[uuid.UUID] = Field(min_length=1)
    review_status: Optional[Literal["pending", "confirmed", "updated", "escalated"]] = None
    review_evidence: Optional[str] = None
    assigned_reviewer_id: Optional[uuid.UUID] = None
    responsible_user_id: Optional[uuid.UUID] = None


class ReviewItemBulkMutationFailure(BaseModel):
    item_id: uuid.UUID
    detail: str


class ReviewItemBulkMutationResponse(BaseModel):
    updated_count: int
    failed_count: int
    updated_item_ids: List[uuid.UUID] = Field(default_factory=list)
    failures: List[ReviewItemBulkMutationFailure] = Field(default_factory=list)


class ReviewItemJiraUpdate(BaseModel):
    jira_issue_key: Optional[str] = None


class ReviewCycleJiraSyncRequest(BaseModel):
    force: bool = False


class ReviewCycleJiraSyncResponse(BaseModel):
    total_items: int
    keyed_items: int
    refreshed_items: int
    skipped_fresh_items: int
    failed_items: int
    missing_items: int
    integration_configured: bool


class ReviewCycleReminderRequest(BaseModel):
    review_statuses: List[str]


class RequirementSummary(BaseModel):
    id: uuid.UUID
    document_id: Optional[uuid.UUID]
    reference_id: str
    title: Optional[str]
    text: str
    requirement_type: str
    parent_id: Optional[uuid.UUID]
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ReviewItemWithRequirementResponse(ReviewItemResponse):
    requirement: RequirementSummary
    requirement_current_status: Optional[str] = None
    reviewer_name: Optional[str] = None
    evidence_changed_since_review: bool = False


class ReviewCycleWithItemsResponse(ReviewCycleResponse):
    readiness: dict = Field(default_factory=dict)
    jira_integration_configured: bool = False
    items: List[ReviewItemWithRequirementResponse] = Field(default_factory=list)
    progress: dict = Field(default_factory=dict)


class SnapshotCreate(BaseModel):
    name: str
    description: Optional[str] = None


class SnapshotResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    snapshot_type: str
    total_requirements: int
    evidenced_requirements: int
    created_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SnapshotDetailResponse(SnapshotResponse):
    data_json: str
