import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.extraction import ExtractionRunResponse


class DocumentCreate(BaseModel):
    document_type: str = Field(min_length=1, max_length=50)
    version: Optional[str] = None
    effective_date: Optional[datetime] = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    filename: Optional[str]
    has_source: bool
    name: Optional[str]
    document_type: str = Field(min_length=1, max_length=50)
    version: Optional[str]
    effective_date: Optional[datetime]
    status: str
    uploaded_by: uuid.UUID
    approval_comment: Optional[str]
    approved_by: Optional[uuid.UUID]
    current_extraction_id: Optional[uuid.UUID]
    maintenance_plan_id: Optional[uuid.UUID]
    cadence_interval_days: Optional[int]
    testing_frequency: Optional[str]
    archived_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentWithExtractionResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    filename: Optional[str]
    has_source: bool
    name: Optional[str]
    document_type: str = Field(min_length=1, max_length=50)
    version: Optional[str]
    effective_date: Optional[datetime]
    status: str
    uploaded_by: uuid.UUID
    approval_comment: Optional[str]
    approved_by: Optional[uuid.UUID]
    current_extraction_id: Optional[uuid.UUID]
    current_extraction: Optional[ExtractionRunResponse] = None
    maintenance_plan_id: Optional[uuid.UUID]
    cadence_interval_days: Optional[int]
    testing_frequency: Optional[str]
    archived_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[datetime] = None
    status: Optional[str] = None
    approval_comment: Optional[str] = None
    testing_frequency: Optional[str] = None


class DocumentMetadataUpdate(BaseModel):
    name: Optional[str] = None
    document_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    version: Optional[str] = None
    effective_date: Optional[datetime] = None
    testing_frequency: Optional[str] = None


class ExtractedRequirementResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    reference_id: str
    title: Optional[str]
    text: str
    original_text: str
    requirement_type: str
    parent_id: Optional[uuid.UUID]
    page_number: int
    confidence_score: float
    status: str
    needs_review: bool
    review_reason: Optional[str]
    source_excerpt: Optional[str]
    parser_strategy: str
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractedRequirementUpdate(BaseModel):
    reference_id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    requirement_type: Optional[str] = None
    status: Optional[str] = None
    needs_review: Optional[bool] = None
    review_reason: Optional[str] = None
    sync_parent_from_reference: Optional[bool] = None


class ExtractionFeedbackCreate(BaseModel):
    action: str
    corrected_reference_id: Optional[str] = None
    corrected_text: Optional[str] = None


class ExtractionFeedbackResponse(BaseModel):
    id: uuid.UUID
    extraction_run_id: uuid.UUID
    extracted_requirement_id: uuid.UUID
    action: str
    corrected_reference_id: Optional[str]
    corrected_text: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionBatchSplitItem(BaseModel):
    reference_id: str = Field(min_length=1)
    title: Optional[str] = None
    text: str = Field(min_length=1)
    requirement_type: str = "mandatory"
    status: str = "pending"


class ExtractionBatchOperation(BaseModel):
    action: str = Field(min_length=1)
    extraction_id: Optional[uuid.UUID] = None
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    reference_id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    requirement_type: Optional[str] = None
    status: Optional[str] = None
    comment: Optional[str] = None
    split_items: list[ExtractionBatchSplitItem] = Field(default_factory=list)


class ExtractionBatchRequest(BaseModel):
    operations: list[ExtractionBatchOperation] = Field(default_factory=list)
    republish: bool = False


class ExtractionBatchResult(BaseModel):
    processed: int
    updated_ids: list[uuid.UUID] = Field(default_factory=list)
    created_ids: list[uuid.UUID] = Field(default_factory=list)
    rejected_ids: list[uuid.UUID] = Field(default_factory=list)
    comments_added: int = 0
    errors: list[str] = Field(default_factory=list)


class ExtractionBatchDistributionItem(BaseModel):
    key: str
    total: int


class ExtractionFeedbackBatchFilter(BaseModel):
    needs_review_only: bool = True
    confidence_min: Optional[float] = Field(default=None, ge=0, le=1)
    confidence_max: Optional[float] = Field(default=None, ge=0, le=1)
    requirement_types: list[str] = Field(default_factory=list)
    section_prefixes: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    include_statuses: list[str] = Field(default_factory=list)
    exclude_statuses: list[str] = Field(default_factory=lambda: ["rejected"])

    @model_validator(mode="after")
    def validate_confidence_bounds(self):
        if (
            self.confidence_min is not None
            and self.confidence_max is not None
            and self.confidence_min > self.confidence_max
        ):
            raise ValueError("confidence_min must be less than or equal to confidence_max")
        return self


class ExtractionFeedbackBatchEdit(BaseModel):
    requirement_type: Optional[str] = None
    status: Optional[str] = None


class ExtractionFeedbackBatchAction(BaseModel):
    type: str = Field(min_length=1)
    edit: Optional[ExtractionFeedbackBatchEdit] = None

    @model_validator(mode="after")
    def validate_action(self):
        normalized = self.type.strip().lower()
        if normalized not in {"accept", "reject", "edit"}:
            raise ValueError("type must be one of: accept, reject, edit")
        if normalized == "edit":
            if self.edit is None or (
                self.edit.requirement_type is None and self.edit.status is None
            ):
                raise ValueError(
                    "edit payload is required for edit actions and must include requirement_type and/or status"
                )
        self.type = normalized
        return self


class ExtractionFeedbackBatchRequest(BaseModel):
    run_id: Optional[uuid.UUID] = None
    preview_only: bool = False
    filter: ExtractionFeedbackBatchFilter = Field(default_factory=ExtractionFeedbackBatchFilter)
    action: ExtractionFeedbackBatchAction


class ExtractionFeedbackBatchFailure(BaseModel):
    extraction_id: Optional[uuid.UUID] = None
    code: str
    detail: str


class ExtractionFeedbackBatchDistributions(BaseModel):
    by_review_reason: list[ExtractionBatchDistributionItem] = Field(default_factory=list)
    by_requirement_type: list[ExtractionBatchDistributionItem] = Field(default_factory=list)
    by_section_prefix: list[ExtractionBatchDistributionItem] = Field(default_factory=list)
    by_confidence_band: list[ExtractionBatchDistributionItem] = Field(default_factory=list)


class ExtractionFeedbackBatchResponse(BaseModel):
    preview_only: bool
    matched_count: int
    affected_count: int
    affected_ids: list[uuid.UUID] = Field(default_factory=list)
    affected_ids_truncated: bool = False
    failures: list[ExtractionFeedbackBatchFailure] = Field(default_factory=list)
    distributions: ExtractionFeedbackBatchDistributions


class ExtractionReorderRequest(BaseModel):
    run_id: uuid.UUID
    ordered_ids: list[uuid.UUID] = Field(default_factory=list)


class ExtractionReorderResponse(BaseModel):
    updated_count: int
    ordered_ids: list[uuid.UUID] = Field(default_factory=list)
