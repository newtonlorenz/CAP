import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.preparation import PreparationField

Scope = Literal["annex_only", "licence", "full_pack"]
ComponentKind = Literal["form", "annex", "document"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Revision(StrictModel):
    expected_revision: int = Field(ge=1)


class ApplicationCreate(StrictModel):
    visibility: Literal["organisation", "restricted", "secret"] = "secret"
    name: str = Field(min_length=1, max_length=255)
    scope: Scope
    jurisdiction_id: uuid.UUID
    applicant: str | None = Field(default=None, max_length=255)
    authority: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None


class ApplicationPatch(Revision):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scope: Scope | None = None
    applicant: str | None = Field(default=None, max_length=255)
    authority: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None


class SetupAnswers(StrictModel):
    foreign_applicant: bool = False
    representative_used: bool = False
    foreign_people: bool = False
    people: list[str] = Field(default_factory=list, max_length=100)


class GuidedItem(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    kind: ComponentKind
    required: bool = True
    included: bool = True
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    profile_item_key: str | None = Field(default=None, max_length=100)


class GuidedApplicationCreate(ApplicationCreate):
    profile_version: str
    setup_answers: SetupAnswers
    items: list[GuidedItem] = Field(max_length=200)


class ProfileItem(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    kind: ComponentKind
    required: bool = True
    condition: Literal["foreign_applicant", "representative_used", "foreign_people"] | None = None
    repeat_for: Literal["people"] | None = None
    source_url: str | None = None
    guidance: str | None = None


class ProfileContent(StrictModel):
    status: Literal["published", "draft"]
    label: str = Field(min_length=1, max_length=255)
    authority: str = Field(min_length=1, max_length=255)
    setup_questions: list[dict] = Field(default_factory=list)
    items: list[ProfileItem] = Field(default_factory=list, max_length=200)
    guidance: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    checked_at: date | None = None


class ProfilePatch(ProfileContent):
    jurisdiction_id: uuid.UUID
    expected_revision: int = Field(ge=0)


class DuplicateComponent(Revision):
    name: str = Field(min_length=1, max_length=255)


class ComponentCreate(Revision):
    name: str = Field(min_length=1, max_length=255)
    kind: ComponentKind
    required: bool = True
    included: bool = True
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    case_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    evidence_id: uuid.UUID | None = None
    form_fields: list[PreparationField] | None = Field(default=None, max_length=500)
    original_evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class ComponentPatch(Revision):
    expected_case_revision: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: ComponentKind | None = None
    required: bool | None = None
    included: bool | None = None
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    case_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    evidence_id: uuid.UUID | None = None
    form_fields: list[PreparationField] | None = Field(default=None, max_length=500)
    original_evidence_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class WorkflowAction(Revision):
    notes: str | None = Field(default=None, max_length=10000)
    reason: str | None = Field(default=None, max_length=10000)
    reference: str | None = Field(default=None, max_length=255)
    submitted_at: datetime | None = None
    outcome: str | None = Field(default=None, max_length=10000)


class FollowupCreate(Revision):
    question: str = Field(min_length=1, max_length=10000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None


class FollowupPatch(Revision):
    question: str | None = Field(default=None, min_length=1, max_length=10000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    response: str | None = Field(default=None, max_length=10000)
    evidence_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    status: Literal["open", "resolved"] | None = None
