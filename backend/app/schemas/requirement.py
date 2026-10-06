import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class RequirementSetCreateRequest(BaseModel):
    jurisdiction_id: uuid.UUID
    name: str = Field(..., min_length=1)
    document_type: str = Field(..., min_length=1, max_length=50)
    testing_frequency: str = Field(..., min_length=1)
    version: Optional[str] = None
    effective_date: Optional[datetime] = None


class RequirementCreateRequest(BaseModel):
    document_id: uuid.UUID
    requirement_set_version_id: Optional[uuid.UUID] = None
    reference_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    text: Optional[str] = None
    requirement_type: str = Field(default="mandatory")
    parent_id: Optional[uuid.UUID] = None
    default_owner_id: Optional[uuid.UUID] = None


class RequirementResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    jurisdiction_id: uuid.UUID
    source_extraction_id: Optional[uuid.UUID]
    document_id: Optional[uuid.UUID]
    requirement_set_version_id: Optional[uuid.UUID]
    source_requirement_id: Optional[uuid.UUID]
    reference_id: str
    title: Optional[str]
    text: str
    requirement_type: str
    parent_id: Optional[uuid.UUID]
    default_owner_id: Optional[uuid.UUID]
    active: bool
    version: int
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RequirementStatusResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    status: str
    assigned_to: Optional[uuid.UUID]
    comment: str
    changed_by: uuid.UUID
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceCounts(BaseModel):
    notes: int = 0
    files: int = 0
    links: int = 0


class RequirementWithStatusResponse(RequirementResponse):
    current_status: Optional[str] = None
    assigned_to: Optional[uuid.UUID] = None
    status_history: List[RequirementStatusResponse] = []
    evidence_counts: EvidenceCounts = Field(default_factory=EvidenceCounts)


class StatusChangeRequest(BaseModel):
    status: str
    comment: str = Field(..., min_length=1)


class AssignRequest(BaseModel):
    assigned_to: uuid.UUID
    comment: str


class RequirementUpdate(BaseModel):
    reference_id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    requirement_type: Optional[str] = None
    default_owner_id: Optional[uuid.UUID] = None
    sync_parent_from_reference: Optional[bool] = None


class RequirementSetSummaryResponse(BaseModel):
    document_id: uuid.UUID
    jurisdiction_id: uuid.UUID
    filename: Optional[str]
    has_source: bool
    name: Optional[str]
    document_type: str
    version: Optional[str] = None
    testing_frequency: Optional[str] = None
    document_status: str
    archived_at: Optional[datetime]
    requirements_total: int
    requirements_active: int
    current_version_id: Optional[uuid.UUID] = None
    current_version_number: Optional[int] = None
    current_version_status: Optional[str] = None


class RequirementSetVersionResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    document_id: uuid.UUID
    version_number: int
    status: str
    is_current: bool
    based_on_version_id: Optional[uuid.UUID]
    change_summary: Optional[str]
    created_by: uuid.UUID
    approved_by: Optional[uuid.UUID]
    created_at: datetime
    approved_at: Optional[datetime]
    locked_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class RequirementSetVersionCloneRequest(BaseModel):
    source_version_id: uuid.UUID
    change_summary: Optional[str] = None


class RequirementSetVersionSubmitRequest(BaseModel):
    change_summary: Optional[str] = None


class RequirementSetVersionApproveRequest(BaseModel):
    comment: Optional[str] = None
